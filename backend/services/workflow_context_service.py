"""Generate the document summary and normalized user goal before workflow planning."""

from __future__ import annotations

import json
from typing import Any

from schemas.agent_schema import MasterAgentChatRequest
from services.llm_service import chat_json
from utils.json_utils import extract_json_from_text


WORKFLOW_CONTEXT_SYSTEM_PROMPT = """
你是 Workflow 生成前的项目上下文整理 Agent。用户的处理意图已经明确并完成确认。

请根据用户意图和文档文本，生成后续“本体草案生成”可直接使用的上下文。

输出要求：
1. 只输出 JSON object，不要输出 Markdown。
2. JSON 只包含 document_summary 和 user_goal。
3. document_summary 客观概括文档的主题、核心对象、关键事件与关系线索，不编造文档中没有的内容。
4. user_goal 将用户的已确认意图改写为简洁、明确、可执行的建图目标。
5. 若文档内容有限，document_summary 应保守说明已知内容和信息边界。
""".strip()


def _normalize_text(value: Any, max_chars: int) -> str:
    return " ".join(str(value or "").split()).strip()[:max_chars]


def _fallback_context(request: MasterAgentChatRequest) -> dict[str, str]:
    preview = _normalize_text(request.document_text_preview, 1600)
    summary = preview or _normalize_text(request.document_summary, 1600)
    if not summary:
        summary = "当前未获取到足够的文档内容，后续将仅基于用户已确认目标进行保守处理。"

    goal = _normalize_text(request.message or request.user_goal, 800)
    if not goal:
        goal = "基于当前文档构建可审核的知识图谱。"

    return {"document_summary": summary, "user_goal": goal}


def generate_workflow_context(request: MasterAgentChatRequest) -> dict[str, str]:
    context = {
        "confirmed_user_intent": request.message,
        "selected_feature": request.selected_feature,
        "document_text": request.document_text_preview,
        "existing_document_summary": request.document_summary,
        "existing_user_goal": request.user_goal,
    }

    try:
        response_text = chat_json(
            system_prompt=WORKFLOW_CONTEXT_SYSTEM_PROMPT,
            user_prompt=json.dumps(context, ensure_ascii=False, indent=2),
            temperature=0.2,
        )
        payload = extract_json_from_text(response_text)
        document_summary = _normalize_text(payload.get("document_summary"), 4000)
        user_goal = _normalize_text(payload.get("user_goal"), 1200)
        if not document_summary or not user_goal:
            raise ValueError("LLM 未返回完整的 workflow 上下文")
        return {"document_summary": document_summary, "user_goal": user_goal}
    except Exception:
        return _fallback_context(request)
