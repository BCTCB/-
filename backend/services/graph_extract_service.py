import json
import re
from pathlib import Path
from typing import Any

from config import CHUNKS_DIR, RAW_GRAPHS_DIR
from prompts.kg_extraction_prompt import KG_EXTRACTION_PROMPT
from services.llm_service import chat_json
from utils.json_utils import extract_json_from_text, read_json, write_json


DEFAULT_ENTITY_TYPES = [
    "主题",
    "概念",
    "对象",
    "事件",
    "问题",
    "原因",
    "结果",
    "方法",
    "步骤",
    "工具",
    "指标",
    "条件",
    "结论",
    "组织",
    "人物",
    "地点",
    "时间",
    "文档结构",
    "其他",
]

DEFAULT_RELATION_TYPES = [
    "包含",
    "属于",
    "导致",
    "影响",
    "解决",
    "使用",
    "产生",
    "依赖",
    "组成",
    "解释",
    "说明",
    "对应",
    "适用于",
    "前置于",
    "后续于",
    "对比",
    "评价",
    "约束",
    "输入",
    "输出",
    "相关",
]

MAX_EXTRACT_CHARS = 2200
EXTRACT_OVERLAP_CHARS = 120
MAX_EVIDENCE_CHARS = 120


def get_chunks_json_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return CHUNKS_DIR / f"{safe_id}_chunks.json"


def get_raw_graph_json_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return RAW_GRAPHS_DIR / f"{safe_id}_raw_graph.json"


def get_raw_graph_jsonl_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return RAW_GRAPHS_DIR / f"{safe_id}_raw_graph_parts.jsonl"


def write_jsonl(data: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        for item in data:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"^[一二三四五六七八九十\d]+[、.．]\s*", "", name)
    return name[:120]


def truncate_evidence(evidence: Any) -> str:
    text = normalize_text(str(evidence or ""))
    return text[:MAX_EVIDENCE_CHARS]


def split_content_for_extraction(content: str, max_chars: int = MAX_EXTRACT_CHARS) -> list[str]:
    content = normalize_text(content)

    if not content:
        return []

    if len(content) <= max_chars:
        return [content]

    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", content) if paragraph.strip()]
    parts: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                parts.append(current.strip())
                current = ""

            start = 0
            while start < len(paragraph):
                end = min(start + max_chars, len(paragraph))
                parts.append(paragraph[start:end].strip())
                if end >= len(paragraph):
                    break
                start = max(0, end - EXTRACT_OVERLAP_CHARS)
            continue

        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph

        if len(candidate) <= max_chars:
            current = candidate
        else:
            parts.append(current.strip())
            current = paragraph

    if current:
        parts.append(current.strip())

    return parts


def should_skip_chunk(chunk: dict[str, Any]) -> str | None:
    content = normalize_text(str(chunk.get("content", "")))

    if not content:
        return "chunk 内容为空，跳过抽取"

    quality = chunk.get("quality", {})
    suggestion = quality.get("suggestion")
    level = quality.get("level")

    if suggestion == "discard":
        return "chunk 质量建议为 discard，跳过抽取"

    if level == "bad" and len(content) < 80:
        return "chunk 内容过短且质量为 bad，跳过抽取"

    return None


