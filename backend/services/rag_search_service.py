"""Local vector search for RAG chunks."""

from typing import Any

from services.rag_embedding_service import (
    encode_texts,
    get_embedding_model_name,
    get_rag_vector_matrix_path,
    get_rag_vector_metadata_path,
)
from utils.json_utils import read_json


DEFAULT_TOP_K = 5
MAX_TOP_K = 20


def normalize_top_k(top_k: int | None) -> int:
    if top_k is None:
        return DEFAULT_TOP_K

    return min(MAX_TOP_K, max(1, int(top_k)))


def load_vector_index(extraction_id: str) -> tuple[Any, list[dict[str, Any]], dict[str, Any]]:
    import numpy as np

    matrix_path = get_rag_vector_matrix_path(extraction_id)
    metadata_path = get_rag_vector_metadata_path(extraction_id)

    if not matrix_path.exists():
        raise FileNotFoundError(f"向量矩阵不存在，请先运行 RAG 向量化：{matrix_path}")

    if not metadata_path.exists():
        raise FileNotFoundError(f"向量 metadata 不存在，请先运行 RAG 向量化：{metadata_path}")

    matrix = np.load(matrix_path)
    metadata_payload = read_json(metadata_path)
    metadata = metadata_payload.get("metadata", [])

    if matrix.ndim != 2 or matrix.shape[0] == 0:
        raise ValueError("向量矩阵为空或格式不正确")

    if not isinstance(metadata, list) or len(metadata) != matrix.shape[0]:
        raise ValueError("向量 metadata 数量与矩阵行数不一致")

    return matrix, metadata, metadata_payload


def build_query_text(query: str) -> str:
    query = query.strip()

    if not query:
        raise ValueError("检索问题不能为空")

    return f"Represent this sentence for searching relevant passages: {query}"


def search_rag_chunks(
    extraction_id: str,
    query: str,
    top_k: int | None = DEFAULT_TOP_K,
    min_score: float | None = None,
) -> dict[str, Any]:
    import numpy as np

    matrix, metadata, metadata_payload = load_vector_index(extraction_id)
    query_text = build_query_text(query)
    query_vectors = encode_texts([query_text])

    if not query_vectors:
        raise ValueError("问题向量化失败")

    query_vector = np.asarray(query_vectors[0], dtype=np.float32)
    scores = matrix @ query_vector
    requested_top_k = normalize_top_k(top_k)
    candidate_count = min(requested_top_k, len(scores))

    if candidate_count == 0:
        results: list[dict[str, Any]] = []
    else:
        ranked_indexes = np.argsort(scores)[::-1][:candidate_count]
        results = []

        for rank, index in enumerate(ranked_indexes, start=1):
            score = float(scores[index])

            if min_score is not None and score < min_score:
                continue

            item = metadata[int(index)]
            results.append(
                {
                    "rank": rank,
                    "score": round(score, 6),
                    "id": item.get("id"),
                    "text": item.get("text"),
                    "metadata": item.get("metadata", {}),
                }
            )

    return {
        "success": True,
        "message": "RAG 检索完成",
        "extraction_id": extraction_id,
        "query": query,
        "top_k": requested_top_k,
        "min_score": min_score,
        "embedding_model": metadata_payload.get("embedding_model") or get_embedding_model_name(),
        "embedding_dimension": metadata_payload.get("embedding_dimension"),
        "result_count": len(results),
        "results": results,
    }
