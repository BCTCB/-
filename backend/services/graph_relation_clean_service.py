"""Knowledge graph relation cleaning service."""

import json
from pathlib import Path
from typing import Any

from config import MERGED_GRAPHS_DIR, RELATION_CLEANED_GRAPHS_DIR
from prompts.relation_clean_prompt import RELATION_CLEAN_PROMPT
from services.llm_service import chat_json
from utils.json_utils import extract_json_from_text, read_json, write_json


MAX_RELATIONS_PER_BATCH = 100
MAX_EXAMPLES_PER_RELATION = 5
MAX_TEXT_FIELD_CHARS = 180


def get_merged_graph_json_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return MERGED_GRAPHS_DIR / f"{safe_id}_merged_graph.json"


def get_relation_cleaned_graph_json_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return RELATION_CLEANED_GRAPHS_DIR / f"{safe_id}_relation_cleaned_graph.json"


def normalize_text(value: Any, max_chars: int = MAX_TEXT_FIELD_CHARS) -> str:
    return str(value or "").strip()[:max_chars]


def build_node_name_map(nodes: list[dict[str, Any]]) -> dict[str, str]:
    node_names: dict[str, str] = {}

    for node in nodes:
        if not isinstance(node, dict):
            continue

        node_id = str(node.get("id", ""))
        name = normalize_text(node.get("name") or node.get("canonical_name") or node_id, 120)

        if node_id:
            node_names[node_id] = name

    return node_names


def summarize_relations(
    edges: list[dict[str, Any]],
    node_names: dict[str, str],
) -> list[dict[str, Any]]:
    relation_by_name: dict[str, dict[str, Any]] = {}

    for edge in edges:
        if not isinstance(edge, dict):
            continue

        relation = normalize_text(edge.get("relation") or "相关", 120)

        if not relation:
            continue

        summary = relation_by_name.setdefault(
            relation,
            {
                "relation": relation,
                "count": 0,
                "examples": [],
            },
        )
        summary["count"] += 1

        if len(summary["examples"]) >= MAX_EXAMPLES_PER_RELATION:
            continue

        source_id = str(edge.get("source", ""))
        target_id = str(edge.get("target", ""))
        summary["examples"].append(
            {
                "source": node_names.get(source_id, source_id),
                "target": node_names.get(target_id, target_id),
                "description": normalize_text(edge.get("description")),
            }
        )

    return sorted(
        relation_by_name.values(),
        key=lambda item: (-int(item["count"]), str(item["relation"])),
    )


