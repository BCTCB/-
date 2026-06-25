"""Workflow agent service for generating reusable workflow plans."""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

from schemas.agent_schema import MasterAgentChatRequest, WorkflowPlan, WorkflowStep
from services.llm_service import chat_json
from utils.json_utils import extract_json_from_text


WORKFLOW_AGENT_SYSTEM_PROMPT = """
你是 Workflow Agent，负责把用户在知识图谱项目工作台中的明确意图转换成后续可执行的 workflow。

输出要求：
1. 只输出 JSON 对象，不要输出 Markdown。
2. JSON 字段必须包含：title、intent、summary、steps、start_question。
3. steps 是数组，每一步包含 id、title、description、required_inputs、expected_outputs。
4. 流程要具体、可审核、适合后续由主控 Agent 或后端流水线执行。
5. 不要声称已经开始执行流程；当前只生成 workflow 展示给用户确认。
""".strip()


FEATURE_LABELS = {
    "knowledge-graph": "知识图谱抽取",
    "document-qa": "文档问答",
    "summary": "文档摘要",
    "report": "报告生成",
    "entity-review": "实体审核",
    "relationship-review": "关系审核",
}

CLEAR_INTENT_KEYWORDS = (
    "生成",
    "抽取",
    "开始",
    "运行",
    "执行",
    "创建",
    "构建",
    "整理",
    "分析",
    "审核",
    "校对",
    "总结",
    "摘要",
    "报告",
    "问答",
    "知识图谱",
    "实体",
    "关系",
    "workflow",
    "工作流",
    "流程",
)

INTENT_CONFIRMATION_MARKER = "确认后，我再生成 workflow"

CONFIRMATION_REPLIES = {
    "确认",
    "确认无误",
    "没问题",
    "没有问题",
    "理解正确",
    "理解准确",
    "准确",
    "是的",
    "对",
    "对的",
    "可以",
    "同意",
    "继续",
    "生成吧",
    "请生成",
    "开始生成",
}

KNOWLEDGE_GRAPH_WORKFLOW_STEPS = (
    {
        "id": "pdf_to_text",
        "title": "文本提取",
        "description": "上传 PDF，提取全文并保存为后续流程使用的 TXT。",
        "required_inputs": ["file"],
        "expected_outputs": ["txt_path"],
    },
    {
        "id": "ontology_draft",
        "title": "本体草案生成",
        "description": "根据文档摘要和建图目标生成实体类型、关系类型和关系约束。",
        "required_inputs": ["extraction_id", "document_summary", "user_goal"],
        "expected_outputs": ["ontology_path"],
    },
    {
        "id": "split_strategy",
        "title": "切分策略选择",
        "description": "分析文本结构，选择适合知识图谱抽取的切分策略。",
        "required_inputs": ["extraction_id"],
        "expected_outputs": ["strategy_path"],
    },
    {
        "id": "chunking",
        "title": "执行切分",
        "description": "按切分策略生成 chunks，并输出 chunk 质量检查结果。",
        "required_inputs": ["extraction_id"],
        "expected_outputs": ["chunks_json_path"],
    },
    {
        "id": "graph_extraction",
        "title": "本体实例化",
        "description": "基于 chunks 和本体约束抽取实体、关系，生成原始图谱。",
        "required_inputs": ["extraction_id"],
        "expected_outputs": ["raw_graph_json_path"],
    },
    {
        "id": "exact_cleaning",
        "title": "重复内容清理",
        "description": "清理完全重复的节点和边，生成去重后的图谱。",
        "required_inputs": ["extraction_id"],
        "expected_outputs": ["cleaned_graph_json_path"],
    },
    {
        "id": "semantic_node_merge",
        "title": "相近节点合并",
        "description": "识别语义相近节点并进行归并，减少概念重复。",
        "required_inputs": ["extraction_id"],
        "expected_outputs": ["merged_graph_json_path"],
    },
    {
        "id": "relation_cleaning",
        "title": "关系清洗",
        "description": "规范关系命名并清理低质量关系。",
        "required_inputs": ["extraction_id"],
        "expected_outputs": ["relation_cleaned_graph_json_path"],
    },
    {
        "id": "quality_report",
        "title": "质量报告",
        "description": "统计图谱质量指标，输出可审核的质量报告。",
        "required_inputs": ["extraction_id"],
        "expected_outputs": ["quality_report_path"],
    },
    {
        "id": "final_graph",
        "title": "最终图谱生成",
        "description": "结合清洗后图谱和质量报告，生成最终展示用知识图谱。",
        "required_inputs": ["extraction_id"],
        "expected_outputs": ["final_graph_json_path"],
    },
)


def is_clear_workflow_intent(request: MasterAgentChatRequest) -> bool:
    if request.selected_feature:
        return True

    normalized = " ".join(request.message.split()).lower()
    if len(normalized) < 2:
        return False

    return any(keyword.lower() in normalized for keyword in CLEAR_INTENT_KEYWORDS)


def is_workflow_intent_confirmed(request: MasterAgentChatRequest) -> bool:
    """Only accept an explicit reply to the most recent confirmation request."""
    if not request.history:
        return False

    last_message = request.history[-1]
    if last_message.role.strip().lower() != "assistant":
        return False
    if INTENT_CONFIRMATION_MARKER not in last_message.content:
        return False

    normalized = re.sub(r"[\s，。！？、,.!?]+", "", request.message).lower()
    normalized_replies = {
        re.sub(r"[\s，。！？、,.!?]+", "", reply).lower()
        for reply in CONFIRMATION_REPLIES
    }
    if normalized in normalized_replies:
        return True

    return bool(
        re.fullmatch(
            r"(?:好的?)?(?:确认(?:无误)?|同意|没(?:有)?问题|理解(?:正确|准确))"
            r"(?:了)?(?:请)?(?:生成|开始生成|继续生成)?(?:workflow|工作流|流程)?(?:吧)?",
            normalized,
        )
    )


