"""Knowledge graph semantic merge service."""

import json
from pathlib import Path
from typing import Any

from config import CLEANED_GRAPHS_DIR, MERGED_GRAPHS_DIR
from prompts.entity_merge_prompt import ENTITY_MERGE_PROMPT
from services.llm_service import chat_json
from utils.json_utils import extract_json_from_text, read_json, write_json


MAX_NODES_PER_MERGE_BATCH = 80
MAX_TEXT_FIELD_CHARS = 180


def get_cleaned_graph_json_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return CLEANED_GRAPHS_DIR / f"{safe_id}_cleaned_graph.json"


def get_merged_graph_json_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return MERGED_GRAPHS_DIR / f"{safe_id}_merged_graph.json"


def normalize_text(value: Any, max_chars: int = MAX_TEXT_FIELD_CHARS) -> str:
    return str(value or "").strip()[:max_chars]


def build_llm_node_payload(node: dict[str, Any]) -> dict[str, Any]:
    aliases = node.get("aliases", [])

    if not isinstance(aliases, list):
        aliases = []

    return {
        "id": str(node.get("id", "")),
        "name": normalize_text(node.get("name")),
        "canonical_name": normalize_text(node.get("canonical_name") or node.get("name")),
        "aliases": [normalize_text(alias, 80) for alias in aliases if str(alias).strip()],
        "type": normalize_text(node.get("type") or "其他", 80),
        "description": normalize_text(node.get("description")),
        "evidence": normalize_text(node.get("evidence")),
    }


def group_nodes_by_type(nodes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}

    for node in nodes:
        if not isinstance(node, dict):
            continue

        node_type = normalize_text(node.get("type") or "其他", 80)
        grouped.setdefault(node_type, []).append(node)

    return grouped