def split_relation_batches(relations: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    return [
        relations[index : index + MAX_RELATIONS_PER_BATCH]
        for index in range(0, len(relations), MAX_RELATIONS_PER_BATCH)
    ]


def build_relation_clean_input(relations: list[dict[str, Any]]) -> str:
    return json.dumps({"relations": relations}, ensure_ascii=False, indent=2)


def request_relation_groups(relations: list[dict[str, Any]]) -> dict[str, Any]:
    response_text = chat_json(
        system_prompt=RELATION_CLEAN_PROMPT,
        user_prompt=build_relation_clean_input(relations),
        temperature=0.1,
    )
    result = extract_json_from_text(response_text)

    if not isinstance(result, dict):
        raise ValueError("关系清洗结果必须是 JSON object")

    relation_groups = result.get("relation_groups", [])
    warnings = result.get("warnings", [])

    if not isinstance(relation_groups, list):
        relation_groups = []

    if not isinstance(warnings, list):
        warnings = [str(warnings)]

    return {
        "relation_groups": relation_groups,
        "warnings": [str(warning) for warning in warnings if str(warning).strip()],
    }


def validate_relation_groups(
    raw_groups: list[Any],
    batch_relations: list[dict[str, Any]],
    used_relation_names: set[str],
) -> list[dict[str, Any]]:
    batch_relation_names = {str(item.get("relation", "")) for item in batch_relations}
    groups: list[dict[str, Any]] = []

    for raw_group in raw_groups:
        if not isinstance(raw_group, dict):
            continue

        canonical_relation = normalize_text(raw_group.get("canonical_relation"), 120)
        relation_names = raw_group.get("relation_names", [])

        if not canonical_relation or not isinstance(relation_names, list):
            continue

        cleaned_relation_names: list[str] = []

        for relation_name in relation_names:
            relation_name = str(relation_name)

            if (
                relation_name not in batch_relation_names
                or relation_name in used_relation_names
                or relation_name in cleaned_relation_names
            ):
                continue

            cleaned_relation_names.append(relation_name)

        if len(cleaned_relation_names) < 2 and (
            len(cleaned_relation_names) != 1
            or cleaned_relation_names[0] == canonical_relation
        ):
            continue

        used_relation_names.update(cleaned_relation_names)
        groups.append(
            {
                "canonical_relation": canonical_relation,
                "relation_names": cleaned_relation_names,
                "reason": normalize_text(raw_group.get("reason"), 220),
            }
        )

    return groups


def collect_relation_groups(relation_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    warnings: list[str] = []
    used_relation_names: set[str] = set()

    for batch in split_relation_batches(relation_summaries):
        if len(batch) < 2:
            continue

        try:
            result = request_relation_groups(batch)
        except Exception as error:
            warnings.append(f"关系批次清洗失败：{error}")
            continue

        groups.extend(
            validate_relation_groups(
                raw_groups=result["relation_groups"],
                batch_relations=batch,
                used_relation_names=used_relation_names,
            )
        )
        warnings.extend(result["warnings"])

    return {
        "relation_groups": groups,
        "warnings": warnings,
    }


def build_relation_map(relation_groups: list[dict[str, Any]]) -> dict[str, str]:
    relation_map: dict[str, str] = {}

    for group in relation_groups:
        canonical_relation = group["canonical_relation"]

        for relation_name in group["relation_names"]:
            relation_map[relation_name] = canonical_relation

    return relation_map


def clean_edges(
    edges: list[dict[str, Any]],
    relation_map: dict[str, str],
) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    cleaned_edges: list[dict[str, Any]] = []
    next_edge_index = 1

    for edge in edges:
        if not isinstance(edge, dict):
            continue

        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        relation = normalize_text(edge.get("relation") or "相关", 120)
        relation = relation_map.get(relation, relation)

        if not source or not target or source == target:
            continue

        dedupe_key = (source, target, relation)

        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)
        cleaned_edge = dict(edge)
        cleaned_edge["id"] = f"rce{next_edge_index}"
        cleaned_edge["source"] = source
        cleaned_edge["target"] = target
        cleaned_edge["relation"] = relation
        cleaned_edges.append(cleaned_edge)
        next_edge_index += 1

    return cleaned_edges


def build_relation_type_count(edges: list[dict[str, Any]]) -> dict[str, int]:
    relation_type_count: dict[str, int] = {}

    for edge in edges:
        relation = str(edge.get("relation", "相关") or "相关")
        relation_type_count[relation] = relation_type_count.get(relation, 0) + 1

    return dict(
        sorted(relation_type_count.items(), key=lambda item: item[1], reverse=True)
    )


def update_relation_clean_report(
    payload: dict[str, Any],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> None:
    report = payload.get("report")

    if not isinstance(report, dict):
        payload["report"] = {}
        report = payload["report"]

    report["node_count"] = len(nodes)
    report["edge_count"] = len(edges)
    report["relation_type_count"] = build_relation_type_count(edges)


def clean_merged_graph_relations(extraction_id: str) -> dict[str, Any]:
    merged_graph_json_path = get_merged_graph_json_path(extraction_id)
    merged_graph = read_json(merged_graph_json_path)

    if not isinstance(merged_graph, dict):
        raise ValueError("merged graph 必须是 JSON object")

    nodes = merged_graph.get("nodes", [])
    edges = merged_graph.get("edges", [])

    if not isinstance(nodes, list):
        nodes = []

    if not isinstance(edges, list):
        edges = []

    node_names = build_node_name_map(nodes)
    is_constrained_mode = merged_graph.get("extraction_mode") == "ontology"

    if is_constrained_mode:
        relation_result = {
            "relation_groups": [],
            "warnings": ["本体约束抽取下跳过关系重命名，保留本体草案中的关系名称。"],
        }
    else:
        relation_summaries = summarize_relations(edges, node_names)
        relation_result = collect_relation_groups(relation_summaries)

    relation_groups = relation_result["relation_groups"]
    relation_map = build_relation_map(relation_groups)
    cleaned_edges = clean_edges(edges, relation_map)
    relation_cleaned_graph = dict(merged_graph)
    relation_cleaned_graph["nodes"] = nodes
    relation_cleaned_graph["edges"] = cleaned_edges
    update_relation_clean_report(relation_cleaned_graph, nodes, cleaned_edges)
    relation_cleaned_graph["relation_cleaning"] = {
        "source_merged_graph_path": str(merged_graph_json_path),
        "relation_groups": relation_groups,
        "relation_map": relation_map,
        "warnings": relation_result["warnings"],
        "renamed_relation_count": sum(
            1
            for old_relation, new_relation in relation_map.items()
            if old_relation != new_relation
        ),
        "removed_edge_count": len(edges) - len(cleaned_edges),
        "next_stage": "final_graph",
    }
    relation_cleaned_graph["next_stage"] = "final_graph"

    relation_cleaned_graph_json_path = get_relation_cleaned_graph_json_path(extraction_id)
    write_json(relation_cleaned_graph_json_path, relation_cleaned_graph)

    return {
        "success": True,
        "message": "关系清洗完成：已统一近义关系名称并合并重复边",
        "extraction_id": extraction_id,
        "merged_graph_json_path": str(merged_graph_json_path),
        "relation_cleaned_graph_json_path": str(relation_cleaned_graph_json_path),
        "relation_groups": relation_groups,
        "relation_map": relation_map,
        "warnings": relation_result["warnings"],
        "report": relation_cleaned_graph.get("report", {}),
        "next_stage": "final_graph",
    }
