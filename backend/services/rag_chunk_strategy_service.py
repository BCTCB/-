"""RAG chunk strategy skill.

This skill reuses the existing KG text cleanup and structure clue extraction,
then asks the LLM for a retrieval-oriented split strategy.
"""

import json
import re
from pathlib import Path
from typing import Any

from config import CHUNKS_DIR, STRATEGY_DIR
from prompts.rag_chunk_strategy_prompt import RAG_CHUNK_STRATEGY_PROMPT
from services.chunk_service import (
    build_document_preview,
    build_split_report,
    clean_text_for_chunking,
    extract_structure_clues,
    get_extracted_text_path,
    read_txt_file,
    split_by_chapter_section_question,
    split_by_fixed_length,
    split_by_generic_heading,
    split_by_heading_regex,
    split_by_two_level_regex,
)
from services.llm_service import chat_json
from utils.json_utils import extract_json_from_text, read_json, write_json


DEFAULT_RAG_METADATA_FIELDS = [
    "chunk_id",
    "doc_id",
    "title",
    "parent_title",
    "chapter_title",
    "section_title",
    "retrieval_unit_type",
    "start_char",
    "end_char",
    "char_count",
    "embedding_text",
    "content",
]


def get_rag_split_strategy_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return STRATEGY_DIR / "rag" / f"{safe_id}_rag_split_strategy.json"


def get_rag_chunks_json_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return CHUNKS_DIR / "rag" / f"{safe_id}_rag_chunks.json"


def get_rag_chunks_jsonl_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return CHUNKS_DIR / "rag" / f"{safe_id}_rag_chunks.jsonl"


