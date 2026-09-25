"""
vector_store.py — FAISS 向量存储层

使用 FAISS IndexFlatIP（内积 = 余弦相似度，因为向量已 L2 归一化）。
VECTOR_DIM = 384，与 sentence-transformers multilingual 模型对齐。
自动降级到 NumPy 暴力检索（FAISS 不可用时）。
"""

import math
import pickle
import threading
from pathlib import Path

import numpy as np

from ..logger import get_logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

logger = get_logger("vector_store")
VECTORS_DIR = PROJECT_ROOT / "rag" / "data" / "vectors"
FAISS_INDEX_PATH = VECTORS_DIR / "faiss.index"
META_PATH = VECTORS_DIR / "meta.pkl"

VECTOR_DIM = 384

_faiss_mod = None
_index = None
_meta: dict[str, dict] = {}
_loaded = False
_lock = threading.Lock()


def _try_import_faiss():
    global _faiss_mod
    if _faiss_mod is not None:
        return True
    try:
        import faiss as m
        _faiss_mod = m
        return True
    except ImportError:
        _faiss_mod = False
        return False


def _has_faiss():
    return _faiss_mod is not False and _faiss_mod is not None


def _ensure_loaded():
    global _loaded, _index, _meta
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        VECTORS_DIR.mkdir(parents=True, exist_ok=True)
        _try_import_faiss()
        if FAISS_INDEX_PATH.exists() and _has_faiss():
            try:
                _index = _faiss_mod.read_index(str(FAISS_INDEX_PATH))
            except Exception as e:
                logger.error("FAISS 加载失败: %s", e)
                _index = None
        if _index is None:
            _index = _load_numpy_fallback()
        if META_PATH.exists():
            try:
                with open(META_PATH, "rb") as f:
                    _meta = pickle.load(f)
            except Exception as e:
                logger.error("元数据加载失败: %s", e)
                _meta = {}
        _loaded = True


def _save():
    VECTORS_DIR.mkdir(parents=True, exist_ok=True)
    if _index is not None and _has_faiss() and hasattr(_index, 'ntotal'):
        try:
            _faiss_mod.write_index(_index, str(FAISS_INDEX_PATH))
        except Exception as e:
            logger.error("FAISS 写入失败: %s", e)
    _save_numpy_fallback()
    with open(META_PATH, "wb") as f:
        pickle.dump(_meta, f, protocol=5)


def _load_numpy_fallback():
    npy_path = VECTORS_DIR / "vectors.npy"
    if npy_path.exists():
        try:
            return np.load(str(npy_path))
        except Exception:
            pass
    return None


def _save_numpy_fallback():
    if _index is None:
        return
    arr = None
    if _has_faiss() and hasattr(_index, 'ntotal') and _index.ntotal > 0:
        try:
            arr = _faiss_mod.vector_to_array(
                _index.reconstruct_n(0, _index.ntotal)
            ).reshape(-1, VECTOR_DIM)
        except Exception:
            pass
    elif isinstance(_index, np.ndarray):
        arr = _index
    if arr is not None:
        np.save(str(VECTORS_DIR / "vectors.npy"), arr)


def _ensure_index(vectors: np.ndarray):
    global _index
    if _has_faiss():
        dim = vectors.shape[1]
        _index = _faiss_mod.IndexFlatIP(dim)
        _faiss_mod.normalize_L2(vectors)
        _index.add(vectors)
    else:
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms < 1e-10] = 1.0
        _index = vectors / norms


def _append_to_index(vectors: np.ndarray):
    global _index
    if _has_faiss() and hasattr(_index, 'add'):
        _faiss_mod.normalize_L2(vectors)
        _index.add(vectors)
    elif isinstance(_index, np.ndarray):
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms < 1e-10] = 1.0
        _index = np.vstack([_index, vectors / norms])
    else:
        _ensure_index(vectors)


def cosine_similarity(vec_a, vec_b):
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for i in range(len(vec_a)):
        va = vec_a[i]
        vb = vec_b[i] if i < len(vec_b) else 0
        dot += va * vb
        norm_a += va * va
        norm_b += vb * vb
    denom = math.sqrt(norm_a) * math.sqrt(norm_b)
    if denom < 1e-10:
        return 0.0
    return dot / denom


