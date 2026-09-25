"""
embedder.py — 向量嵌入生成器

策略：
1. 优先使用 sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2)
   — 支持中文的多语言模型，输出 384 维向量
2. 回退到 TF-IDF (scikit-learn) — 完全本地运行，无需网络

架构设计：
- 统一接口 embed_text / embed_batch
- 向量存储层不感知嵌入实现细节
- 模型加载为延迟加载（首次调用时初始化）
"""

import os
import joblib
import numpy as np
from pathlib import Path

from .logger import get_logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

logger = get_logger("embedder")

# TF-IDF 向量器持久化路径。
# 训练与查询必须共用同一套词表，否则词表维度会不一致，
# 导致向量检索维度不匹配（index 侧 11433 维 vs query 侧 384 维哈希）。
TFIDF_PATH = PROJECT_ROOT / "rag" / "data" / "vectors" / "tfidf.joblib"

# 向量维度：与 sentence-transformers 多语言模型
# （paraphrase-multilingual-MiniLM-L12-v2）对齐，也是哈希回退嵌入的维度。
# 这是该常量的唯一真源，vector_store 从这里导入。
#
# 注意：TF-IDF 路径产出的维度 = 词表大小（动态），与这里无关；
# 索引端与查询端只要用同一套词表即可自洽。
VECTOR_DIM = 384

# 全局状态
_transformer_model = None
_model_attempted = False

# TF-IDF 后备
_tfidf_vectorizer = None
_tfidf_built = False


# ====== 中文工具函数 ======

_STOP_WORDS = {
    "的", "了", "是", "在", "有", "和", "就", "不", "都", "而",
    "且", "但", "也", "之", "与", "这", "那", "到", "去", "能", "会", "可",
    "以", "让", "把", "被", "从", "对", "为", "上", "下", "中", "里", "着", "过",
    "没", "很", "太", "更", "最", "又", "再", "才", "还", "已", "将", "要",
    "所", "如", "于", "其", "各", "因", "或", "及", "等",
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "can", "could",
    "this", "that", "these", "those", "i", "me", "my", "you", "your", "it",
}


def tokenize(text):
    """智能中文分词（兼顾词汇和语义覆盖）

    - 汉字提取为单字词和相邻双字词
    - 英文/数字保留原词
    - 过滤停用词
    """
    text = str(text).lower()
    tokens = []
    i = 0

    while i < len(text):
        ch = text[i]

        # 汉字
        if "一" <= ch <= "鿿":
            if ch not in _STOP_WORDS:
                tokens.append(ch)
                # 相邻双字词
                if i + 1 < len(text) and "一" <= text[i + 1] <= "鿿":
                    bigram = text[i:i + 2]
                    if bigram not in _STOP_WORDS:
                        tokens.append(bigram)
            i += 1
        # 英文/数字
        elif ch.isascii() and ch.isalnum():
            # 注意：不能只用 isalnum() —— 中文的 isalnum() 也是 True，
            # 那样 "ai写作需要去ai味" 整串会被当成一个 ASCII 词吞掉。
            word = ""
            while i < len(text) and text[i].isascii() and text[i].isalnum():
                word += text[i]
                i += 1
            if word and word not in _STOP_WORDS:
                tokens.append(word)
        else:
            i += 1

    return tokens


# ====== sentence-transformers 嵌入器 ======


def _try_load_transformer():
    """尝试加载 sentence-transformers 模型（延迟加载）

    默认只读本地缓存（local_files_only），避免因联网 HEAD 检查超时而卡住；
    需要下载模型时设置环境变量 NOVEL_HARNESS_ALLOW_MODEL_DOWNLOAD=1 放开。
    """
    global _transformer_model, _model_attempted
    if _model_attempted:
        return
    _model_attempted = True

    try:
        from sentence_transformers import SentenceTransformer

        model_name = "paraphrase-multilingual-MiniLM-L12-v2"
        local_only = os.environ.get("NOVEL_HARNESS_ALLOW_MODEL_DOWNLOAD") != "1"
        logger.info("加载模型: %s (local_files_only=%s) ...", model_name, local_only)
        _transformer_model = SentenceTransformer(model_name, local_files_only=local_only)
        dim = _transformer_model.get_sentence_embedding_dimension()
        logger.info("模型加载成功，输出维度: %d", dim)
    except Exception as e:
        # 这是最容易踩的坑：模型解析失败会被静默降级到 TF-IDF，
        # 而 TF-IDF 的向量维度 = 词表大小（默认上限 20000），不是 384 ——
        # 索引能跑，但向量文件会从 ~14MB 涨到数百 MB，且失去语义检索能力。
        # 所以这里把异常类型打出来，并给出可操作的下一步。
        logger.warning(
            "sentence-transformers 不可用（%s: %s），将使用 TF-IDF 统计嵌入回退方案；"
            "本次索引的向量维度 = 词表大小（默认上限 20000），不是 384。"
            "如需语义检索：确认模型权重已完整下载到 HF 缓存，"
            "或设置 NOVEL_HARNESS_ALLOW_MODEL_DOWNLOAD=1 后重建索引。",
            type(e).__name__,
            e,
        )