def write_jsonl(data: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        for item in data:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


def build_rag_split_strategy_user_prompt(text: str) -> str:
    cleaned_text = clean_text_for_chunking(text)
    structure_clues = extract_structure_clues(cleaned_text)
    document_preview = build_document_preview(cleaned_text)

    return f"""
请根据以下资料，判断最适合后续 RAG 检索与问答的文本切分方式。

注意：
1. 你只需要判断 RAG 切分策略。
2. 不要抽取实体。
3. 不要生成知识图谱。
4. 不要总结资料内容。
5. 必须输出 executable_rag_split_config。
6. executable_rag_split_config 中的正则表达式必须可以被 Python re 直接使用。
7. 可以复用知识图谱切分中的结构线索，但最终目标是提升检索召回、引用准确性和回答可读性。
8. 不要假设资料一定是“案例”，也可能是例子、问题、任务、实验、条目、故障排查或其他结构。

====================
结构线索
====================

{json.dumps(structure_clues, ensure_ascii=False, indent=2)}

====================
资料内容预览
====================

{document_preview}
"""


def validate_and_repair_rag_strategy(result: dict[str, Any]) -> dict[str, Any]:
    if "executable_rag_split_config" not in result:
        result["executable_rag_split_config"] = {}

    config = result["executable_rag_split_config"]
    config.setdefault("split_mode", "structure_then_window")
    config.setdefault("retrieval_unit_name", "semantic_chunk")
    config.setdefault("primary_unit_name", "structure_unit")
    config.setdefault("secondary_unit_name", None)
    config.setdefault("primary_start_patterns", [])
    config.setdefault("secondary_start_patterns", [])
    config.setdefault("parent_context_patterns", [])
    config.setdefault("chapter_start_patterns", [])
    config.setdefault("section_start_patterns", [])
    config.setdefault("question_start_patterns", [])
    config.setdefault(
        "semantic_window",
        {
            "target_chars": 900,
            "max_chars": 1400,
            "min_chars": 300,
            "overlap_chars": 120,
            "split_priority": ["blank_line", "paragraph", "sentence", "fixed_length"],
        },
    )
    config.setdefault(
        "context_injection",
        {
            "prepend_title_chain_to_embedding_text": True,
            "prepend_title_chain_to_display_content": False,
            "title_chain_separator": " > ",
        },
    )
    config.setdefault("metadata_fields", DEFAULT_RAG_METADATA_FIELDS)
    config.setdefault(
        "fallback",
        {
            "enabled": True,
            "method": "generic_heading_then_semantic_window",
            "target_chars": 900,
            "max_chars": 1400,
            "overlap_chars": 120,
        },
    )

    semantic_window = config.get("semantic_window")
    if not isinstance(semantic_window, dict):
        semantic_window = {}
        config["semantic_window"] = semantic_window

    semantic_window.setdefault("target_chars", 900)
    semantic_window.setdefault("max_chars", 1400)
    semantic_window.setdefault("min_chars", 300)
    semantic_window.setdefault("overlap_chars", 120)
    semantic_window.setdefault(
        "split_priority",
        ["blank_line", "paragraph", "sentence", "fixed_length"],
    )

    fallback = config.get("fallback")
    if not isinstance(fallback, dict):
        fallback = {}
        config["fallback"] = fallback

    fallback.setdefault("enabled", True)
    fallback.setdefault("method", "generic_heading_then_semantic_window")
    fallback.setdefault("target_chars", semantic_window["target_chars"])
    fallback.setdefault("max_chars", semantic_window["max_chars"])
    fallback.setdefault("overlap_chars", semantic_window["overlap_chars"])

    return result


def analyze_rag_split_strategy(text: str) -> dict[str, Any]:
    response_text = chat_json(
        system_prompt=RAG_CHUNK_STRATEGY_PROMPT,
        user_prompt=build_rag_split_strategy_user_prompt(text),
        temperature=0.1,
    )
    result = extract_json_from_text(response_text)

    if not isinstance(result, dict):
        raise ValueError("RAG 切分策略结果必须是 JSON object")

    return validate_and_repair_rag_strategy(result)


def analyze_rag_split_strategy_from_extraction(extraction_id: str) -> dict[str, Any]:
    txt_path = get_extracted_text_path(extraction_id)
    text = read_txt_file(txt_path)
    rag_strategy = analyze_rag_split_strategy(text)
    strategy_path = get_rag_split_strategy_path(extraction_id)
    payload = {
        "extraction_id": extraction_id,
        "source_txt_path": str(txt_path),
        "strategy_path": str(strategy_path),
        "strategy_type": "rag_split_strategy",
        "strategy": rag_strategy,
        "next_stage": "rag_chunk_generation",
    }


def get_executable_rag_config(strategy_payload: dict[str, Any]) -> dict[str, Any]:
    strategy = strategy_payload.get("strategy", strategy_payload)
    config = strategy.get("executable_rag_split_config")

    if not config:
        raise ValueError("RAG 切分策略中缺少 executable_rag_split_config 字段")

    return validate_and_repair_rag_strategy(
        {"executable_rag_split_config": config}
    )["executable_rag_split_config"]


def build_structure_split_config(config: dict[str, Any]) -> dict[str, Any]:
    split_mode = config.get("split_mode", "structure_then_window")

    if split_mode == "structure_then_window":
        if config.get("chapter_start_patterns") and config.get("question_start_patterns"):
            split_mode = "chapter_section_question"
        elif config.get("secondary_start_patterns"):
            split_mode = "two_level_regex"
        elif config.get("primary_start_patterns"):
            split_mode = "heading_regex"
        else:
            split_mode = "fixed_length"

    fallback = config.get("fallback", {})
    semantic_window = config.get("semantic_window", {})

    return {
        "split_mode": split_mode,
        "primary_start_patterns": config.get("primary_start_patterns", []),
        "secondary_start_patterns": config.get("secondary_start_patterns", []),
        "parent_context_patterns": config.get("parent_context_patterns", []),
        "chapter_start_patterns": config.get("chapter_start_patterns", []),
        "section_start_patterns": config.get("section_start_patterns", []),
        "question_start_patterns": config.get("question_start_patterns", []),
        "fallback": {
            "enabled": True,
            "method": "generic_heading_then_fixed_length",
            "max_chars": fallback.get("max_chars")
            or semantic_window.get("max_chars")
            or 1400,
            "overlap": fallback.get("overlap_chars")
            or semantic_window.get("overlap_chars")
            or 120,
        },
    }


def split_base_structure_units(text: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    structure_config = build_structure_split_config(config)
    split_mode = structure_config.get("split_mode")
    chunks: list[dict[str, Any]] = []

    if split_mode == "heading_regex":
        chunks = split_by_heading_regex(text, structure_config)
    elif split_mode == "two_level_regex":
        chunks = split_by_two_level_regex(text, structure_config)
    elif split_mode == "chapter_section_question":
        chunks = split_by_chapter_section_question(text, structure_config)
    elif split_mode == "fixed_length":
        fallback = structure_config.get("fallback", {})
        chunks = split_by_fixed_length(
            text,
            max_chars=fallback.get("max_chars", 1400),
            overlap=fallback.get("overlap", 120),
        )

    if chunks:
        return chunks

    generic_chunks = split_by_generic_heading(text)
    if generic_chunks:
        return generic_chunks

    semantic_window = config.get("semantic_window", {})
    return split_by_fixed_length(
        text,
        max_chars=semantic_window.get("max_chars", 1400),
        overlap=semantic_window.get("overlap_chars", 120),
    )


def sentence_split(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?；;])\s*", text)
    return [part.strip() for part in parts if part.strip()]


def split_long_text_semantically(
    content: str,
    max_chars: int,
    overlap_chars: int,
) -> list[tuple[str, int, int]]:
    content = content.strip()

    if not content:
        return []

    if len(content) <= max_chars:
        return [(content, 0, len(content))]

    paragraphs = [
        match
        for match in re.finditer(r"\S(?:.*?\S)?(?:\n\s*\n|$)", content, flags=re.DOTALL)
        if match.group(0).strip()
    ]
    units: list[tuple[str, int, int]] = []

    for paragraph_match in paragraphs:
        paragraph = paragraph_match.group(0).strip()
        paragraph_start = paragraph_match.start()

        if len(paragraph) <= max_chars:
            units.append((paragraph, paragraph_start, paragraph_start + len(paragraph)))
            continue

        search_start = 0
        for sentence in sentence_split(paragraph):
            sentence_start = paragraph.find(sentence, search_start)
            if sentence_start < 0:
                sentence_start = search_start

            global_start = paragraph_start + sentence_start
            units.append((sentence, global_start, global_start + len(sentence)))
            search_start = sentence_start + len(sentence)

    if not units:
        units = [(content[index : index + max_chars], index, min(index + max_chars, len(content))) for index in range(0, len(content), max_chars)]

    windows: list[tuple[str, int, int]] = []
    current_parts: list[str] = []
    current_start: int | None = None
    current_end = 0

    for unit_text, unit_start, unit_end in units:
        candidate = "\n\n".join([*current_parts, unit_text]).strip()

        if current_parts and len(candidate) > max_chars:
            window_text = "\n\n".join(current_parts).strip()
            if window_text and current_start is not None:
                windows.append((window_text, current_start, current_end))

            if overlap_chars > 0 and windows:
                overlap_text = window_text[-overlap_chars:].strip()
                current_parts = [overlap_text, unit_text] if overlap_text else [unit_text]
                current_start = max(current_end - len(overlap_text), unit_start)
            else:
                current_parts = [unit_text]
                current_start = unit_start

            current_end = unit_end
            continue

        if not current_parts:
            current_start = unit_start

        current_parts.append(unit_text)
        current_end = unit_end

    if current_parts and current_start is not None:
        windows.append(("\n\n".join(current_parts).strip(), current_start, current_end))

    return windows


def build_title_chain(chunk: dict[str, Any], separator: str) -> str:
    titles = [
        chunk.get("chapter_title"),
        chunk.get("section_title"),
        chunk.get("parent_title"),
        chunk.get("title"),
    ]
    cleaned_titles: list[str] = []
    seen: set[str] = set()

    for title in titles:
        text = str(title or "").strip()

        if not text or text in seen:
            continue

        seen.add(text)
        cleaned_titles.append(text)

    return separator.join(cleaned_titles)


def build_embedding_text(content: str, chunk: dict[str, Any], config: dict[str, Any]) -> str:
    context_config = config.get("context_injection", {})

    if not context_config.get("prepend_title_chain_to_embedding_text", True):
        return content

    separator = context_config.get("title_chain_separator", " > ")
    title_chain = build_title_chain(chunk, separator)

    if not title_chain:
        return content

    return f"{title_chain}\n\n{content}".strip()


def build_rag_chunks(
    extraction_id: str,
    text: str,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    base_chunks = split_base_structure_units(text, config)
    semantic_window = config.get("semantic_window", {})
    max_chars = int(semantic_window.get("max_chars", 1400))
    overlap_chars = int(semantic_window.get("overlap_chars", 120))
    retrieval_unit_name = str(config.get("retrieval_unit_name") or "semantic_chunk")
    rag_chunks: list[dict[str, Any]] = []

    for base_index, base_chunk in enumerate(base_chunks, start=1):
        windows = split_long_text_semantically(
            str(base_chunk.get("content") or ""),
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )

        for window_index, (content, local_start, local_end) in enumerate(windows, start=1):
            start_char = int(base_chunk.get("start_char") or 0) + local_start
            end_char = int(base_chunk.get("start_char") or 0) + local_end
            chunk_id = f"rag_{base_index:04d}_{window_index:02d}"
            rag_chunk = {
                "chunk_id": chunk_id,
                "split_type": "rag_semantic_window",
                "doc_id": extraction_id,
                "title": base_chunk.get("title"),
                "parent_title": base_chunk.get("parent_title"),
                "chapter_title": base_chunk.get("chapter_title"),
                "section_title": base_chunk.get("section_title"),
                "retrieval_unit_type": retrieval_unit_name,
                "source_split_type": base_chunk.get("split_type"),
                "source_chunk_id": base_chunk.get("chunk_id"),
                "window_index": window_index,
                "start_char": start_char,
                "end_char": end_char,
                "char_count": len(content),
                "content": content,
            }
            rag_chunk["embedding_text"] = build_embedding_text(content, rag_chunk, config)
            rag_chunks.append(rag_chunk)

    return rag_chunks


def execute_rag_chunking_from_extraction(extraction_id: str) -> dict[str, Any]:
    txt_path = get_extracted_text_path(extraction_id)
    strategy_path = get_rag_split_strategy_path(extraction_id)
    raw_text = read_txt_file(txt_path)
    text = clean_text_for_chunking(raw_text)
    strategy_payload = read_json(strategy_path)
    config = get_executable_rag_config(strategy_payload)
    rag_chunks = build_rag_chunks(extraction_id=extraction_id, text=text, config=config)

    if not rag_chunks:
        raise RuntimeError("RAG 切分失败：没有生成任何 chunk")

    chunks_json_path = get_rag_chunks_json_path(extraction_id)
    chunks_jsonl_path = get_rag_chunks_jsonl_path(extraction_id)
    report = build_split_report(rag_chunks)
    output_data = {
        "extraction_id": extraction_id,
        "source_file": str(txt_path),
        "strategy_file": str(strategy_path),
        "executable_rag_split_config": config,
        "split_report": report,
        "chunks": rag_chunks,
        "next_stage": "rag_embedding",
    }

    write_json(chunks_json_path, output_data)
    write_jsonl(rag_chunks, chunks_jsonl_path)

    return {
        "success": True,
        "message": "RAG 文本切分完成，chunks 已包含检索所需 metadata 和 embedding_text",
        "extraction_id": extraction_id,
        "source_txt_path": str(txt_path),
        "strategy_path": str(strategy_path),
        "chunks_json_path": str(chunks_json_path),
        "chunks_jsonl_path": str(chunks_jsonl_path),
        "split_report": report,
        "next_stage": "rag_embedding",
    }
    write_json(strategy_path, payload)

    return {
        "success": True,
        "message": "RAG 切分策略分析完成，结果已保存供后续检索流程使用",
        "extraction_id": extraction_id,
        "source_txt_path": str(txt_path),
        "strategy_path": str(strategy_path),
        "strategy": rag_strategy,
        "next_stage": "rag_chunk_generation",
    }
