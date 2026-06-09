"""End-to-end extraction pipeline service."""

from typing import Any

from fastapi import UploadFile

from services.chunk_service import analyze_strategy_and_execute_chunking
from services.final_graph_service import generate_final_knowledge_graph
from services.graph_clean_service import clean_raw_graph_exact_duplicates
from services.graph_extract_service import execute_graph_extraction_from_chunks
from services.graph_merge_service import merge_cleaned_graph_semantic_nodes
from services.graph_quality_report_service import generate_graph_quality_report
from services.graph_relation_clean_service import clean_merged_graph_relations
from services.pdf_service import convert_uploaded_pdf_to_txt


def normalize_mode(mode: str | None) -> str:
    return mode if mode in {"auto", "custom"} else "auto"


def collect_relation_types(relations: list[dict[str, Any]] | None) -> list[str]:
    if not isinstance(relations, list):
        return []

    relation_types: list[str] = []
    seen: set[str] = set()

    for relation in relations:
        if not isinstance(relation, dict):
            continue

        relation_name = str(relation.get("relation", "")).strip()

        if not relation_name or relation_name in seen:
            continue

        seen.add(relation_name)
        relation_types.append(relation_name)

    return relation_types


def build_pipeline_steps(
    upload_result: dict[str, Any],
    chunk_result: dict[str, Any],
    extract_result: dict[str, Any],
    exact_clean_result: dict[str, Any],
    node_merge_result: dict[str, Any],
    relation_clean_result: dict[str, Any],
    quality_report_result: dict[str, Any],
    final_graph_result: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            "stage": "pdf_to_text",
            "success": bool(upload_result.get("success")),
            "message": upload_result.get("message", ""),
            "output_path": upload_result.get("txt_path", ""),
        },
        {
            "stage": "chunking",
            "success": bool(chunk_result.get("success")),
            "message": chunk_result.get("message", ""),
            "output_path": chunk_result.get("chunks_json_path", ""),
        },
        {
            "stage": "graph_extraction",
            "success": bool(extract_result.get("success")),
            "message": extract_result.get("message", ""),
            "output_path": extract_result.get("raw_graph_json_path", ""),
        },
        {
            "stage": "exact_cleaning",
            "success": bool(exact_clean_result.get("success")),
            "message": exact_clean_result.get("message", ""),
            "output_path": exact_clean_result.get("cleaned_graph_json_path", ""),
        },
        {
            "stage": "semantic_node_merge",
            "success": bool(node_merge_result.get("success")),
            "message": node_merge_result.get("message", ""),
            "output_path": node_merge_result.get("merged_graph_json_path", ""),
        },
        {
            "stage": "relation_cleaning",
            "success": bool(relation_clean_result.get("success")),
            "message": relation_clean_result.get("message", ""),
            "output_path": relation_clean_result.get("relation_cleaned_graph_json_path", ""),
        },
        {
            "stage": "quality_report",
            "success": bool(quality_report_result.get("success")),
            "message": quality_report_result.get("message", ""),
            "output_path": quality_report_result.get("quality_report_path", ""),
        },
        {
            "stage": "final_graph",
            "success": bool(final_graph_result.get("success")),
            "message": final_graph_result.get("message", ""),
            "output_path": final_graph_result.get("final_graph_json_path", ""),
        },
    ]


async def run_pdf_to_final_graph_pipeline(
    file: UploadFile,
    mode: str = "auto",
    entity_types: list[str] | None = None,
    relations: list[dict[str, Any]] | None = None,
    allowed_entity_types: list[str] | None = None,
    allowed_relation_types: list[str] | None = None,
) -> dict[str, Any]:
    mode = normalize_mode(mode)
    entity_types = entity_types or []
    relations = relations or []

    if mode == "custom":
        allowed_entity_types = allowed_entity_types or entity_types
        allowed_relation_types = allowed_relation_types or collect_relation_types(relations)
    else:
        allowed_entity_types = []
        allowed_relation_types = []

    upload_result = await convert_uploaded_pdf_to_txt(
        file=file,
        entity_types=entity_types,
        relations=relations,
    )
    extraction_id = upload_result["extraction_id"]
    chunk_result = analyze_strategy_and_execute_chunking(extraction_id)
    extract_result = execute_graph_extraction_from_chunks(
        extraction_id=extraction_id,
        mode=mode,
        allowed_entity_types=allowed_entity_types,
        allowed_relation_types=allowed_relation_types,
    )
    exact_clean_result = clean_raw_graph_exact_duplicates(extraction_id)
    node_merge_result = merge_cleaned_graph_semantic_nodes(extraction_id)
    relation_clean_result = clean_merged_graph_relations(extraction_id)
    quality_report_result = generate_graph_quality_report(extraction_id)
    final_graph_result = generate_final_knowledge_graph(extraction_id)
    pipeline_steps = build_pipeline_steps(
        upload_result=upload_result,
        chunk_result=chunk_result,
        extract_result=extract_result,
        exact_clean_result=exact_clean_result,
        node_merge_result=node_merge_result,
        relation_clean_result=relation_clean_result,
        quality_report_result=quality_report_result,
        final_graph_result=final_graph_result,
    )

    return {
        **final_graph_result,
        "message": "PDF 到最终知识图谱的一键流程已完成",
        "pipeline_steps": pipeline_steps,
    }
