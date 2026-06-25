"""RAG embedding generation with Qwen3-Embedding.

The defaults are intentionally conservative for MacBook Air M1 class machines:
small batches, capped sequence length, and lazy model loading.
"""

import json
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from config import BASE_DIR, EMBEDDINGS_DIR
from services.rag_chunk_strategy_service import get_rag_chunks_json_path
from utils.json_utils import read_json, write_json


DEFAULT_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_EMBEDDING_BATCH_SIZE = 2
DEFAULT_EMBEDDING_MAX_SEQ_LENGTH = 2048
DEFAULT_EMBEDDING_LOCAL_FILES_ONLY = True


def add_local_embedding_paths() -> None:
    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("USE_FLAX", "0")
    os.environ.setdefault("USE_JAX", "0")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    os.environ.setdefault("HF_HOME", str(BASE_DIR / "data" / "models" / "huggingface"))

    local_paths = [
        BASE_DIR / "shims",
        BASE_DIR / ".deps",
    ]

    for path in reversed(local_paths):
        path_text = str(path)

        if path.exists() and path_text not in sys.path:
            sys.path.insert(0, path_text)


def get_rag_embeddings_json_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return EMBEDDINGS_DIR / "rag" / f"{safe_id}_rag_embeddings.json"


def get_rag_embeddings_jsonl_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return EMBEDDINGS_DIR / "rag" / f"{safe_id}_rag_embeddings.jsonl"


def get_rag_vector_matrix_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return EMBEDDINGS_DIR / "rag" / f"{safe_id}_rag_vectors.npy"


def get_rag_vector_metadata_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return EMBEDDINGS_DIR / "rag" / f"{safe_id}_rag_vector_metadata.json"


def write_jsonl(data: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        for item in data:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


def get_embedding_model_name() -> str:
    return os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)


