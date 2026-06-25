import json
import re
from pathlib import Path
from typing import Any

from config import CHUNKS_DIR, RAW_GRAPHS_DIR
from prompts.kg_extraction_prompt import KG_EXTRACTION_PROMPT
from services.llm_service import chat_json
from services.ontology_service import load_ontology_draft
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
    allowed_relations: list[dict[str, str]],
) -> str:
    payload = {
        "mode": mode,
        "allowed_entity_types": allowed_entity_types,
        "allowed_relation_types": allowed_relation_types,
        "allowed_relations": allowed_relations,
        "ontology_hint": {
            "entity_types": DEFAULT_ENTITY_TYPES,
            "relation_types": DEFAULT_RELATION_TYPES,
        },
        "chunk": {
            "chunk_id": chunk.get("chunk_id"),
            "part_id": part_id,
            "title": chunk.get("title"),
            "parent_title": chunk.get("parent_title"),
            "chapter_title": chunk.get("chapter_title"),
            "section_title": chunk.get("section_title"),
            "content": part_content,
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def normalize_allowed_relations(relations: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    if not isinstance(relations, list):
        return []

    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    for relation in relations:
        if not isinstance(relation, dict):
            continue

        source_type = normalize_name(str(relation.get("from", "")))
        relation_name = normalize_name(str(relation.get("relation", "")))
        target_type = normalize_name(str(relation.get("to", "")))
        key = (source_type, relation_name, target_type)

        if not all(key) or key in seen:
            continue

        seen.add(key)
        normalized.append(
            {
                "from": source_type,
                "relation": relation_name,
                "to": target_type,
            }
        )

    return normalized


def normalize_allowed_names(names: list[str] | None) -> list[str]:
    if not isinstance(names, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()

    for name in names:
        normalized_name = normalize_name(str(name))

        if not normalized_name or normalized_name in seen:
            continue

        seen.add(normalized_name)
        normalized.append(normalized_name)

    return normalized


def filter_constrained_result(
    part_result: dict[str, Any],
    allowed_entity_types: list[str],
    allowed_relation_types: list[str],
    allowed_relations: list[dict[str, str]],
) -> dict[str, Any]:
    allowed_entity_types = normalize_allowed_names(allowed_entity_types)
    allowed_relation_types = normalize_allowed_names(allowed_relation_types)
    allowed_relations = normalize_allowed_relations(allowed_relations)
    allowed_entity_type_set = set(allowed_entity_types)
    allowed_relation_type_set = set(allowed_relation_types)
    allowed_relation_set = {
        (relation["from"], relation["relation"], relation["to"])
        for relation in allowed_relations
    }

    nodes = part_result.get("nodes", [])
    edges = part_result.get("edges", [])

    if not isinstance(nodes, list):
        nodes = []

    if not isinstance(edges, list):
        edges = []

    if allowed_entity_type_set:
        nodes = [
            node for node in nodes
            if isinstance(node, dict) and node.get("type") in allowed_entity_type_set
        ]

    node_by_id = {
        str(node.get("id", "")): node
        for node in nodes
        if isinstance(node, dict) and node.get("id")
    }
    filtered_edges: list[dict[str, Any]] = []

    for edge in edges:
        if not isinstance(edge, dict):
            continue

        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        relation = str(edge.get("relation", ""))
        source_node = node_by_id.get(source)
        target_node = node_by_id.get(target)

        if not source_node or not target_node:
            continue

        if allowed_relation_type_set and relation not in allowed_relation_type_set:
            continue

        if allowed_relation_set:
            relation_key = (
                str(source_node.get("type", "")),
                relation,
                str(target_node.get("type", "")),
            )

            if relation_key not in allowed_relation_set:
                continue

        filtered_edges.append(edge)

    part_result["nodes"] = nodes
    part_result["edges"] = filtered_edges
    return part_result


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
        "chapter_title": chunk.get("chapter_title"),
        "section_title": chunk.get("section_title"),
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
    allowed_relations: list[dict[str, str]],
) -> dict[str, Any]:
    user_prompt = build_extraction_input(
        chunk=chunk,
        part_content=part_content,
        part_id=part_id,
        mode=mode,
        allowed_entity_types=allowed_entity_types,
        allowed_relation_types=allowed_relation_types,
        allowed_relations=allowed_relations,
    )
    response_text = chat_json(
        system_prompt=KG_EXTRACTION_PROMPT,
        user_prompt=user_prompt,
        temperature=0.1,
    )
    result = extract_json_from_text(response_text)
    part_result = repair_extraction_result(result, chunk=chunk, part_id=part_id, mode=mode)

    if mode == "ontology":
        part_result = filter_constrained_result(
            part_result=part_result,
            allowed_entity_types=allowed_entity_types,
            allowed_relation_types=allowed_relation_types,
            allowed_relations=allowed_relations,
        )

    return part_result


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


def normalize_instance_nodes(raw_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(raw_nodes, list):
        raise ValueError("nodes 必须是数组")

    normalized_nodes: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for index, node in enumerate(raw_nodes, start=1):
        if not isinstance(node, dict):
            continue

        node_id = normalize_name(str(node.get("id") or f"rn{index}"))
        name = normalize_name(str(node.get("name") or node.get("label") or ""))
        node_type = normalize_name(str(node.get("type") or "其他"))

        if not node_id or not name or node_id in seen_ids:
            continue

        seen_ids.add(node_id)
        normalized_nodes.append(
            {
                **node,
                "id": node_id,
                "name": name,
                "canonical_name": normalize_name(
                    str(node.get("canonical_name") or name)
                ),
                "type": node_type,
                "description": normalize_text(str(node.get("description", "")))[:180],
                "evidence": truncate_evidence(node.get("evidence")),
            }
        )

    if not normalized_nodes:
        raise ValueError("请至少保留一个实例节点")

    return normalized_nodes


def normalize_instance_edges(
    raw_edges: list[dict[str, Any]],
    node_ids: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(raw_edges, list):
        raise ValueError("edges 必须是数组")

    normalized_edges: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()

    for index, edge in enumerate(raw_edges, start=1):
        if not isinstance(edge, dict):
            continue

        edge_id = normalize_name(str(edge.get("id") or f"re{index}"))
        source = normalize_name(str(edge.get("source") or edge.get("from") or ""))
        target = normalize_name(str(edge.get("target") or edge.get("to") or ""))
        relation = normalize_name(str(edge.get("relation") or edge.get("label") or "相关"))
        key = (source, relation, target)

        if not edge_id or not relation or source == target:
            continue

        if source not in node_ids or target not in node_ids or key in seen_keys:
            continue

        seen_keys.add(key)
        normalized_edges.append(
            {
                **edge,
                "id": edge_id,
                "source": source,
                "target": target,
                "relation": relation,
                "description": normalize_text(str(edge.get("description", "")))[:180],
                "evidence": truncate_evidence(edge.get("evidence")),
            }
        )

    return normalized_edges


def update_graph_instantiation(
    extraction_id: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    raw_graph_json_path = get_raw_graph_json_path(extraction_id)
    raw_graph = read_json(raw_graph_json_path)

    if not isinstance(raw_graph, dict):
        raise ValueError("raw graph 必须是 JSON object")

    normalized_nodes = normalize_instance_nodes(nodes)
    normalized_edges = normalize_instance_edges(
        edges,
        node_ids={node["id"] for node in normalized_nodes},
    )
    report = build_extraction_report(
        chunks=[],
        part_results=raw_graph.get("part_results", []),
        skipped_chunks=raw_graph.get("skipped_chunks", []),
        nodes=normalized_nodes,
        edges=normalized_edges,
    )
    previous_report = raw_graph.get("report", {})

    if isinstance(previous_report, dict):
        report["chunk_count"] = previous_report.get("chunk_count", report["chunk_count"])
        report["processed_parts"] = previous_report.get("processed_parts", report["processed_parts"])
        report["skipped_chunks"] = previous_report.get("skipped_chunks", report["skipped_chunks"])
        report["warning_count"] = previous_report.get("warning_count", report["warning_count"])
        report["skipped_chunk_preview"] = previous_report.get(
            "skipped_chunk_preview",
            report["skipped_chunk_preview"],
        )

    raw_graph["nodes"] = normalized_nodes
    raw_graph["edges"] = normalized_edges
    raw_graph["report"] = report
    raw_graph["instance_review"] = {
        "status": "edited_by_user",
        "node_count": len(normalized_nodes),
        "edge_count": len(normalized_edges),
    }

    write_json(raw_graph_json_path, raw_graph)

    return {
        "success": True,
        "message": "本体实例化结果已保存",
        "extraction_id": extraction_id,
        "raw_graph_json_path": str(raw_graph_json_path),
        "report": report,
        "nodes": normalized_nodes,
        "edges": normalized_edges,
        "next_stage": "graph_merge",
    }


def execute_graph_extraction_from_chunks(
    extraction_id: str,
    mode: str = "ontology",
    allowed_entity_types: list[str] | None = None,
    allowed_relation_types: list[str] | None = None,
    allowed_relations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if mode != "ontology":
        raise ValueError("mode 只能是 ontology")

    chunks_json_path = get_chunks_json_path(extraction_id)
    chunks_payload = read_json(chunks_json_path)
    chunks = chunks_payload.get("chunks", [])

    if not isinstance(chunks, list) or not chunks:
        raise RuntimeError("图谱抽取失败：未找到可用 chunks")

    ontology_draft = load_ontology_draft(extraction_id)

    if mode == "ontology" and ontology_draft:
        ontology_payload = ontology_draft.get("ontology", {})
        allowed_entity_types = ontology_payload.get("entity_types", [])
        allowed_relation_types = ontology_payload.get("relation_types", [])
        allowed_relations = ontology_payload.get("relations", [])

    allowed_entity_types = normalize_allowed_names(allowed_entity_types)
    allowed_relation_types = normalize_allowed_names(allowed_relation_types)
    allowed_relations = normalize_allowed_relations(allowed_relations)

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
                    allowed_relations=allowed_relations,
                )
            except Exception as error:
                part_result = {
                    "chunk_id": str(chunk.get("chunk_id")),
                    "part_id": part_id,
                    "title": chunk.get("title"),
                    "parent_title": chunk.get("parent_title"),
                    "chapter_title": chunk.get("chapter_title"),
                    "section_title": chunk.get("section_title"),
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
        "allowed_relations": allowed_relations,
        "ontology": ontology_draft.get("ontology") if ontology_draft else {
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
        "message": "本体实例化完成，raw graph 已保存供后续处理使用",
        "extraction_id": extraction_id,
        "chunks_json_path": str(chunks_json_path),
        "raw_graph_json_path": str(raw_graph_json_path),
        "raw_graph_jsonl_path": str(raw_graph_jsonl_path),
        "report": report,
        "nodes": all_nodes,
        "edges": all_edges,
        "next_stage": "graph_merge",
    }
