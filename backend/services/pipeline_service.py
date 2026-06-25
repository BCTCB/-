"""End-to-end extraction pipeline service."""

from typing import Any

from fastapi import UploadFile

from services.pipeline_skill_service import PIPELINE_SKILLS, execute_pipeline_skill


def update_pipeline_context(context: dict[str, Any], result: dict[str, Any]) -> None:
    extraction_id = result.get("extraction_id")

    if extraction_id:
        context["extraction_id"] = extraction_id

    ontology = result.get("ontology")

    if isinstance(ontology, dict):
        context["ontology"] = ontology
        context["allowed_entity_types"] = context.get("allowed_entity_types") or ontology.get(
            "entity_types",
            [],
        )
        context["allowed_relation_types"] = context.get("allowed_relation_types") or ontology.get(
            "relation_types",
            [],
        )
        context["relations"] = context.get("relations") or ontology.get("relations", [])


async def run_pdf_to_final_graph_pipeline(
    file: UploadFile,
    document_summary: str,
    user_goal: str,
    entity_types: list[str] | None = None,
    relations: list[dict[str, Any]] | None = None,
    allowed_entity_types: list[str] | None = None,
    allowed_relation_types: list[str] | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "file": file,
        "document_summary": document_summary,
        "user_goal": user_goal,
        "entity_types": entity_types or [],
        "relations": relations or [],
        "allowed_entity_types": allowed_entity_types or [],
        "allowed_relation_types": allowed_relation_types or [],
    }
    pipeline_steps: list[dict[str, Any]] = []
    final_graph_result: dict[str, Any] = {}

    for skill in PIPELINE_SKILLS:
        result = await execute_pipeline_skill(skill, context)
        update_pipeline_context(context, result)
        pipeline_steps.append(skill.build_step(result))
        final_graph_result = result

    return {
        **final_graph_result,
        "message": "PDF 到最终知识图谱的一键流程已完成",
        "pipeline_steps": pipeline_steps,
    }