def get_local_model_snapshot_path(model_name: str) -> Path | None:
    cache_repo_name = f"models--{model_name.replace('/', '--')}"
    snapshots_dir = BASE_DIR / "data" / "models" / "huggingface" / "hub" / cache_repo_name / "snapshots"

    if not snapshots_dir.exists():
        return None

    snapshots = sorted(
        [path for path in snapshots_dir.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    for snapshot in snapshots:
        if (snapshot / "config.json").exists() and (snapshot / "modules.json").exists():
            return snapshot

    return None


def resolve_embedding_model_path(model_name: str) -> str:
    if not get_embedding_local_files_only():
        return model_name

    local_snapshot = get_local_model_snapshot_path(model_name)

    if local_snapshot is not None:
        return str(local_snapshot)

    return model_name


def get_embedding_batch_size() -> int:
    raw_value = os.getenv("EMBEDDING_BATCH_SIZE", str(DEFAULT_EMBEDDING_BATCH_SIZE))

    try:
        return max(1, int(raw_value))
    except ValueError:
        return DEFAULT_EMBEDDING_BATCH_SIZE


def get_embedding_max_seq_length() -> int:
    raw_value = os.getenv("EMBEDDING_MAX_SEQ_LENGTH", str(DEFAULT_EMBEDDING_MAX_SEQ_LENGTH))

    try:
        return max(256, int(raw_value))
    except ValueError:
        return DEFAULT_EMBEDDING_MAX_SEQ_LENGTH


def get_embedding_local_files_only() -> bool:
    raw_value = os.getenv("EMBEDDING_LOCAL_FILES_ONLY", "true").strip().lower()
    return raw_value not in {"0", "false", "no", "off"}


def resolve_embedding_device() -> str | None:
    configured_device = os.getenv("EMBEDDING_DEVICE", "").strip()

    if configured_device:
        return configured_device

    try:
        import torch

        if torch.backends.mps.is_available():
            return "mps"
    except Exception:
        return None

    return None


@lru_cache(maxsize=1)
def get_embedding_model() -> Any:
    add_local_embedding_paths()

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as error:
        raise RuntimeError(
            "缺少 sentence-transformers 依赖，请安装 backend/requirements.txt 后重试"
        ) from error

    model_name = get_embedding_model_name()
    device = resolve_embedding_device()

    kwargs: dict[str, Any] = {}

    if device:
        kwargs["device"] = device

    model_path = resolve_embedding_model_path(model_name)
    model = SentenceTransformer(
        model_path,
        local_files_only=get_embedding_local_files_only(),
        **kwargs,
    )
    model.max_seq_length = get_embedding_max_seq_length()
    return model


def load_rag_chunks(extraction_id: str) -> list[dict[str, Any]]:
    chunks_path = get_rag_chunks_json_path(extraction_id)
    payload = read_json(chunks_path)
    chunks = payload.get("chunks", [])

    if not isinstance(chunks, list) or not chunks:
        raise ValueError("RAG chunks 文件中没有可向量化的 chunks")

    return [chunk for chunk in chunks if isinstance(chunk, dict)]


def build_embedding_metadata(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": chunk.get("chunk_id"),
        "doc_id": chunk.get("doc_id"),
        "title": chunk.get("title"),
        "parent_title": chunk.get("parent_title"),
        "chapter_title": chunk.get("chapter_title"),
        "section_title": chunk.get("section_title"),
        "retrieval_unit_type": chunk.get("retrieval_unit_type"),
        "source_split_type": chunk.get("source_split_type"),
        "source_chunk_id": chunk.get("source_chunk_id"),
        "window_index": chunk.get("window_index"),
        "start_char": chunk.get("start_char"),
        "end_char": chunk.get("end_char"),
        "char_count": chunk.get("char_count"),
    }


def encode_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    model = get_embedding_model()
    vectors = model.encode(
        texts,
        batch_size=get_embedding_batch_size(),
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    return [vector.tolist() for vector in vectors]


def generate_rag_embeddings_from_chunks(extraction_id: str) -> dict[str, Any]:
    chunks = load_rag_chunks(extraction_id)
    texts = [str(chunk.get("embedding_text") or chunk.get("content") or "") for chunk in chunks]
    valid_items = [
        (chunk, text)
        for chunk, text in zip(chunks, texts, strict=False)
        if text.strip()
    ]

    if not valid_items:
        raise ValueError("没有可向量化的 RAG chunk 文本")

    valid_chunks = [item[0] for item in valid_items]
    valid_texts = [item[1] for item in valid_items]
    vectors = encode_texts(valid_texts)
    records: list[dict[str, Any]] = []

    for chunk, text, vector in zip(valid_chunks, valid_texts, vectors, strict=False):
        records.append(
            {
                "id": chunk.get("chunk_id"),
                "text": text,
                "embedding": vector,
                "metadata": build_embedding_metadata(chunk),
            }
        )

    embeddings_json_path = get_rag_embeddings_json_path(extraction_id)
    embeddings_jsonl_path = get_rag_embeddings_jsonl_path(extraction_id)
    vector_matrix_path = get_rag_vector_matrix_path(extraction_id)
    vector_metadata_path = get_rag_vector_metadata_path(extraction_id)
    dimension = len(records[0]["embedding"]) if records else 0
    model_name = get_embedding_model_name()
    vector_matrix_path.parent.mkdir(parents=True, exist_ok=True)

    import numpy as np

    vector_matrix = np.asarray([record["embedding"] for record in records], dtype=np.float32)
    np.save(vector_matrix_path, vector_matrix)
    write_json(
        vector_metadata_path,
        {
            "extraction_id": extraction_id,
            "embedding_model": model_name,
            "embedding_dimension": dimension,
            "normalize_embeddings": True,
            "chunk_count": len(records),
            "metadata": [
                {
                    "id": record["id"],
                    "text": record["text"],
                    "metadata": record["metadata"],
                }
                for record in records
            ],
        },
    )
    output_data = {
        "extraction_id": extraction_id,
        "source_chunks_path": str(get_rag_chunks_json_path(extraction_id)),
        "embedding_model": model_name,
        "embedding_dimension": dimension,
        "normalize_embeddings": True,
        "chunk_count": len(records),
        "records": records,
        "vector_matrix_path": str(vector_matrix_path),
        "vector_metadata_path": str(vector_metadata_path),
        "next_stage": "rag_vector_store",
    }

    write_json(embeddings_json_path, output_data)
    write_jsonl(records, embeddings_jsonl_path)

    return {
        "success": True,
        "message": "RAG chunks 向量化完成",
        "extraction_id": extraction_id,
        "source_chunks_path": str(get_rag_chunks_json_path(extraction_id)),
        "embeddings_json_path": str(embeddings_json_path),
        "embeddings_jsonl_path": str(embeddings_jsonl_path),
        "vector_matrix_path": str(vector_matrix_path),
        "vector_metadata_path": str(vector_metadata_path),
        "embedding_model": model_name,
        "embedding_dimension": dimension,
        "chunk_count": len(records),
        "batch_size": get_embedding_batch_size(),
        "max_seq_length": get_embedding_max_seq_length(),
        "device": resolve_embedding_device() or "default",
        "next_stage": "rag_vector_store",
    }