def build_extraction_input(
    chunk: dict[str, Any],
    part_content: str,
    part_id: str,
    mode: str,
    allowed_entity_types: list[str],
    allowed_relation_types: list[str],
) -> str:
    payload = {
        "mode": mode,
        "allowed_entity_types": allowed_entity_types,
        "allowed_relation_types": allowed_relation_types,
        "ontology_hint": {
            "entity_types": DEFAULT_ENTITY_TYPES,
            "relation_types": DEFAULT_RELATION_TYPES,
        },
        "chunk": {
            "chunk_id": chunk.get("chunk_id"),
            "part_id": part_id,
            "title": chunk.get("title"),
            "parent_title": chunk.get("parent_title"),
            "content": part_content,
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def repair_extraction_result(
    result: Any,
    chunk: dict[str, Any],
    part_id: str,
    mode: str,
) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("模型抽取结果必须是 JSON object")

    nodes = result.get("nodes", [])
    edges = result.get("edges", [])
    warnings = result.get("warnings", [])

    if not isinstance(nodes, list):
        nodes = []

    if not isinstance(edges, list):
        edges = []

    if not isinstance(warnings, list):
        warnings = [str(warnings)]

    repaired_nodes: list[dict[str, Any]] = []
    seen_node_names: set[tuple[str, str]] = set()

    for index, node in enumerate(nodes, start=1):
        if not isinstance(node, dict):
            continue

        name = normalize_name(str(node.get("name", "")))

        if not name:
            continue

        node_type = normalize_name(str(node.get("type", "其他") or "其他"))
        dedupe_key = (name, node_type)

        if dedupe_key in seen_node_names:
            continue

        seen_node_names.add(dedupe_key)
        aliases = node.get("aliases", [])

        if not isinstance(aliases, list):
            aliases = []

        repaired_nodes.append(
            {
                "id": str(node.get("id") or f"n{index}"),
                "name": name,
                "canonical_name": normalize_name(
                    str(node.get("canonical_name") or name)
                ),
                "aliases": [normalize_name(str(alias)) for alias in aliases if str(alias).strip()],
                "type": node_type,
                "description": normalize_text(str(node.get("description", "")))[:180],
                "source_chunk_id": str(chunk.get("chunk_id")),
                "source_part_id": part_id,
                "evidence": truncate_evidence(node.get("evidence")),
            }
        )

    valid_local_ids = {node["id"] for node in repaired_nodes}
    repaired_edges: list[dict[str, Any]] = []

    for index, edge in enumerate(edges, start=1):
        if not isinstance(edge, dict):
            continue

        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        relation = normalize_name(str(edge.get("relation", "相关") or "相关"))

        if source not in valid_local_ids or target not in valid_local_ids or source == target:
            continue

        repaired_edges.append(
            {
                "id": str(edge.get("id") or f"e{index}"),
                "source": source,
                "target": target,
                "relation": relation,
                "description": normalize_text(str(edge.get("description", "")))[:180],
                "source_chunk_id": str(chunk.get("chunk_id")),
                "source_part_id": part_id,
                "evidence": "",
            }
        )

    return {
        "chunk_id": str(chunk.get("chunk_id")),
        "part_id": part_id,
        "title": chunk.get("title"),
        "parent_title": chunk.get("parent_title"),
        "extraction_mode": mode,
        "nodes": repaired_nodes,
        "edges": repaired_edges,
        "warnings": [str(warning) for warning in warnings if str(warning).strip()],
    }


def rewrite_part_ids(
    part_result: dict[str, Any],
    node_start_index: int,
    edge_start_index: int,
) -> tuple[dict[str, Any], int, int]:
    id_map: dict[str, str] = {}

    for offset, node in enumerate(part_result["nodes"], start=0):
        old_id = node["id"]
        new_id = f"rn{node_start_index + offset}"
        id_map[old_id] = new_id
        node["id"] = new_id

    for offset, edge in enumerate(part_result["edges"], start=0):
        edge["id"] = f"re{edge_start_index + offset}"
        edge["source"] = id_map[edge["source"]]
        edge["target"] = id_map[edge["target"]]

    return (
        part_result,
        node_start_index + len(part_result["nodes"]),
        edge_start_index + len(part_result["edges"]),
    )


def extract_graph_from_part(
    chunk: dict[str, Any],
    part_content: str,
    part_id: str,
    mode: str,
    allowed_entity_types: list[str],
    allowed_relation_types: list[str],
) -> dict[str, Any]:
    user_prompt = build_extraction_input(
        chunk=chunk,
        part_content=part_content,
        part_id=part_id,
        mode=mode,
        allowed_entity_types=allowed_entity_types,
        allowed_relation_types=allowed_relation_types,
    )
    response_text = chat_json(
        system_prompt=KG_EXTRACTION_PROMPT,
        user_prompt=user_prompt,
        temperature=0.1,
    )
    result = extract_json_from_text(response_text)
    return repair_extraction_result(result, chunk=chunk, part_id=part_id, mode=mode)


def build_extraction_report(
    chunks: list[dict[str, Any]],
    part_results: list[dict[str, Any]],
    skipped_chunks: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    entity_type_count: dict[str, int] = {}
    relation_type_count: dict[str, int] = {}

    for node in nodes:
        node_type = node.get("type", "其他")
        entity_type_count[node_type] = entity_type_count.get(node_type, 0) + 1

    for edge in edges:
        relation = edge.get("relation", "相关")
        relation_type_count[relation] = relation_type_count.get(relation, 0) + 1

    warning_count = sum(len(result.get("warnings", [])) for result in part_results)

    return {
        "chunk_count": len(chunks),
        "processed_parts": len(part_results),
        "skipped_chunks": len(skipped_chunks),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "warning_count": warning_count,
        "entity_type_count": dict(
            sorted(entity_type_count.items(), key=lambda item: item[1], reverse=True)
        ),
        "relation_type_count": dict(
            sorted(relation_type_count.items(), key=lambda item: item[1], reverse=True)
        ),
        "skipped_chunk_preview": skipped_chunks[:20],
    }


def execute_graph_extraction_from_chunks(
    extraction_id: str,
    mode: str = "auto",
    allowed_entity_types: list[str] | None = None,
    allowed_relation_types: list[str] | None = None,
) -> dict[str, Any]:
    if mode not in {"auto", "custom"}:
        raise ValueError("mode 只能是 auto 或 custom")

    chunks_json_path = get_chunks_json_path(extraction_id)
    chunks_payload = read_json(chunks_json_path)
    chunks = chunks_payload.get("chunks", [])

    if not isinstance(chunks, list) or not chunks:
        raise RuntimeError("图谱抽取失败：未找到可用 chunks")

    allowed_entity_types = allowed_entity_types or []
    allowed_relation_types = allowed_relation_types or []

    part_results: list[dict[str, Any]] = []
    skipped_chunks: list[dict[str, Any]] = []
    all_nodes: list[dict[str, Any]] = []
    all_edges: list[dict[str, Any]] = []
    next_node_index = 1
    next_edge_index = 1

    for chunk in chunks:
        skip_reason = should_skip_chunk(chunk)

        if skip_reason:
            skipped_chunks.append(
                {
                    "chunk_id": chunk.get("chunk_id"),
                    "title": chunk.get("title"),
                    "reason": skip_reason,
                }
            )
            continue

        parts = split_content_for_extraction(str(chunk.get("content", "")))

        for part_index, part_content in enumerate(parts, start=1):
            part_id = f"{chunk.get('chunk_id')}__part_{part_index:03d}"

            try:
                part_result = extract_graph_from_part(
                    chunk=chunk,
                    part_content=part_content,
                    part_id=part_id,
                    mode=mode,
                    allowed_entity_types=allowed_entity_types,
                    allowed_relation_types=allowed_relation_types,
                )
            except Exception as error:
                part_result = {
                    "chunk_id": str(chunk.get("chunk_id")),
                    "part_id": part_id,
                    "title": chunk.get("title"),
                    "parent_title": chunk.get("parent_title"),
                    "extraction_mode": mode,
                    "nodes": [],
                    "edges": [],
                    "warnings": [f"模型抽取失败：{error}"],
                }

            part_result, next_node_index, next_edge_index = rewrite_part_ids(
                part_result,
                node_start_index=next_node_index,
                edge_start_index=next_edge_index,
            )
            part_results.append(part_result)
            all_nodes.extend(part_result["nodes"])
            all_edges.extend(part_result["edges"])

    raw_graph_json_path = get_raw_graph_json_path(extraction_id)
    raw_graph_jsonl_path = get_raw_graph_jsonl_path(extraction_id)
    report = build_extraction_report(
        chunks=chunks,
        part_results=part_results,
        skipped_chunks=skipped_chunks,
        nodes=all_nodes,
        edges=all_edges,
    )
    output_data = {
        "extraction_id": extraction_id,
        "source_chunks_path": str(chunks_json_path),
        "extraction_mode": mode,
        "allowed_entity_types": allowed_entity_types,
        "allowed_relation_types": allowed_relation_types,
        "ontology": {
            "entity_types": DEFAULT_ENTITY_TYPES,
            "relation_types": DEFAULT_RELATION_TYPES,
        },
        "report": report,
        "nodes": all_nodes,
        "edges": all_edges,
        "part_results": part_results,
        "skipped_chunks": skipped_chunks,
        "next_stage": "graph_merge",
    }

    write_json(raw_graph_json_path, output_data)
    write_jsonl(part_results, raw_graph_jsonl_path)

    return {
        "success": True,
        "message": "知识图谱抽取完成，raw graph 已保存供后续合并使用",
        "extraction_id": extraction_id,
        "chunks_json_path": str(chunks_json_path),
        "raw_graph_json_path": str(raw_graph_json_path),
        "raw_graph_jsonl_path": str(raw_graph_jsonl_path),
        "report": report,
        "next_stage": "graph_merge",
    }
