"""Workflow execution agent: review gate, skill selection, and execution."""

from __future__ import annotations

import re
from typing import Any

from schemas.agent_schema import WorkflowExecutionRequest, WorkflowStep
from services.ontology_service import load_ontology_draft
from services.pipeline_service import update_pipeline_context
from services.pipeline_skill_service import PIPELINE_SKILLS, KnowledgeExtractionSkill, execute_pipeline_skill


SKILLS_BY_STAGE = {skill.stage: skill for skill in PIPELINE_SKILLS}
SKILLS_BY_KEY = {skill.key: skill for skill in PIPELINE_SKILLS}
SKILL_ORDER = {skill.stage: index for index, skill in enumerate(PIPELINE_SKILLS)}

STAGE_ALIASES = {
    "upload": "pdf_to_text",
    "pdf_text_extraction": "pdf_to_text",
    "ontology": "ontology_draft",
    "ontology_draft_generation": "ontology_draft",
    "strategy": "split_strategy",
    "split_strategy_analysis": "split_strategy",
    "chunk": "chunking",
    "text_chunking": "chunking",
    "extract": "graph_extraction",
    "ontology_instantiation": "graph_extraction",
    "clean": "exact_cleaning",
    "exact_duplicate_cleaning": "exact_cleaning",
    "merge": "semantic_node_merge",
    "relationclean": "relation_cleaning",
    "quality": "quality_report",
    "graph_quality_report": "quality_report",
    "final": "final_graph",
    "final_graph_generation": "final_graph",
}

TITLE_ALIASES = {
    "文本提取": "pdf_to_text",
    "本体草案生成": "ontology_draft",
    "切分策略选择": "split_strategy",
    "执行切分": "chunking",
    "本体实例化": "graph_extraction",
    "重复内容清理": "exact_cleaning",
    "相近节点合并": "semantic_node_merge",
    "关系清洗": "relation_cleaning",
    "质量报告": "quality_report",
    "最终图谱生成": "final_graph",
}


def _normalize_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def select_skill(step: WorkflowStep) -> KnowledgeExtractionSkill:
    """Select a registered skill without allowing the workflow to name arbitrary code."""
    identifier = _normalize_identifier(step.id)
    stage = STAGE_ALIASES.get(identifier, identifier)

    if stage in SKILLS_BY_STAGE:
        return SKILLS_BY_STAGE[stage]
    if identifier in SKILLS_BY_KEY:
        return SKILLS_BY_KEY[identifier]

    title_stage = TITLE_ALIASES.get("".join(step.title.split()))
    if title_stage:
        return SKILLS_BY_STAGE[title_stage]

    raise ValueError(f"步骤「{step.title}」没有可用的 skill，请调整 workflow 后重试")


def select_workflow_skills(steps: list[WorkflowStep]) -> list[tuple[WorkflowStep, KnowledgeExtractionSkill]]:
    if not steps:
        raise ValueError("workflow 中没有可执行步骤")

    selected = [(step, select_skill(step)) for step in steps]
    stages = [skill.stage for _, skill in selected]

    if len(stages) != len(set(stages)):
        raise ValueError("workflow 中存在重复执行步骤")

    order = [SKILL_ORDER[stage] for stage in stages]
    if order != sorted(order):
        raise ValueError("workflow 步骤顺序与 skill 依赖顺序不一致")

    return selected


def _build_context(request: WorkflowExecutionRequest) -> dict[str, Any]:
    context: dict[str, Any] = {
        "project_id": request.project_id,
        "extraction_id": request.extraction_id,
        "document_summary": request.document_summary or "",
        "user_goal": request.user_goal or "",
        "entity_types": request.entity_types,
        "allowed_entity_types": request.entity_types,
        "allowed_relation_types": request.relation_types,
        "relations": request.relations,
    }

    if request.extraction_id:
        ontology_payload = load_ontology_draft(request.extraction_id)
        if ontology_payload:
            update_pipeline_context(context, ontology_payload)

    return context


async def execute_approved_workflow(request: WorkflowExecutionRequest) -> dict[str, Any]:
    if not request.approved:
        raise ValueError("请先审核并确认 workflow，再开始执行")

    selected = select_workflow_skills(request.workflow.steps)
    context = _build_context(request)
    execution_steps: list[dict[str, Any]] = []
    final_result: dict[str, Any] = {}

    for workflow_step, skill in selected:
        if skill.stage == "pdf_to_text" and context.get("extraction_id"):
            result = {
                "success": True,
                "message": "已复用当前项目的文本提取结果",
                "extraction_id": context["extraction_id"],
            }
            status = "reused"
        elif skill.stage == "pdf_to_text":
            raise ValueError("文本提取 skill 需要 PDF，请先在项目中上传文件")
        else:
            result = await execute_pipeline_skill(skill, context)
            status = "completed"

        update_pipeline_context(context, result)
        final_result = result
        execution_steps.append(
            {
                "workflow_step_id": workflow_step.id,
                "stage": skill.stage,
                "skill": skill.key,
                "title": workflow_step.title,
                "status": status,
                "success": bool(result.get("success", True)),
                "message": str(result.get("message") or ""),
                "output_path": str(result.get(skill.output_path_field) or ""),
                "result": result,
            }
        )

    return {
        "success": True,
        "agent": "workflow-executor",
        "message": "Workflow 执行 Agent 已完成全部步骤",
        "workflow_id": request.workflow.id,
        "project_id": request.project_id,
        "extraction_id": context.get("extraction_id"),
        "selected_skills": [skill.key for _, skill in selected],
        "steps": execution_steps,
        "final_result": final_result,
    }