def split_batches(nodes: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    return [
        nodes[index : index + MAX_NODES_PER_MERGE_BATCH]
        for index in range(0, len(nodes), MAX_NODES_PER_MERGE_BATCH)
    ]


def build_merge_input(entity_type: str, nodes: list[dict[str, Any]]) -> str:
    payload = {
        "entity_type": entity_type,
        "nodes": [build_llm_node_payload(node) for node in nodes],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def request_merge_groups(entity_type: str, nodes: list[dict[str, Any]]) -> dict[str, Any]:
    response_text = chat_json(
        system_prompt=ENTITY_MERGE_PROMPT,
        user_prompt=build_merge_input(entity_type, nodes),
        temperature=0.1,
    )
    result = extract_json_from_text(response_text)

    if not isinstance(result, dict):
        raise ValueError("实体合并结果必须是 JSON object")

    merge_groups = result.get("merge_groups", [])
    warnings = result.get("warnings", [])

    if not isinstance(merge_groups, list):
        merge_groups = []

    if not isinstance(warnings, list):
        warnings = [str(warnings)]

    return {
        "merge_groups": merge_groups,
        "warnings": [str(warning) for warning in warnings if str(warning).strip()],
    }


def validate_merge_groups(
    raw_groups: list[Any],
    batch_nodes: list[dict[str, Any]],
    used_node_ids: set[str],
) -> list[dict[str, Any]]:
    batch_node_ids = {str(node.get("id", "")) for node in batch_nodes}
    groups: list[dict[str, Any]] = []

    for raw_group in raw_groups:
        if not isinstance(raw_group, dict):
            continue

        canonical_name = normalize_text(raw_group.get("canonical_name"), 120)
        node_ids = raw_group.get("node_ids", [])

        if not canonical_name or not isinstance(node_ids, list):
            continue

        cleaned_node_ids: list[str] = []

        for node_id in node_ids:
            node_id = str(node_id)

            if (
                node_id not in batch_node_ids
                or node_id in used_node_ids
                or node_id in cleaned_node_ids
            ):
                continue

            cleaned_node_ids.append(node_id)

        if len(cleaned_node_ids) < 2:
            continue

        used_node_ids.update(cleaned_node_ids)
        groups.append(
            {
                "canonical_name": canonical_name,
                "node_ids": cleaned_node_ids,
                "reason": normalize_text(raw_group.get("reason"), 220),
            }
        )

    return groups


def collect_semantic_merge_groups(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    all_groups: list[dict[str, Any]] = []
    warnings: list[str] = []
    used_node_ids: set[str] = set()

    for entity_type, typed_nodes in group_nodes_by_type(nodes).items():
        if len(typed_nodes) < 2:
            continue

        for batch in split_batches(typed_nodes):
            if len(batch) < 2:
                continue

            try:
                result = request_merge_groups(entity_type, batch)
            except Exception as error:
                warnings.append(f"{entity_type} 批次合并失败：{error}")
                continue

            groups = validate_merge_groups(
                raw_groups=result["merge_groups"],
                batch_nodes=batch,
                used_node_ids=used_node_ids,
            )
            all_groups.extend(groups)
            warnings.extend(result["warnings"])

    return {
        "merge_groups": all_groups,
        "warnings": warnings,
    }


def unique_texts(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []

    for value in values:
        text = str(value or "").strip()

        if not text or text in seen:
            continue

        seen.add(text)
        results.append(text)

    return results


def merge_node_group(
    group: dict[str, Any],
    node_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    group_nodes = [node_by_id[node_id] for node_id in group["node_ids"] if node_id in node_by_id]

    if len(group_nodes) < 2:
        return None

    representative = dict(group_nodes[0])
    canonical_name = group["canonical_name"]
    alias_candidates: list[Any] = []
    description_candidates: list[Any] = []
    evidence_candidates: list[Any] = []
    chunk_candidates: list[Any] = []
    part_candidates: list[Any] = []

    for node in group_nodes:
        alias_candidates.extend(
            [
                node.get("name"),
                node.get("canonical_name"),
                *node.get("aliases", []),
            ]
            if isinstance(node.get("aliases", []), list)
            else [node.get("name"), node.get("canonical_name")]
        )
        description_candidates.append(node.get("description"))
        evidence_candidates.append(node.get("evidence"))
        chunk_candidates.append(node.get("source_chunk_id"))
        part_candidates.append(node.get("source_part_id"))

    aliases = [alias for alias in unique_texts(alias_candidates) if alias != canonical_name]
    descriptions = unique_texts(description_candidates)
    evidences = unique_texts(evidence_candidates)

    representative["name"] = canonical_name
    representative["canonical_name"] = canonical_name
    representative["aliases"] = aliases
    representative["description"] = "；".join(descriptions)[:240]
    representative["evidence"] = "；".join(evidences)[:240]
    representative["source_chunk_id"] = ",".join(unique_texts(chunk_candidates))
    representative["source_part_id"] = ",".join(unique_texts(part_candidates))
    representative["merged_from_node_ids"] = group["node_ids"]
    representative["merge_reason"] = group.get("reason", "")

    return representative


def build_node_id_map(merge_groups: list[dict[str, Any]]) -> dict[str, str]:
    node_id_map: dict[str, str] = {}

    for group in merge_groups:
        representative_id = group["node_ids"][0]

        for node_id in group["node_ids"]:
            node_id_map[node_id] = representative_id

    return node_id_map


def dedupe_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    deduped_edges: list[dict[str, Any]] = []
    next_edge_index = 1

    for edge in edges:
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        relation = normalize_text(edge.get("relation") or "相关", 120)

        if not source or not target or source == target:
            continue

        dedupe_key = (source, target, relation)

        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)
        rewritten_edge = dict(edge)
        rewritten_edge["id"] = f"me{next_edge_index}"
        rewritten_edge["source"] = source
        rewritten_edge["target"] = target
        rewritten_edge["relation"] = relation
        deduped_edges.append(rewritten_edge)
        next_edge_index += 1

    return deduped_edges


def apply_semantic_merges(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    merge_groups: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    node_by_id = {str(node.get("id", "")): node for node in nodes if isinstance(node, dict)}
    merged_node_by_id: dict[str, dict[str, Any]] = {}
    removed_node_ids: set[str] = set()

    for group in merge_groups:
        merged_node = merge_node_group(group, node_by_id)

        if merged_node is None:
            continue

        representative_id = group["node_ids"][0]
        merged_node_by_id[representative_id] = merged_node
        removed_node_ids.update(group["node_ids"][1:])

    merged_nodes: list[dict[str, Any]] = []

    for node in nodes:
        node_id = str(node.get("id", ""))

        if node_id in removed_node_ids:
            continue

        merged_nodes.append(merged_node_by_id.get(node_id, node))

    node_id_map = build_node_id_map(merge_groups)
    rewritten_edges: list[dict[str, Any]] = []

    for edge in edges:
        if not isinstance(edge, dict):
            continue

        rewritten_edge = dict(edge)
        rewritten_edge["source"] = node_id_map.get(
            str(edge.get("source", "")),
            str(edge.get("source", "")),
        )
        rewritten_edge["target"] = node_id_map.get(
            str(edge.get("target", "")),
            str(edge.get("target", "")),
        )
        rewritten_edges.append(rewritten_edge)

    return merged_nodes, dedupe_edges(rewritten_edges)


def update_merged_report(payload: dict[str, Any], nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    report = payload.get("report")

    if not isinstance(report, dict):
        payload["report"] = {}
        report = payload["report"]

    report["node_count"] = len(nodes)
    report["edge_count"] = len(edges)


def merge_cleaned_graph_semantic_nodes(extraction_id: str) -> dict[str, Any]:
    cleaned_graph_json_path = get_cleaned_graph_json_path(extraction_id)
    cleaned_graph = read_json(cleaned_graph_json_path)

    if not isinstance(cleaned_graph, dict):
        raise ValueError("cleaned graph 必须是 JSON object")

    nodes = cleaned_graph.get("nodes", [])
    edges = cleaned_graph.get("edges", [])

    if not isinstance(nodes, list):
        nodes = []

    if not isinstance(edges, list):
        edges = []

    semantic_result = collect_semantic_merge_groups(nodes)
    merge_groups = semantic_result["merge_groups"]
    merged_nodes, merged_edges = apply_semantic_merges(nodes, edges, merge_groups)
    merged_graph = dict(cleaned_graph)
    merged_graph["nodes"] = merged_nodes
    merged_graph["edges"] = merged_edges
    update_merged_report(merged_graph, merged_nodes, merged_edges)
    merged_graph["semantic_merge"] = {
        "source_cleaned_graph_path": str(cleaned_graph_json_path),
        "merge_groups": merge_groups,
        "warnings": semantic_result["warnings"],
        "merged_node_count": len(nodes) - len(merged_nodes),
        "removed_edge_count": len(edges) - len(merged_edges),
        "next_stage": "final_graph",
    }
    merged_graph["next_stage"] = "final_graph"

    merged_graph_json_path = get_merged_graph_json_path(extraction_id)
    write_json(merged_graph_json_path, merged_graph)

    return {
        "success": True,
        "message": "语义相同节点清洗完成：已统一命名并合并节点",
        "extraction_id": extraction_id,
        "cleaned_graph_json_path": str(cleaned_graph_json_path),
        "merged_graph_json_path": str(merged_graph_json_path),
        "merge_groups": merge_groups,
        "warnings": semantic_result["warnings"],
        "report": merged_graph.get("report", {}),
        "next_stage": "final_graph",
    }