def _transformer_embed(texts):
    """使用 transformer 模型生成 embedding"""
    if _transformer_model is None:
        raise RuntimeError("Transformer model not loaded")

    if isinstance(texts, str):
        texts = [texts]

    embeddings = _transformer_model.encode(texts, normalize_embeddings=True)
    return embeddings.tolist()


# ====== TF-IDF 统计嵌入器（后备方案）======


def _custom_tokenizer(text):
    """模块级分词器（必须定义在模块层，否则 TfidfVectorizer 无法 pickle 落盘）"""
    return tokenize(text)


def build_vocabulary(corpus, max_vocab=20000):
    """从语料构建 TF-IDF 向量器，并持久化到磁盘

    参数：
        corpus: 字符串列表
        max_vocab: 最大词表大小
    """
    global _tfidf_vectorizer, _tfidf_built

    from sklearn.feature_extraction.text import TfidfVectorizer

    _tfidf_vectorizer = TfidfVectorizer(
        tokenizer=_custom_tokenizer,
        lowercase=True,
        max_features=max_vocab,
        norm="l2",
        token_pattern=None,
    )

    _tfidf_vectorizer.fit(corpus)
    _tfidf_built = True

    vocab_size = len(_tfidf_vectorizer.get_feature_names_out())
    logger.info("TF-IDF 词表构建完成: %d 个词, %d 篇文档", vocab_size, len(corpus))

    save_vectorizer()


def save_vectorizer():
    """把已训练的 TF-IDF 向量器落盘，供查询进程复用"""
    if _tfidf_vectorizer is None:
        return False
    try:
        TFIDF_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(_tfidf_vectorizer, TFIDF_PATH)
        logger.info("TF-IDF 词表已保存: %s", TFIDF_PATH.name)
        return True
    except Exception as e:
        logger.error("TF-IDF 词表保存失败: %s", e)
        return False


def load_vectorizer():
    """从磁盘加载已训练的 TF-IDF 向量器（查询进程用）

    返回 True 表示加载成功；加载后 embed_text 会与索引端共用同一套词表。
    """
    global _tfidf_vectorizer, _tfidf_built
    if _tfidf_built:
        return True
    if not TFIDF_PATH.exists():
        return False
    try:
        _tfidf_vectorizer = joblib.load(TFIDF_PATH)
        _tfidf_built = True
        logger.info("已加载本地 TF-IDF 词表: %d 个词", len(_tfidf_vectorizer.get_feature_names_out()))
        return True
    except Exception as e:
        logger.error("TF-IDF 词表加载失败: %s", e)
        _tfidf_vectorizer = None
        _tfidf_built = False
        return False


def clear_vectorizer():
    """清空内存中的向量器与磁盘快照（重建索引时调用）"""
    global _tfidf_vectorizer, _tfidf_built
    _tfidf_vectorizer = None
    _tfidf_built = False
    try:
        if TFIDF_PATH.exists():
            TFIDF_PATH.unlink()
    except OSError as e:
        logger.warning("TF-IDF 词表清理失败: %s", e)


def _tfidf_embed(texts):
    """TF-IDF 向量化"""
    if _tfidf_vectorizer is None:
        raise RuntimeError("TF-IDF 向量器尚未构建，请先调用 build_vocabulary()。")

    if isinstance(texts, str):
        texts = [texts]

    vectors = _tfidf_vectorizer.transform(texts)
    return vectors.toarray().tolist()


# ====== 公共接口 ======


def embed_text(text):
    """为单段文本生成 embedding

    降级顺序：
    1. sentence-transformers（语义，384 维）
    2. TF-IDF 向量器（内存中已训练 / 从磁盘加载，维度与索引端一致）
    3. 哈希嵌入（最后防线，仅在索引端为语义模型时可用）

    参数：
        text: 待嵌入文本

    返回：
        与索引端一致的维度的向量
    """
    if not _model_attempted:
        _try_load_transformer()

    if _transformer_model is not None:
        try:
            return _transformer_embed(text)[0]
        except Exception as e:
            logger.warning("Transformer 嵌入失败: %s，回退到 TF-IDF", e)

    # 查询进程：尝试加载索引端落盘的同一套词表
    if not _tfidf_built:
        load_vectorizer()

    if _tfidf_built and _tfidf_vectorizer is not None:
        return _tfidf_embed(text)[0]

    return _fallback_embed(text)


def embed_batch(texts):
    """批量生成嵌入向量"""
    if not isinstance(texts, (list, tuple)):
        texts = [texts]

    if not _model_attempted:
        _try_load_transformer()

    if _transformer_model is not None:
        try:
            return _transformer_embed(texts)
        except Exception as e:
            logger.warning("Transformer 批量嵌入失败: %s，回退到 TF-IDF", e)

    if not _tfidf_built:
        load_vectorizer()

    if _tfidf_built and _tfidf_vectorizer is not None:
        return _tfidf_embed(texts)

    return [_fallback_embed(t) for t in texts]


def _fallback_embed(text):
    """简单哈希嵌入（最后防线）"""
    dim = VECTOR_DIM
    vector = np.zeros(dim)
    text = str(text)
    length = len(text) or 1

    for i, ch in enumerate(text):
        idx = abs(ord(ch)) % dim
        vector[idx] += 1.0 / length

    norm = np.linalg.norm(vector)
    if norm > 1e-10:
        vector = vector / norm

    return vector.tolist()
