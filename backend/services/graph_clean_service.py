"""Knowledge graph cleaning service."""

import json
from pathlib import Path
from typing import Any

from config import CLEANED_GRAPHS_DIR, RAW_GRAPHS_DIR
from utils.json_utils import read_json, write_json


def get_raw_graph_json_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return RAW_GRAPHS_DIR / f"{safe_id}_raw_graph.json"


def get_cleaned_graph_json_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return CLEANED_GRAPHS_DIR / f"{safe_id}_cleaned_graph.json"


def build_exact_value_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def dedupe_exact_values(values: list[Any]) -> tuple[list[Any], int]:
    seen: set[str] = set()
    deduped: list[Any] = []
    removed_count = 0

    for value in values:
        exact_key = build_exact_value_key(value)

        if exact_key in seen:
            removed_count += 1
            continue

        seen.add(exact_key)
        deduped.append(value)

    return deduped, removed_count


def clean_same_key_exact_values(
    data: Any,
    stats: dict[str, Any],
    path: str = "$",
) -> Any:
    if isinstance(data, dict):
        cleaned: dict[str, Any] = {}

        for key, value in data.items():
            child_path = f"{path}.{key}" if path != "$" else key
            cleaned_value = clean_same_key_exact_values(value, stats, child_path)

            if isinstance(cleaned_value, list):
                deduped_value, removed_count = dedupe_exact_values(cleaned_value)

                if removed_count:
                    stats["removed_duplicate_values"] += removed_count
                    stats["deduped_keys"].append(
                        {
                            "key": key,
                            "path": child_path,
                            "before": len(cleaned_value),
                            "after": len(deduped_value),
                            "removed": removed_count,
                        }
                    )

                cleaned_value = deduped_value

            cleaned[key] = cleaned_value

        return cleaned

    if isinstance(data, list):
        return [
            clean_same_key_exact_values(value, stats, f"{path}[{index}]")
            for index, value in enumerate(data)
        ]

    return data


def update_cleaned_report(payload: dict[str, Any]) -> None:
    report = payload.get("report")

    if not isinstance(report, dict):
        return

    nodes = payload.get("nodes", [])
    edges = payload.get("edges", [])

    if isinstance(nodes, list):
        report["node_count"] = len(nodes)

    if isinstance(edges, list):
        report["edge_count"] = len(edges)


def clean_raw_graph_exact_duplicates(extraction_id: str) -> dict[str, Any]:
    raw_graph_json_path = get_raw_graph_json_path(extraction_id)
    raw_graph = read_json(raw_graph_json_path)

    if not isinstance(raw_graph, dict):
        raise ValueError("raw graph 必须是 JSON object")

    stats: dict[str, Any] = {
        "rule": "same_key_exact_value_dedupe",
        "removed_duplicate_values": 0,
        "deduped_keys": [],
    }
    cleaned_graph = clean_same_key_exact_values(raw_graph, stats)

    if not isinstance(cleaned_graph, dict):
        raise ValueError("清洗后的 graph 必须是 JSON object")

    update_cleaned_report(cleaned_graph)
    cleaned_graph["cleaning"] = {
        "source_raw_graph_path": str(raw_graph_json_path),
        "stats": stats,
        "next_stage": "graph_merge",
    }
    cleaned_graph["next_stage"] = "graph_merge"

    cleaned_graph_json_path = get_cleaned_graph_json_path(extraction_id)
    write_json(cleaned_graph_json_path, cleaned_graph)

    return {
        "success": True,
        "message": "图谱清洗完成：已合并同一 key 下完全相同的 value",
        "extraction_id": extraction_id,
        "raw_graph_json_path": str(raw_graph_json_path),
        "cleaned_graph_json_path": str(cleaned_graph_json_path),
        "stats": stats,
        "report": cleaned_graph.get("report", {}),
        "next_stage": "graph_merge",
    }
