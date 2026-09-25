"""
server.py — RAG HTTP 服务

基于 FastAPI，提供 6 个端点：
- POST /retrieve        混合检索（面向 Agent 消费）
- GET  /health          健康检查
- POST /reindex         重建索引
- POST /explain-retrieval  检索解释（调试用，含分数分解）
- GET  /stats           索引统计
- GET  /routes          任务路由定义
"""

import json
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .logger import get_logger
from . import indexer
from . import router as router_mod
from . import context_pack as context_pack_mod
from .storage import sqlite_store
from .storage import vector_store
from .retriever import hybrid_retrieve

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

logger = get_logger("server")


# ====== Pydantic 模型 ======

class RetrieveRequest(BaseModel):
    """混合检索请求"""
    query: str = Field(..., description="检索查询文本", examples=["去AI味修改指南"])
    task_type: str | None = Field(
        None,
        description="任务类型（可选，自动路由）",
        examples=["humanization"],
    )
    project_hint: str | None = Field(None, description="项目提示（保留字段）")
    top_k: int = Field(5, description="返回结果数量", ge=1, le=20)


class RetrieveResultItem(BaseModel):
    """单条检索结果"""
    chunk_id: str
    title: str
    score: float
    reason: str
    snippet: str
    source_path: str
    source_type: str
    category: str
    tags: list[str]
    priority: int


class RetrieveMeta(BaseModel):
    """检索元信息"""
    total_candidates: int
    fts_count: int
    bm25_count: int
    vector_count: int
    elapsed_ms: int
    task_type: str | None
    confidence: float
    rerank_used: bool


class RetrieveContext(BaseModel):
    """上下文包，含排序结果和摘要"""
    task_type: str
    query: str
    results: list[RetrieveResultItem]
    knowledge_summary: str
    source_breakdown: dict[str, int]
    meta: RetrieveMeta


class RetrieveResponse(BaseModel):
    """检索响应"""
    context_pack: RetrieveContext
    context_text: str


class ReindexResponse(BaseModel):
    """重建索引响应"""
    status: str = Field(..., examples=["ok"])
    documents: int
    chunks: int
    vectors: int
    elapsed_seconds: float


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = Field(..., examples=["ok"])
    timestamp: str
    sqlite: bool = Field(description="SQLite 是否有数据")
    vectors: bool = Field(description="向量库是否已加载")


class ExplainRequest(BaseModel):
    """检索解释请求（调试用）"""
    query: str = Field(..., description="检索查询文本", examples=["这段太像 AI 写的"])
    task_type: str | None = Field(None, description="任务类型")


class RouteAnalysis(BaseModel):
    """路由分析结果"""
    task_type: str | None
    categories: list[str]
    stages: list[str]
    confidence: float


class ExplainResponse(BaseModel):
    """检索解释响应"""
    query: str
    route_analysis: RouteAnalysis
    retrieval: dict


class StatsResponse(BaseModel):
    """索引统计响应"""
    sqlite: dict
    vectors: int


# ====== 应用 ======

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化 SQLite，关闭时清理连接"""
    sqlite_store.initialize()
    stats = sqlite_store.get_stats()
    vec_count = vector_store.get_vector_count()
    logger.info("RAG 服务启动 (SQLite=%d docs/%d chunks, Vectors=%d)",
                stats["documents"], stats["chunks"], vec_count)
    yield
    sqlite_store.close()


app = FastAPI(
    title="novel-harness RAG Service",
    version="1.1.0",
    summary="轻量混合 RAG 知识层 — 面向 AI Agent 消费的写作知识检索服务",
    description="""
面向小说创作 Agent 的知识检索服务。

**核心能力：**
- 三路混合检索（FTS5 + BM25 + FAISS 向量）
- CrossEncoder 精排
- 任务路由（7 种写作场景自动识别）
- 可注入 Prompt 的上下文包输出

**适用场景：**
- 去 AI 味规则检索 → `humanization`
- 大纲质量评估 → `outline_review`
- 章节写前准备 → `chapter_prewrite`
- 题材分析路由 → `genre_routing`
- 节奏审查 → `rhythm_review`
- 一致性检查 → `consistency_check`
- 剧情灵感 → `ideation`
""",
    lifespan=lifespan,
    contact={
        "name": "novel-harness",
        "url": "https://github.com/anomalyco/novel-harness",
    },
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0",
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ====== 端点 ======

@app.get("/health", response_model=HealthResponse,
         tags=["系统"], summary="健康检查")
def health_check():
    """检查服务是否正常运行，及 SQLite/向量库加载状态"""
    stats = sqlite_store.get_stats()
    vec_count = vector_store.get_vector_count()
    return HealthResponse(
        status="ok",
        timestamp=datetime.now().isoformat(),
        sqlite=stats["documents"] > 0,
        vectors=vec_count > 0,
    )


@app.post("/retrieve", response_model=RetrieveResponse,
          tags=["检索"], summary="混合检索")
def retrieve(request: RetrieveRequest):
    """
    执行三路混合检索，返回上下文包。

    - **query**: 用户查询文本
    - **task_type**: （可选）指定任务类型，不传则自动路由
    - **top_k**: 返回结果数量 (1-20)
    """
    result = hybrid_retrieve(
        query=request.query,
        task_type=request.task_type,
        top_k=request.top_k,
    )
    context_pack = context_pack_mod.build_context_pack(
        query=request.query,
        retrieval_result=result,
        task_type=request.task_type,
        project_hint=request.project_hint,
    )
    context_text = context_pack_mod.context_pack_to_text(context_pack)

    return {
        "context_pack": context_pack,
        "context_text": context_text,
    }


@app.post("/reindex", response_model=ReindexResponse,
          tags=["管理"], summary="重建索引")
def reindex():
    """
    清空并重建完整索引。

    流程：清空 → 扫描 → 标准化 → 分块 → 嵌入 → BM25 → FAISS
    """
    start = __import__("time").time()
    stats = indexer.build_full_index()
    elapsed = __import__("time").time() - start
    return ReindexResponse(
        status="ok",
        documents=stats["documents"],
        chunks=stats["chunks"],
        vectors=stats["vectors"],
        elapsed_seconds=round(elapsed, 2),
    )


@app.post("/explain-retrieval", response_model=ExplainResponse,
          tags=["调试"], summary="检索解释（含分数分解）")
def explain_retrieval(request: ExplainRequest):
    """
    调试端点：返回路由分析 + 完整检索结果及分数分解。
    """
    route_result = router_mod.route_query(request.query) if not request.task_type else {
        "task_type": request.task_type,
        **router_mod.get_route(request.task_type),
    }
    result = hybrid_retrieve(
        query=request.query,
        task_type=request.task_type,
        top_k=5,
    )
    return {
        "query": request.query,
        "route_analysis": RouteAnalysis(
            task_type=route_result.get("task_type"),
            categories=route_result.get("categories", []),
            stages=route_result.get("stages", []),
            confidence=route_result.get("confidence", 0),
        ),
        "retrieval": result,
    }


@app.get("/stats", response_model=StatsResponse,
         tags=["系统"], summary="索引统计")
def stats():
    """返回 SQLite 和向量库的统计信息"""
    sqlite_stats = sqlite_store.get_stats()
    vec_count = vector_store.get_vector_count()
    return {
        "sqlite": sqlite_stats,
        "vectors": vec_count,
    }


@app.get("/routes", tags=["系统"], summary="任务路由定义")
def routes():
    """返回完整的任务路由配置（JSON）"""
    routes_path = PROJECT_ROOT / "rag" / "config" / "task-routes.json"
    try:
        with open(routes_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=500, detail=str(e))
