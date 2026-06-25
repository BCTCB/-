"""Final knowledge graph generation service."""

from pathlib import Path
from typing import Any

from config import FINAL_GRAPHS_DIR, GRAPH_QUALITY_REPORTS_DIR, RELATION_CLEANED_GRAPHS_DIR
from services.result_retention_service import cleanup_old_intermediate_results
from utils.json_utils import read_json, write_json


def get_relation_cleaned_graph_json_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return RELATION_CLEANED_GRAPHS_DIR / f"{safe_id}_relation_cleaned_graph.json"


def get_graph_quality_report_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return GRAPH_QUALITY_REPORTS_DIR / f"{safe_id}_quality_report.json"


def get_final_graph_json_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return FINAL_GRAPHS_DIR / f"{safe_id}_final_graph.json"


def normalize_text(value: Any, max_chars: int = 240) -> str:
    return str(value or "").strip()[:max_chars]


def build_node_degree_map(edges: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    degree_map: dict[str, dict[str, int]] = {}

    for edge in edges:
        source = normalize_text(edge.get("source"))
        target = normalize_text(edge.get("target"))

        if not source or not target:
            continue

        source_degree = degree_map.setdefault(source, {"in": 0, "out": 0, "total": 0})
        target_degree = degree_map.setdefault(target, {"in": 0, "out": 0, "total": 0})
        source_degree["out"] += 1
        source_degree["total"] += 1
        target_degree["in"] += 1
        target_degree["total"] += 1

    return degree_map


def build_final_nodes(nodes: list[dict[str, Any]], degree_map: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
    final_nodes: list[dict[str, Any]] = []
    seen_node_ids: set[str] = set()

    for node in nodes:
        if not isinstance(node, dict):
            continue

        node_id = normalize_text(node.get("id"))

        if not node_id or node_id in seen_node_ids:
            continue

        label = normalize_text(node.get("name") or node.get("canonical_name") or node_id, 120)
        node_type = normalize_text(node.get("type") or "其他", 80)
        seen_node_ids.add(node_id)
        final_nodes.append(
            {
                "id": node_id,
                "label": label,
                "type": node_type,
                "title": normalize_text(node.get("description") or label),
                "aliases": node.get("aliases", []) if isinstance(node.get("aliases"), list) else [],
                "degree": degree_map.get(node_id, {"in": 0, "out": 0, "total": 0}),
                "source_chunk_id": normalize_text(node.get("source_chunk_id")),
                "source_part_id": normalize_text(node.get("source_part_id")),
                "evidence": normalize_text(node.get("evidence")),
            }
        )

    return final_nodes


def build_final_edges(
    edges: list[dict[str, Any]],
    valid_node_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    final_edges: list[dict[str, Any]] = []
    skipped_edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    next_edge_index = 1

    for edge in edges:
        if not isinstance(edge, dict):
            continue

        source = normalize_text(edge.get("source"))
        target = normalize_text(edge.get("target"))
        relation = normalize_text(edge.get("relation") or "相关", 120)

        if source not in valid_node_ids or target not in valid_node_ids or source == target:
            skipped_edges.append(
                {
                    "id": normalize_text(edge.get("id")),
                    "source": source,
                    "target": target,
                    "relation": relation,
                    "reason": "invalid_endpoint_or_self_loop",
                }
            )
            continue

        edge_key = (source, target, relation)

        if edge_key in seen_edges:
            skipped_edges.append(
                {
                    "id": normalize_text(edge.get("id")),
                    "source": source,
                    "target": target,
                    "relation": relation,
                    "reason": "duplicate_edge",
                }
            )
            continue

        seen_edges.add(edge_key)
        final_edges.append(
            {
                "id": f"fe{next_edge_index}",
                "from": source,
                "to": target,
                "label": relation,
                "relation": relation,
                "title": normalize_text(edge.get("description") or relation),
                "source_chunk_id": normalize_text(edge.get("source_chunk_id")),
                "source_part_id": normalize_text(edge.get("source_part_id")),
                "evidence": normalize_text(edge.get("evidence")),
            }
        )
        next_edge_index += 1

    return final_edges, skipped_edges


def build_final_report(
    source_graph: dict[str, Any],
    final_nodes: list[dict[str, Any]],
    final_edges: list[dict[str, Any]],
    skipped_edges: list[dict[str, Any]],
) -> dict[str, Any]:
    node_type_count: dict[str, int] = {}
    relation_type_count: dict[str, int] = {}

    for node in final_nodes:
        node_type = node["type"]
        node_type_count[node_type] = node_type_count.get(node_type, 0) + 1

    for edge in final_edges:
        relation = edge["relation"]
        relation_type_count[relation] = relation_type_count.get(relation, 0) + 1

    return {
        "node_count": len(final_nodes),
        "edge_count": len(final_edges),
        "skipped_edge_count": len(skipped_edges),
        "entity_type_count": dict(
            sorted(node_type_count.items(), key=lambda item: item[1], reverse=True)
        ),
        "relation_type_count": dict(
            sorted(relation_type_count.items(), key=lambda item: item[1], reverse=True)
        ),
        "source_report": source_graph.get("report", {}),
    }


def load_quality_report(extraction_id: str) -> dict[str, Any]:
    quality_report_path = get_graph_quality_report_path(extraction_id)

    if not quality_report_path.exists():
        return {}

    quality_report = read_json(quality_report_path)
    return quality_report if isinstance(quality_report, dict) else {}


def generate_final_knowledge_graph(extraction_id: str) -> dict[str, Any]:
    source_graph_path = get_relation_cleaned_graph_json_path(extraction_id)
    source_graph = read_json(source_graph_path)

    if not isinstance(source_graph, dict):
        raise ValueError("relation cleaned graph 必须是 JSON object")

    nodes = source_graph.get("nodes", [])
    edges = source_graph.get("edges", [])

    if not isinstance(nodes, list):
        nodes = []

    if not isinstance(edges, list):
        edges = []

    final_nodes = build_final_nodes(nodes, {})
    valid_node_ids = {node["id"] for node in final_nodes}
    final_edges, skipped_edges = build_final_edges(edges, valid_node_ids)
    degree_map = build_node_degree_map(
        [{"source": edge["from"], "target": edge["to"]} for edge in final_edges]
    )
    final_nodes = build_final_nodes(nodes, degree_map)
    quality_report = load_quality_report(extraction_id)
    final_report = build_final_report(source_graph, final_nodes, final_edges, skipped_edges)
    final_graph = {
        "success": True,
        "extraction_id": extraction_id,
        "source_graph_path": str(source_graph_path),
        "quality_report_path": str(get_graph_quality_report_path(extraction_id))
        if quality_report
        else "",
        "report": final_report,
        "quality": quality_report.get("quality", {}),
        "nodes": final_nodes,
        "edges": final_edges,
        "skipped_edges": skipped_edges[:50],
        "metadata": {
            "format": "antv-g6-adapted",
            "node_fields": ["id", "label", "type"],
            "edge_fields": ["from", "to", "label"],
            "next_stage": "visualization",
        },
        "next_stage": "visualization",
    }

    final_graph_path = get_final_graph_json_path(extraction_id)
    write_json(final_graph_path, final_graph)
    cleanup_result = cleanup_old_intermediate_results(extraction_id)

    return {
        **final_graph,
        "message": "最终知识图谱已生成",
        "final_graph_json_path": str(final_graph_path),
        "cleanup_result": cleanup_result,
    }