def request_with_confirmed_intent(request: MasterAgentChatRequest) -> MasterAgentChatRequest:
    """Restore the intent that preceded the confirmation reply for workflow generation."""
    confirmed_intent = ""
    for message in reversed(request.history[:-1]):
        if message.role.strip().lower() == "user" and message.content.strip():
            confirmed_intent = message.content.strip()
            break

    if not confirmed_intent:
        confirmed_intent = request.user_goal or get_selected_feature_label(request.selected_feature)
    if not confirmed_intent:
        confirmed_intent = request.message

    update = {"message": confirmed_intent}
    if hasattr(request, "model_copy"):
        return request.model_copy(update=update)
    return request.copy(update=update)


def generate_workflow(request: MasterAgentChatRequest) -> WorkflowPlan:
    prompt = build_workflow_prompt(request)

    try:
        response_text = chat_json(
            system_prompt=WORKFLOW_AGENT_SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=0.2,
        )
        payload = extract_json_from_text(response_text)
        return normalize_workflow(payload, request)
    except Exception:
        return build_fallback_workflow(request)


def build_workflow_prompt(request: MasterAgentChatRequest) -> str:
    selected_feature = get_selected_feature_label(request.selected_feature)
    context = {
        "user_message": request.message,
        "selected_feature": selected_feature,
        "project_id": request.project_id,
        "extraction_id": request.extraction_id,
        "document_summary": request.document_summary,
        "document_text_preview": request.document_text_preview,
        "user_goal": request.user_goal,
        "available_knowledge_graph_pipeline": list(KNOWLEDGE_GRAPH_WORKFLOW_STEPS),
    }

    return json.dumps(context, ensure_ascii=False, indent=2)


def normalize_workflow(payload: dict[str, Any], request: MasterAgentChatRequest) -> WorkflowPlan:
    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        return build_fallback_workflow(request)

    normalized_steps = []
    for index, raw_step in enumerate(steps, start=1):
        if not isinstance(raw_step, dict):
            continue

        title = str(raw_step.get("title") or f"步骤 {index}").strip()
        description = str(raw_step.get("description") or "完成该阶段处理并产出可审核结果。").strip()
        step_id = sanitize_step_id(raw_step.get("id"), index)

        normalized_steps.append(
            WorkflowStep(
                id=step_id,
                title=title,
                description=description,
                required_inputs=normalize_string_list(raw_step.get("required_inputs")),
                expected_outputs=normalize_string_list(raw_step.get("expected_outputs")),
            )
        )

    if not normalized_steps:
        return build_fallback_workflow(request)

    return WorkflowPlan(
        id=f"workflow_{uuid4().hex[:12]}",
        title=str(payload.get("title") or get_default_workflow_title(request)).strip(),
        intent=str(payload.get("intent") or request.message).strip(),
        summary=str(payload.get("summary") or "已根据当前意图生成 workflow，等待用户确认是否开始。").strip(),
        steps=normalized_steps,
        start_question=str(payload.get("start_question") or "是否开始这个流程？").strip(),
    )


def build_fallback_workflow(request: MasterAgentChatRequest) -> WorkflowPlan:
    feature_label = get_selected_feature_label(request.selected_feature)
    if request.selected_feature == "knowledge-graph" or "知识图谱" in request.message or "抽取" in request.message:
        steps = [
            WorkflowStep(
                id=step["id"],
                title=step["title"],
                description=step["description"],
                required_inputs=step["required_inputs"],
                expected_outputs=step["expected_outputs"],
            )
            for step in KNOWLEDGE_GRAPH_WORKFLOW_STEPS
        ]
    else:
        steps = [
            WorkflowStep(
                id="clarify_scope",
                title="确认目标与输入",
                description="确认用户要处理的文件、目标范围和期望产出。",
                required_inputs=["用户目标", "项目文件或已有结果"],
                expected_outputs=["流程范围说明"],
            ),
            WorkflowStep(
                id="process_content",
                title=feature_label or "执行核心处理",
                description="按照确认后的目标处理项目内容，生成初版结果。",
                required_inputs=["流程范围说明"],
                expected_outputs=["初版结果"],
            ),
            WorkflowStep(
                id="review_result",
                title="审核与确认",
                description="展示处理结果，等待用户审核并决定是否继续调整。",
                required_inputs=["初版结果"],
                expected_outputs=["用户确认后的结果"],
            ),
        ]

    return WorkflowPlan(
        id=f"workflow_{uuid4().hex[:12]}",
        title=get_default_workflow_title(request),
        intent=request.message.strip() or feature_label or "用户选择的功能",
        summary="已根据当前明确意图生成 workflow，当前仅展示流程并等待确认。",
        steps=steps,
        start_question="是否开始这个流程？",
    )


def get_default_workflow_title(request: MasterAgentChatRequest) -> str:
    feature_label = get_selected_feature_label(request.selected_feature)
    if feature_label:
        return f"{feature_label} workflow"
    return "项目处理 workflow"


def get_selected_feature_label(selected_feature: str | None) -> str:
    if not selected_feature:
        return ""
    return FEATURE_LABELS.get(selected_feature, selected_feature)


def normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def sanitize_step_id(value: Any, index: int) -> str:
    raw = str(value or f"step_{index}").strip().lower()
    normalized = re.sub(r"[^a-z0-9_\-]+", "_", raw).strip("_")
    return normalized or f"step_{index}"