def insert_vectors(chunk_vectors):
    _ensure_loaded()
    if not chunk_vectors:
        return

    new_vectors = []
    for item in chunk_vectors:
        chunk_id = item["chunk_id"]
        _meta[chunk_id] = {"text": item.get("text", "")}
        new_vectors.append(item["vector"])

    arr = np.array(new_vectors, dtype=np.float32)
    if _index is None:
        _ensure_index(arr)
    else:
        _append_to_index(arr)
    _save()


def _faiss_search(query_vector, top_n):
    q = np.array([query_vector], dtype=np.float32)
    index_dim = _index.d
    if q.shape[1] != index_dim:
        raise ValueError(
            f"查询向量维度 {q.shape[1]} 与 FAISS 索引维度 {index_dim} 不一致"
        )
    _faiss_mod.normalize_L2(q)
    ntotal = _index.ntotal
    k = min(top_n, ntotal)
    if k <= 0:
        return []
    distances, indices = _index.search(q, k)
    chunk_ids = list(_meta.keys())
    results = []
    for pos, idx in enumerate(indices[0]):
        if idx < 0 or idx >= len(chunk_ids):
            continue
        results.append({"chunk_id": chunk_ids[idx], "score": float(distances[0][pos])})
    return results


def _numpy_search(query_vector, top_n):
    q = np.array(query_vector, dtype=np.float32)
    if _index is None:
        return []

    # 维度守卫：索引与查询必须由同一种嵌入器生成。
    # 维度不一致时直接返回空，避免 matmul 抛错中断整个检索流程。
    index_dim = _index.shape[1] if isinstance(_index, np.ndarray) else (
        _index.d if _has_faiss() else None
    )
    if index_dim is not None and q.shape[0] != index_dim:
        logger.error(
            "查询向量维度 %d 与索引维度 %d 不一致，跳过向量检索；"
            "请在构建索引的同一嵌入策略下查询，或重建索引。",
            q.shape[0], index_dim,
        )
        return []

    q_norm = np.linalg.norm(q)
    if q_norm > 1e-10:
        q = q / q_norm
    chunk_ids = list(_meta.keys())
    if len(chunk_ids) == 0:
        return []
    dots = _index @ q
    top_k = min(top_n, len(dots))
    top_indices = np.argpartition(dots, -top_k)[-top_k:]
    top_indices = top_indices[np.argsort(-dots[top_indices])]
    results = []
    for idx in top_indices:
        results.append({"chunk_id": chunk_ids[idx], "score": float(dots[idx])})
    return results


def vector_search(query_vector, top_n=15):
    _ensure_loaded()
    if _index is None:
        return []

    ntotal = _index.ntotal if hasattr(_index, 'ntotal') else (len(_index) if isinstance(_index, np.ndarray) else 0)
    if ntotal == 0:
        return []

    if _has_faiss() and hasattr(_index, 'search'):
        try:
            return _faiss_search(query_vector, top_n)
        except Exception as e:
            logger.error("FAISS 检索失败: %s，回退到 NumPy 检索", e)
            return _numpy_search(query_vector, top_n)
    return _numpy_search(query_vector, top_n)


def get_vector_count():
    _ensure_loaded()
    if _index is None:
        return 0
    if hasattr(_index, 'ntotal'):
        return _index.ntotal
    if isinstance(_index, np.ndarray):
        return len(_index)
    return len(_meta)


def get_all_vectors():
    _ensure_loaded()
    chunk_ids = list(_meta.keys())
    vectors = []
    if _has_faiss() and hasattr(_index, 'ntotal') and _index.ntotal > 0:
        ntotal = _index.ntotal
        for i in range(ntotal):
            vec = _faiss_mod.vector_to_array(_index.reconstruct(i))
            cid = chunk_ids[i] if i < len(chunk_ids) else f"chunk_{i}"
            vectors.append({
                "chunk_id": cid,
                "vector": vec.tolist(),
                "text": _meta.get(cid, {}).get("text", ""),
            })
    elif isinstance(_index, np.ndarray):
        for i, vec in enumerate(_index):
            cid = chunk_ids[i] if i < len(chunk_ids) else f"chunk_{i}"
            vectors.append({
                "chunk_id": cid,
                "vector": vec.tolist(),
                "text": _meta.get(cid, {}).get("text", ""),
            })
    return vectors


def clear():
    global _index, _meta, _loaded
    _index = None
    _meta = {}
    _loaded = True
    for p in [FAISS_INDEX_PATH, META_PATH, VECTORS_DIR / "vectors.npy"]:
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass
