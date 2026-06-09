"""Knowledge graph quality report service."""

from pathlib import Path
from typing import Any

from config import GRAPH_QUALITY_REPORTS_DIR, RELATION_CLEANED_GRAPHS_DIR
from utils.json_utils import read_json, write_json


MAX_PREVIEW_ITEMS = 30


def get_relation_cleaned_graph_json_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return RELATION_CLEANED_GRAPHS_DIR / f"{safe_id}_relation_cleaned_graph.json"


def get_graph_quality_report_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return GRAPH_QUALITY_REPORTS_DIR / f"{safe_id}_quality_report.json"


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def sort_count_map(count_map: dict[str, int]) -> dict[str, int]:
    return dict(sorted(count_map.items(), key=lambda item: item[1], reverse=True))


def count_node_types(nodes: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}

    for node in nodes:
        node_type = normalize_text(node.get("type") or "其他")
        counts[node_type] = counts.get(node_type, 0) + 1

    return sort_count_map(counts)


def count_relations(edges: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}

    for edge in edges:
        relation = normalize_text(edge.get("relation") or "相关")
        counts[relation] = counts.get(relation, 0) + 1

    return sort_count_map(counts)


def count_sources(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    node_source_chunks = {
        normalize_text(node.get("source_chunk_id"))
        for node in nodes
        if normalize_text(node.get("source_chunk_id"))
    }
    edge_source_chunks = {
        normalize_text(edge.get("source_chunk_id"))
        for edge in edges
        if normalize_text(edge.get("source_chunk_id"))
    }

    return {
        "node_source_chunk_count": len(node_source_chunks),
        "edge_source_chunk_count": len(edge_source_chunks),
    }


def find_duplicate_node_names(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[str]] = {}

    for node in nodes:
        name = normalize_text(node.get("canonical_name") or node.get("name"))
        node_type = normalize_text(node.get("type") or "其他")
        node_id = normalize_text(node.get("id"))

        if not name or not node_id:
            continue

        grouped.setdefault((name, node_type), []).append(node_id)

    duplicates = [
        {
            "name": name,
            "type": node_type,
            "node_ids": node_ids,
            "count": len(node_ids),
        }
        for (name, node_type), node_ids in grouped.items()
        if len(node_ids) > 1
    ]

    return sorted(duplicates, key=lambda item: item["count"], reverse=True)[:MAX_PREVIEW_ITEMS]


def analyze_edges(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    node_ids = {normalize_text(node.get("id")) for node in nodes if normalize_text(node.get("id"))}
    connected_node_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()
    invalid_edges: list[dict[str, Any]] = []
    self_loop_edges: list[dict[str, Any]] = []
    duplicate_edges: list[dict[str, Any]] = []
    missing_relation_edges: list[dict[str, Any]] = []

    for edge in edges:
        edge_id = normalize_text(edge.get("id"))
        source = normalize_text(edge.get("source"))
        target = normalize_text(edge.get("target"))
        relation = normalize_text(edge.get("relation"))

        if not relation:
            missing_relation_edges.append({"id": edge_id, "source": source, "target": target})

        if source not in node_ids or target not in node_ids:
            invalid_edges.append(
                {
                    "id": edge_id,
                    "source": source,
                    "target": target,
                    "relation": relation,
                    "missing_source": source not in node_ids,
                    "missing_target": target not in node_ids,
                }
            )
            continue

        connected_node_ids.update([source, target])

        if source == target:
            self_loop_edges.append({"id": edge_id, "node": source, "relation": relation})
            continue

        edge_key = (source, target, relation)

        if edge_key in seen_edges:
            duplicate_edges.append(
                {
                    "id": edge_id,
                    "source": source,
                    "target": target,
                    "relation": relation,
                }
            )
            continue

        seen_edges.add(edge_key)

    isolated_node_ids = sorted(node_ids - connected_node_ids)

    return {
        "invalid_edge_count": len(invalid_edges),
        "self_loop_edge_count": len(self_loop_edges),
        "duplicate_edge_count": len(duplicate_edges),
        "missing_relation_edge_count": len(missing_relation_edges),
        "isolated_node_count": len(isolated_node_ids),
        "connected_node_count": len(connected_node_ids),
        "invalid_edges_preview": invalid_edges[:MAX_PREVIEW_ITEMS],
        "self_loop_edges_preview": self_loop_edges[:MAX_PREVIEW_ITEMS],
        "duplicate_edges_preview": duplicate_edges[:MAX_PREVIEW_ITEMS],
        "missing_relation_edges_preview": missing_relation_edges[:MAX_PREVIEW_ITEMS],
        "isolated_node_ids_preview": isolated_node_ids[:MAX_PREVIEW_ITEMS],
    }


def find_sparse_or_vague_items(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    vague_names = {"相关", "其他", "问题", "内容", "情况", "方面", "对象", "概念"}
    vague_nodes: list[dict[str, Any]] = []
    vague_edges: list[dict[str, Any]] = []
    missing_description_nodes = 0
    missing_evidence_nodes = 0

    for node in nodes:
        node_id = normalize_text(node.get("id"))
        name = normalize_text(node.get("name"))
        node_type = normalize_text(node.get("type"))

        if not normalize_text(node.get("description")):
            missing_description_nodes += 1

        if not normalize_text(node.get("evidence")):
            missing_evidence_nodes += 1

        if name in vague_names or node_type in vague_names:
            vague_nodes.append({"id": node_id, "name": name, "type": node_type})

    for edge in edges:
        relation = normalize_text(edge.get("relation"))

        if relation in vague_names:
            vague_edges.append(
                {
                    "id": normalize_text(edge.get("id")),
                    "source": normalize_text(edge.get("source")),
                    "target": normalize_text(edge.get("target")),
                    "relation": relation,
                }
            )

    return {
        "missing_description_node_count": missing_description_nodes,
        "missing_evidence_node_count": missing_evidence_nodes,
        "vague_node_count": len(vague_nodes),
        "vague_edge_count": len(vague_edges),
        "vague_nodes_preview": vague_nodes[:MAX_PREVIEW_ITEMS],
        "vague_edges_preview": vague_edges[:MAX_PREVIEW_ITEMS],
    }


def summarize_cleaning_steps(graph: dict[str, Any]) -> dict[str, Any]:
    exact_cleaning = graph.get("cleaning", {})
    semantic_merge = graph.get("semantic_merge", {})
    relation_cleaning = graph.get("relation_cleaning", {})

    return {
        "exact_value_dedupe": {
            "removed_duplicate_values": exact_cleaning.get("stats", {}).get(
                "removed_duplicate_values",
                0,
            )
            if isinstance(exact_cleaning, dict)
            else 0,
            "deduped_key_count": len(
                exact_cleaning.get("stats", {}).get("deduped_keys", [])
            )
            if isinstance(exact_cleaning, dict)
            else 0,
        },
        "semantic_node_merge": {
            "merge_group_count": len(semantic_merge.get("merge_groups", []))
            if isinstance(semantic_merge, dict)
            else 0,
            "merged_node_count": semantic_merge.get("merged_node_count", 0)
            if isinstance(semantic_merge, dict)
            else 0,
            "warning_count": len(semantic_merge.get("warnings", []))
            if isinstance(semantic_merge, dict)
            else 0,
        },
        "relation_cleaning": {
            "relation_group_count": len(relation_cleaning.get("relation_groups", []))
            if isinstance(relation_cleaning, dict)
            else 0,
            "renamed_relation_count": relation_cleaning.get("renamed_relation_count", 0)
            if isinstance(relation_cleaning, dict)
            else 0,
            "removed_edge_count": relation_cleaning.get("removed_edge_count", 0)
            if isinstance(relation_cleaning, dict)
            else 0,
            "warning_count": len(relation_cleaning.get("warnings", []))
            if isinstance(relation_cleaning, dict)
            else 0,
        },
    }


def calculate_quality_score(
    node_count: int,
    edge_count: int,
    structural_issues: dict[str, Any],
    sparse_items: dict[str, Any],
) -> dict[str, Any]:
    score = 100
    deductions: list[dict[str, Any]] = []

    rules = [
        ("invalid_edge_count", 8, "存在指向不存在节点的边"),
        ("self_loop_edge_count", 4, "存在自环边"),
        ("duplicate_edge_count", 3, "存在重复边"),
        ("missing_relation_edge_count", 2, "存在关系名称缺失的边"),
    ]

    for key, weight, reason in rules:
        count = int(structural_issues.get(key, 0))

        if count:
            penalty = min(30, count * weight)
            score -= penalty
            deductions.append({"reason": reason, "count": count, "penalty": penalty})

    isolated_count = int(structural_issues.get("isolated_node_count", 0))

    if node_count:
        isolated_ratio = isolated_count / node_count
        isolated_penalty = int(min(20, isolated_ratio * 40))

        if isolated_penalty:
            score -= isolated_penalty
            deductions.append(
                {
                    "reason": "孤立节点占比较高",
                    "count": isolated_count,
                    "penalty": isolated_penalty,
                }
            )

    vague_edge_count = int(sparse_items.get("vague_edge_count", 0))

    if vague_edge_count:
        penalty = min(10, vague_edge_count * 2)
        score -= penalty
        deductions.append({"reason": "存在宽泛关系", "count": vague_edge_count, "penalty": penalty})

    if node_count and edge_count == 0:
        score -= 30
        deductions.append({"reason": "图谱没有关系边", "count": 1, "penalty": 30})

    score = max(0, min(100, score))

    if score >= 85:
        level = "good"
    elif score >= 65:
        level = "review"
    else:
        level = "poor"

    return {
        "score": score,
        "level": level,
        "deductions": deductions,
    }


def build_recommendations(
    structural_issues: dict[str, Any],
    sparse_items: dict[str, Any],
    distributions: dict[str, Any],
) -> list[str]:
    recommendations: list[str] = []

    if structural_issues["invalid_edge_count"]:
        recommendations.append("先删除或修复 source/target 指向不存在节点的边。")

    if structural_issues["self_loop_edge_count"]:
        recommendations.append("检查自环边是否有业务含义；无明确含义时建议删除。")

    if structural_issues["duplicate_edge_count"]:
        recommendations.append("继续执行边去重，按 source、target、relation 合并重复边。")

    if structural_issues["isolated_node_count"]:
        recommendations.append("人工复核孤立节点：重要概念可保留，泛化或噪声节点建议删除。")

    if sparse_items["vague_edge_count"]:
        recommendations.append("进一步清洗“相关”等宽泛关系，尽量替换为更明确的关系。")

    if len(distributions["relation_type_count"]) > 30:
        recommendations.append("关系类型数量偏多，建议继续做关系归一化。")

    if not recommendations:
        recommendations.append("当前图谱结构质量较稳定，可以进入最终导出或可视化阶段。")

    return recommendations


def generate_graph_quality_report(extraction_id: str) -> dict[str, Any]:
    graph_json_path = get_relation_cleaned_graph_json_path(extraction_id)
    graph = read_json(graph_json_path)

    if not isinstance(graph, dict):
        raise ValueError("relation cleaned graph 必须是 JSON object")

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    if not isinstance(nodes, list):
        nodes = []

    if not isinstance(edges, list):
        edges = []

    distributions = {
        "entity_type_count": count_node_types(nodes),
        "relation_type_count": count_relations(edges),
        **count_sources(nodes, edges),
    }
    structural_issues = analyze_edges(nodes, edges)
    sparse_items = find_sparse_or_vague_items(nodes, edges)
    duplicate_nodes = find_duplicate_node_names(nodes)
    cleaning_summary = summarize_cleaning_steps(graph)
    quality = calculate_quality_score(
        node_count=len(nodes),
        edge_count=len(edges),
        structural_issues=structural_issues,
        sparse_items=sparse_items,
    )
    recommendations = build_recommendations(
        structural_issues=structural_issues,
        sparse_items=sparse_items,
        distributions=distributions,
    )
    report = {
        "success": True,
        "extraction_id": extraction_id,
        "source_graph_path": str(graph_json_path),
        "overview": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "entity_type_count": len(distributions["entity_type_count"]),
            "relation_type_count": len(distributions["relation_type_count"]),
        },
        "quality": quality,
        "distributions": distributions,
        "structural_issues": structural_issues,
        "content_issues": {
            **sparse_items,
            "duplicate_node_name_count": len(duplicate_nodes),
            "duplicate_node_names_preview": duplicate_nodes,
        },
        "cleaning_summary": cleaning_summary,
        "recommendations": recommendations,
        "next_stage": "final_graph_export",
    }

    report_path = get_graph_quality_report_path(extraction_id)
    write_json(report_path, report)

    return {
        **report,
        "message": "图谱质量报告已生成",
        "quality_report_path": str(report_path),
    }
