"""Master agent conversation service."""

import re
from typing import Any

from config import EXTRACTED_TEXT_DIR
from schemas.agent_schema import AgentChatMessage, MasterAgentChatRequest
from services.llm_service import chat_text
from services.workflow_context_service import generate_workflow_context
from services.workflow_agent_service import (
    generate_workflow,
    is_clear_workflow_intent,
    is_workflow_intent_confirmed,
    request_with_confirmed_intent,
)


MASTER_AGENT_SYSTEM_PROMPT = """
你是项目主页面中的主控 Agent，负责和用户围绕当前知识图谱项目进行自然对话。

当前职责边界：
1. 负责对话、澄清需求、解释项目状态和帮助用户组织下一步想法。
2. 每次对话都要评估用户意图是否明确。
3. 如果用户意图明确，先向用户复述当前需求和预期结果，并请求确认；只有用户明确确认后，才调用 Workflow Agent 生成 workflow。
4. 回答要简洁、友好、面向项目工作台语境。
5. 不要编造已经执行过的动作，也不要声称流程已经开始执行。
""".strip()


INTENT_CONFIRMATION_SYSTEM_PROMPT = """
你是项目主页面中的主控 Agent。用户已经表达了较明确的工作意图，但此时禁止生成 workflow。

请用简洁、自然的中文向用户说明：
1. 你理解的当前需求是什么；
2. 完成后用户将得到什么结果；
3. 如有关键输入缺失，可以一并点明，但不要展开成执行步骤。

不要输出 workflow、步骤列表或声称已经开始执行。不要替用户做确认。
""".strip()


INTENT_CONFIRMATION_QUESTION = "请确认以上理解是否准确。确认后，我再生成 workflow。"


ALLOWED_HISTORY_ROLES = {"user", "assistant"}
MAX_HISTORY_MESSAGES = 12
MAX_MESSAGE_CHARS = 4000
MAX_DOCUMENT_CONTEXT_CHARS = 12000


def normalize_extraction_id(extraction_id: str | None) -> str | None:
    safe_id = (extraction_id or "").strip()

    if not safe_id or not re.fullmatch(r"[a-fA-F0-9]{32}", safe_id):
        return None

    return safe_id


def compact_document_text(text: str, max_chars: int = MAX_DOCUMENT_CONTEXT_CHARS) -> str:
    lines = [" ".join(line.split()).strip() for line in text.splitlines()]
    compacted = "\n".join(line for line in lines if line)

    if len(compacted) <= max_chars:
        return compacted

    return compacted[:max_chars].rstrip() + "\n\n[后续内容已截断，仅向主控 Agent 提供前文片段。]"


def load_document_text_preview(extraction_id: str | None) -> str | None:
    safe_id = normalize_extraction_id(extraction_id)

    if not safe_id:
        return None

    txt_path = EXTRACTED_TEXT_DIR / f"{safe_id}.txt"

    if not txt_path.exists():
        return None

    text = txt_path.read_text(encoding="utf-8", errors="ignore")
    preview = compact_document_text(text)

    return preview or None


def ensure_document_context(request: MasterAgentChatRequest) -> None:
    if request.document_text_preview:
        request.document_text_preview = compact_document_text(request.document_text_preview)
        return

    request.document_text_preview = load_document_text_preview(request.extraction_id)


def normalize_chat_message(message: AgentChatMessage) -> dict[str, str] | None:
    role = message.role.strip().lower()
    content = " ".join(message.content.split()).strip()

    if role not in ALLOWED_HISTORY_ROLES or not content:
        return None

    return {
        "role": role,
        "content": content[:MAX_MESSAGE_CHARS],
    }


def build_context_message(request: MasterAgentChatRequest) -> dict[str, str]:
    context_lines = []

    if request.project_id:
        context_lines.append(f"项目 ID：{request.project_id}")

    if request.extraction_id:
        context_lines.append(f"抽取 ID：{request.extraction_id}")

    if request.document_summary:
        context_lines.append(f"文档摘要：{request.document_summary[:1200]}")

    if request.document_text_preview:
        context_lines.append(
            "已上传文件的提取清洗文本片段：\n"
            f"{request.document_text_preview[:MAX_DOCUMENT_CONTEXT_CHARS]}"
        )

    if request.user_goal:
        context_lines.append(f"用户目标：{request.user_goal[:800]}")

    if request.selected_feature:
        context_lines.append(f"前端选择功能：{request.selected_feature}")

    if not context_lines:
        context_lines.append("当前没有额外项目上下文。")

    return {
        "role": "user",
        "content": "当前项目上下文：\n" + "\n".join(context_lines),
    }


def build_master_agent_messages(request: MasterAgentChatRequest) -> list[dict[str, str]]:
    history = [
        normalized
        for message in request.history[-MAX_HISTORY_MESSAGES:]
        if (normalized := normalize_chat_message(message)) is not None
    ]
    user_message = " ".join(request.message.split()).strip()

    if not user_message:
        raise ValueError("请输入要发送给主控 Agent 的内容")

    return [
        build_context_message(request),
        *history,
        {
            "role": "user",
            "content": user_message[:MAX_MESSAGE_CHARS],
        },
    ]


def describe_intent_for_confirmation(request: MasterAgentChatRequest) -> str:
    response_text = chat_text(
        system_prompt=INTENT_CONFIRMATION_SYSTEM_PROMPT,
        messages=build_master_agent_messages(request),
        temperature=0.3,
    ).strip()
    response_text = response_text.rstrip("。！？!? \n")
    return f"{response_text}。\n\n{INTENT_CONFIRMATION_QUESTION}"


def chat_with_master_agent(request: MasterAgentChatRequest) -> dict[str, Any]:
    ensure_document_context(request)

    if is_workflow_intent_confirmed(request):
        confirmed_request = request_with_confirmed_intent(request)
        generated_context = generate_workflow_context(confirmed_request)
        context_update = {
            "document_summary": generated_context["document_summary"],
            "user_goal": generated_context["user_goal"],
        }
        if hasattr(confirmed_request, "model_copy"):
            workflow_request = confirmed_request.model_copy(update=context_update)
        else:
            workflow_request = confirmed_request.copy(update=context_update)
        workflow = generate_workflow(workflow_request)
        return {
            "success": True,
            "role": "assistant",
            "agent": "master",
            "message": "我已根据当前意图生成 workflow。请先确认下面的流程，确认后再开始执行。",
            "project_id": request.project_id,
            "extraction_id": request.extraction_id,
            "document_summary": generated_context["document_summary"],
            "user_goal": generated_context["user_goal"],
            "skill_invocation": None,
            "workflow": workflow,
        }

    if is_clear_workflow_intent(request):
        return {
            "success": True,
            "role": "assistant",
            "agent": "master",
            "message": describe_intent_for_confirmation(request),
            "project_id": request.project_id,
            "extraction_id": request.extraction_id,
            "skill_invocation": None,
            "workflow": None,
        }

    messages = build_master_agent_messages(request)
    response_text = chat_text(
        system_prompt=MASTER_AGENT_SYSTEM_PROMPT,
        messages=messages,
        temperature=0.4,
    )

    return {
        "success": True,
        "role": "assistant",
        "agent": "master",
        "message": response_text.strip(),
        "project_id": request.project_id,
        "extraction_id": request.extraction_id,
        "skill_invocation": None,
        "workflow": None,
    }
