import json
import re
from pathlib import Path
from typing import Any

from config import CHUNK_QUALITY_DIR, CHUNKS_DIR, EXTRACTED_TEXT_DIR, STRATEGY_DIR
from prompts.chunk_strategy_prompt import CHUNK_STRATEGY_PROMPT
from services.chunk_quality_service import (
    build_quality_report,
    check_all_chunks,
    filter_problem_chunks,
    write_jsonl as write_quality_jsonl,
)
from services.llm_service import chat_json
from utils.json_utils import extract_json_from_text, read_json, write_json


GENERIC_HEADING_PATTERNS = [
    r"^第[一二三四五六七八九十百千万\d]+[章节篇部分].{0,80}$",
    r"^\d+(?:\.\d+)*[、.．]?\s+.{2,80}$",
    r"^[一二三四五六七八九十]+[、.．]\s*.{2,80}$",
    r"^[（(][一二三四五六七八九十\d]+[）)]\s*.{2,80}$",
    r"^[A-Z][、.．]\s+.{2,80}$",
]

DEFAULT_CHAPTER_PATTERNS = [
    r"^第\s*[一二三四五六七八九十百千万\d]+\s*章\s+.{1,80}$",
]

DEFAULT_SECTION_PATTERNS = [
    r"^第\s*[一二三四五六七八九十百千万\d]+\s*节\s+.{1,80}$",
]

DEFAULT_QUESTION_PATTERNS = [
    r"^\d+[、.．]\s*.{2,80}[？?]\s*$",
]


def read_txt_file(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"输入文件不存在：{file_path}")

    if file_path.suffix.lower() != ".txt":
        raise ValueError(f"当前模块只支持 .txt 文件，当前文件是：{file_path.suffix}")

    return file_path.read_text(encoding="utf-8", errors="ignore")


def write_jsonl(data: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        for item in data:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


def clean_text_for_chunking(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("－", "-").replace("—", "-").replace("–", "-")
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.split("\n")]
    lines = remove_table_of_contents_lines(lines)
    return "\n".join(lines).strip()


def is_table_of_contents_line(line: str) -> bool:
    if not line:
        return False

    normalized = line.replace("…", ".").replace("·", ".")

    if re.fullmatch(r"目\s*录", normalized):
        return True

    dot_count = normalized.count(".")
    has_trailing_page = bool(
        re.search(r"(?:\(|（)?\s*[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ\d]+\s*(?:\)|）)?\s*$", normalized)
    )
    has_toc_leader = bool(re.search(r"[.\-_\s]{4,}", normalized))

    if has_trailing_page and has_toc_leader:
        return True

    if dot_count >= 4 and len(normalized) <= 180:
        return True

    return False


def remove_table_of_contents_lines(lines: list[str]) -> list[str]:
    cleaned = []
    in_toc_block = False
    toc_line_count = 0

    for line in lines:
        if re.fullmatch(r"目\s*录", line):
            in_toc_block = True
            toc_line_count = 0
            continue

        if in_toc_block:
            if is_table_of_contents_line(line):
                toc_line_count += 1
                continue

            if toc_line_count >= 3 and re.match(r"^第\s*[一二三四五六七八九十百千万\d]+\s*章", line):
                in_toc_block = False
            elif toc_line_count < 3:
                in_toc_block = False
            else:
                continue

        if is_table_of_contents_line(line):
            continue

        cleaned.append(line)

    return cleaned


def extract_structure_clues(text: str) -> dict[str, Any]:
    lines = text.split("\n")

    heading_patterns = {
        "chapter_like": [
            r"^第[一二三四五六七八九十百千万\d]+[章节篇部分]\s*[^\n]{0,80}$",
        ],
        "numbered_heading_like": [
            r"^\d+(?:\.\d+)*[、.．]?\s+[^\n]{2,80}$",
        ],
        "chinese_number_heading_like": [
            r"^[一二三四五六七八九十]+[、.．]\s*[^\n]{2,80}$",
        ],
        "bracket_heading_like": [
            r"^[（(][一二三四五六七八九十\d]+[）)]\s*[^\n]{2,80}$",
        ],
        "item_like": [
            r"^(案例|例子|示例|实例|问题|题目|任务|实验|项目|条目|记录|事件|步骤|模块)\s*[一二三四五六七八九十百千万\d]+(?:[-－—.]\d+)*\s*[^\n]{0,100}$",
            r"^(案例|例子|示例|实例|问题|题目|任务|实验|项目|条目|记录|事件|步骤|模块)\s*[:：]\s*[^\n]{1,100}$",
        ],
    }

    structure_keywords = [
        "章节",
        "小节",
        "部分",
        "模块",
        "案例",
        "例子",
        "示例",
        "实例",
        "问题",
        "题目",
        "任务",
        "实验",
        "项目",
        "条目",
        "记录",
        "事件",
        "系统",
        "设备",
        "部件",
        "现象",
        "原因",
        "方法",
        "措施",
        "步骤",
        "流程",
        "结论",
    ]

    results: dict[str, Any] = {
        "chapter_like": [],
        "numbered_heading_like": [],
        "chinese_number_heading_like": [],
        "bracket_heading_like": [],
        "item_like": [],
        "keyword_structure_lines": [],
        "total_chars": len(text),
        "total_lines": len(lines),
    }

    for line in lines:
        line = line.strip()

        if not line:
            continue

        for category, patterns in heading_patterns.items():
            for pattern in patterns:
                if re.search(pattern, line):
                    results[category].append(line)
                    break

        if len(line) <= 120 and any(keyword in line for keyword in structure_keywords):
            results["keyword_structure_lines"].append(line)

    for key in [
        "chapter_like",
        "numbered_heading_like",
        "chinese_number_heading_like",
        "bracket_heading_like",
        "item_like",
        "keyword_structure_lines",
    ]:
        count = len(results[key])
        results[f"{key}_count"] = count
        results[key] = results[key][:100]

    return results


def build_document_preview(text: str, max_chars: int = 24000) -> str:
    if len(text) <= max_chars:
        return text

    part_len = max_chars // 3
    start_part = text[:part_len]
    middle_start = max(0, len(text) // 2 - part_len // 2)
    middle_part = text[middle_start : middle_start + part_len]
    end_part = text[-part_len:]

    return f"""
【文档开头部分】
{start_part}

【文档中间部分】
{middle_part}

【文档结尾部分】
{end_part}
""".strip()


def validate_and_repair_strategy(result: dict[str, Any]) -> dict[str, Any]:
    if "executable_split_config" not in result:
        result["executable_split_config"] = {
            "split_mode": "fixed_length",
            "primary_unit_name": "fixed_chunk",
            "secondary_unit_name": None,
            "primary_start_patterns": [],
            "secondary_start_patterns": [],
            "parent_context_patterns": [],
            "end_boundary_rule": "document_end",
            "keep_parent_context": False,
            "metadata_fields": [
                "chunk_id",
                "title",
                "parent_title",
                "chapter_title",
                "section_title",
                "start_char",
                "end_char",
                "content",
            ],
            "fallback": {
                "enabled": True,
                "method": "generic_heading_then_fixed_length",
                "max_chars": 3000,
                "overlap": 300,
            },
        }

    config = result["executable_split_config"]
    config.setdefault("split_mode", "fixed_length")
    config.setdefault("primary_unit_name", "fixed_chunk")
    config.setdefault("secondary_unit_name", None)
    config.setdefault("primary_start_patterns", [])
    config.setdefault("secondary_start_patterns", [])
    config.setdefault("parent_context_patterns", [])
    config.setdefault("end_boundary_rule", "next_same_level_start")
    config.setdefault("keep_parent_context", True)
    config.setdefault(
        "metadata_fields",
        [
            "chunk_id",
            "title",
            "parent_title",
            "chapter_title",
            "section_title",
            "start_char",
            "end_char",
            "content",
        ],
    )
    config.setdefault(
        "fallback",
        {
            "enabled": True,
            "method": "generic_heading_then_fixed_length",
            "max_chars": 3000,
            "overlap": 300,
        },
    )

    return result


def build_split_strategy_user_prompt(text: str) -> str:
    cleaned_text = clean_text_for_chunking(text)
    structure_clues = extract_structure_clues(cleaned_text)
    document_preview = build_document_preview(cleaned_text)

    return f"""
请根据以下资料，判断最适合后续知识图谱抽取的文本切分方式。

注意：
1. 你只需要判断切分策略。
2. 不要抽取实体。
3. 不要生成知识图谱。
4. 不要总结资料内容。
5. 必须输出 executable_split_config。
6. executable_split_config 中的正则表达式必须可以被 Python re 直接使用。
7. 不要假设资料一定是“案例”，也可能是例子、问题、任务、实验、条目或其他结构。

====================
结构线索
====================

{json.dumps(structure_clues, ensure_ascii=False, indent=2)}

====================
资料内容预览
====================

{document_preview}
"""


def analyze_split_strategy(text: str) -> dict[str, Any]:
    response_text = chat_json(
        system_prompt=CHUNK_STRATEGY_PROMPT,
        user_prompt=build_split_strategy_user_prompt(text),
        temperature=0.1,
    )
    result = extract_json_from_text(response_text)

    if not isinstance(result, dict):
        raise ValueError("切分策略结果必须是 JSON object")

    return validate_and_repair_strategy(result)


def get_extracted_text_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return EXTRACTED_TEXT_DIR / f"{safe_id}.txt"


def get_split_strategy_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return STRATEGY_DIR / f"{safe_id}_split_strategy.json"


def get_chunks_json_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return CHUNKS_DIR / f"{safe_id}_chunks.json"


def get_chunks_jsonl_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return CHUNKS_DIR / f"{safe_id}_chunks.jsonl"


def get_chunk_quality_report_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return CHUNK_QUALITY_DIR / f"{safe_id}_chunk_quality_report.json"


def get_problem_chunks_jsonl_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return CHUNK_QUALITY_DIR / f"{safe_id}_problem_chunks.jsonl"


def get_executable_config(strategy_payload: dict[str, Any]) -> dict[str, Any]:
    strategy = strategy_payload.get("strategy", strategy_payload)
    config = strategy.get("executable_split_config")

    if not config:
        raise ValueError("切分策略中缺少 executable_split_config 字段")

    return config


def get_fallback_config(config: dict[str, Any]) -> dict[str, Any]:
    return config.get(
        "fallback",
        {
            "enabled": True,
            "method": "generic_heading_then_fixed_length",
            "max_chars": 3000,
            "overlap": 300,
        },
    )


def compile_patterns(patterns: list[str]) -> list[re.Pattern]:
    compiled = []

    for pattern in patterns:
        if not pattern:
            continue

        try:
            compiled.append(re.compile(pattern, flags=re.MULTILINE))
        except re.error:
            continue

    return compiled


def deduplicate_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches = sorted(matches, key=lambda item: (item["start"], item["end"]))
    result = []
    used_ranges = set()

    for item in matches:
        key = (item["start"], item["end"])

        if key in used_ranges:
            continue

        used_ranges.add(key)
        result.append(item)

    return result


def find_matches_by_patterns(text: str, patterns: list[str]) -> list[dict[str, Any]]:
    matches = []

    for pattern in compile_patterns(patterns):
        for match in pattern.finditer(text):
            title = match.group(0).strip()

            if not title or len(title) > 200:
                continue

            matches.append(
                {
                    "title": title,
                    "start": match.start(),
                    "end": match.end(),
                    "pattern": pattern.pattern,
                }
            )

    return deduplicate_matches(matches)


def find_nearest_parent_title(
    parent_contexts: list[dict[str, Any]],
    start: int,
) -> str | None:
    parent_title = None

    for item in parent_contexts:
        if item["start"] <= start:
            parent_title = item["title"]
        else:
            break

    return parent_title


def find_containing_boundary(
    boundaries: list[dict[str, Any]],
    start: int,
) -> dict[str, Any] | None:
    containing = None

    for boundary in boundaries:
        if boundary["start"] <= start:
            containing = boundary
        else:
            break

    return containing


def normalize_title_for_id(title: str) -> str:
    title = title.strip()
    title = re.sub(r"\s+", "_", title)
    title = re.sub(r"[^\w\u4e00-\u9fff\-]+", "", title)
    return title[:40]


def make_chunk_id(index: int, title: str, split_type: str) -> str:
    short_title = normalize_title_for_id(title)

    if short_title:
        return f"{split_type}_{index:04d}_{short_title}"

    return f"{split_type}_{index:04d}"


def split_by_boundaries(
    text: str,
    boundaries: list[dict[str, Any]],
    split_type: str,
    parent_contexts: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    chunks = []

    if not boundaries:
        return chunks

    parent_contexts = parent_contexts or []

    for index, boundary in enumerate(boundaries, start=1):
        start = boundary["start"]

        if index < len(boundaries):
            end = boundaries[index]["start"]
        else:
            end = len(text)

        content = text[start:end].strip()

        if not content:
            continue

        title = boundary["title"]
        parent_title = find_nearest_parent_title(parent_contexts, start)

        chunks.append(
            {
                "chunk_id": make_chunk_id(index, title, split_type),
                "split_type": split_type,
                "title": title,
                "parent_title": parent_title,
                "start_char": start,
                "end_char": end,
                "char_count": len(content),
                "content": content,
            }
        )

    return chunks


def split_by_heading_regex(text: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    primary_patterns = config.get("primary_start_patterns", [])
    parent_patterns = config.get("parent_context_patterns", [])
    boundaries = find_matches_by_patterns(text, primary_patterns)
    parent_contexts = find_matches_by_patterns(text, parent_patterns)

    return split_by_boundaries(
        text=text,
        boundaries=boundaries,
        split_type="heading_regex",
        parent_contexts=parent_contexts,
    )


def split_by_two_level_regex(text: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    primary_patterns = config.get("primary_start_patterns", [])
    secondary_patterns = config.get("secondary_start_patterns", [])
    parent_patterns = config.get("parent_context_patterns", [])

    primary_boundaries = find_matches_by_patterns(text, primary_patterns)
    parent_contexts = find_matches_by_patterns(text, parent_patterns)

    if not primary_boundaries:
        return []

    primary_chunks = split_by_boundaries(
        text=text,
        boundaries=primary_boundaries,
        split_type="primary",
        parent_contexts=parent_contexts,
    )

    if not secondary_patterns:
        return primary_chunks

    final_chunks = []

    for primary_index, primary_chunk in enumerate(primary_chunks, start=1):
        local_text = primary_chunk["content"]
        local_secondary_boundaries = find_matches_by_patterns(local_text, secondary_patterns)

        if not local_secondary_boundaries:
            primary_chunk["split_type"] = "primary_only"
            final_chunks.append(primary_chunk)
            continue

        for secondary_index, boundary in enumerate(local_secondary_boundaries, start=1):
            local_start = boundary["start"]

            if secondary_index < len(local_secondary_boundaries):
                local_end = local_secondary_boundaries[secondary_index]["start"]
            else:
                local_end = len(local_text)

            content = local_text[local_start:local_end].strip()

            if not content:
                continue

            global_start = primary_chunk["start_char"] + local_start
            global_end = primary_chunk["start_char"] + local_end
            title = boundary["title"]

            final_chunks.append(
                {
                    "chunk_id": f"two_level_{primary_index:04d}_{secondary_index:04d}_{normalize_title_for_id(title)}",
                    "split_type": "two_level_regex",
                    "title": title,
                    "parent_title": primary_chunk.get("title"),
                    "start_char": global_start,
                    "end_char": global_end,
                    "char_count": len(content),
                    "content": content,
                }
            )

    return final_chunks


def get_config_patterns(
    config: dict[str, Any],
    key: str,
    default_patterns: list[str],
) -> list[str]:
    patterns = config.get(key)

    if isinstance(patterns, list) and patterns:
        return patterns

    return default_patterns


def split_by_chapter_section_question(text: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    chapter_patterns = get_config_patterns(config, "chapter_start_patterns", DEFAULT_CHAPTER_PATTERNS)
    section_patterns = get_config_patterns(config, "section_start_patterns", DEFAULT_SECTION_PATTERNS)
    question_patterns = get_config_patterns(config, "question_start_patterns", DEFAULT_QUESTION_PATTERNS)

    chapter_boundaries = find_matches_by_patterns(text, chapter_patterns)
    section_boundaries = find_matches_by_patterns(text, section_patterns)
    question_boundaries = find_matches_by_patterns(text, question_patterns)

    if not chapter_boundaries or not question_boundaries:
        return []

    chunks = []

    for index, question in enumerate(question_boundaries, start=1):
        start = question["start"]

        if index < len(question_boundaries):
            end = question_boundaries[index]["start"]
        else:
            end = len(text)

        chapter = find_containing_boundary(chapter_boundaries, start)
        section = find_containing_boundary(section_boundaries, start)

        if not chapter:
            continue

        next_chapter = None
        for boundary in chapter_boundaries:
            if boundary["start"] > start:
                next_chapter = boundary
                break

        next_section = None
        for boundary in section_boundaries:
            if boundary["start"] > start:
                next_section = boundary
                break

        if next_chapter and next_chapter["start"] < end:
            end = next_chapter["start"]

        if next_section and next_section["start"] < end:
            end = next_section["start"]

        content = text[start:end].strip()

        if not content:
            continue

        section_title = section["title"] if section else None
        chapter_title = chapter["title"]
        title = question["title"]

        chunks.append(
            {
                "chunk_id": f"chapter_section_question_{index:04d}_{normalize_title_for_id(title)}",
                "split_type": "chapter_section_question",
                "title": title,
                "parent_title": section_title or chapter_title,
                "chapter_title": chapter_title,
                "section_title": section_title,
                "start_char": start,
                "end_char": end,
                "char_count": len(content),
                "content": content,
            }
        )

    return chunks


def split_by_generic_heading(text: str) -> list[dict[str, Any]]:
    boundaries = find_matches_by_patterns(text, GENERIC_HEADING_PATTERNS)
    return split_by_boundaries(
        text=text,
        boundaries=boundaries,
        split_type="generic_heading",
        parent_contexts=[],
    )


def split_by_fixed_length(
    text: str,
    max_chars: int = 3000,
    overlap: int = 300,
) -> list[dict[str, Any]]:
    chunks = []
    start = 0
    index = 1
    overlap = max(0, min(overlap, max_chars - 1))

    while start < len(text):
        end = min(start + max_chars, len(text))
        content = text[start:end].strip()

        if content:
            chunks.append(
                {
                    "chunk_id": f"fixed_{index:04d}",
                    "split_type": "fixed_length",
                    "title": f"fixed_chunk_{index:04d}",
                    "parent_title": None,
                    "start_char": start,
                    "end_char": end,
                    "char_count": len(content),
                    "content": content,
                }
            )

        if end >= len(text):
            break

        start = end - overlap
        index += 1

    return chunks


def split_text_by_config(text: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    split_mode = config.get("split_mode", "fixed_length")
    fallback = get_fallback_config(config)
    chunks: list[dict[str, Any]] = []

    if split_mode == "heading_regex":
        chunks = split_by_heading_regex(text, config)
    elif split_mode == "two_level_regex":
        chunks = split_by_two_level_regex(text, config)
    elif split_mode in {"chapter_section_question", "three_level_regex"}:
        chunks = split_by_chapter_section_question(text, config)
    elif split_mode == "fixed_length":
        max_chars = fallback.get("max_chars", 3000)
        overlap = fallback.get("overlap", 300)
        chunks = split_by_fixed_length(text, max_chars=max_chars, overlap=overlap)

    if chunks:
        return chunks

    if fallback.get("enabled", True):
        method = fallback.get("method", "generic_heading_then_fixed_length")
        max_chars = fallback.get("max_chars", 3000)
        overlap = fallback.get("overlap", 300)

        if method == "generic_heading_then_fixed_length":
            chunks = split_by_generic_heading(text)

            if chunks:
                return chunks

            return split_by_fixed_length(text, max_chars=max_chars, overlap=overlap)

        if method == "fixed_length":
            return split_by_fixed_length(text, max_chars=max_chars, overlap=overlap)

    return []


def build_split_report(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    if not chunks:
        return {
            "chunk_count": 0,
            "split_types": {},
            "avg_chars": 0,
            "max_chars": 0,
            "min_chars": 0,
            "first_5_chunks": [],
        }

    lengths = [chunk["char_count"] for chunk in chunks]
    split_types: dict[str, int] = {}

    for chunk in chunks:
        split_type = chunk.get("split_type", "unknown")
        split_types[split_type] = split_types.get(split_type, 0) + 1

    return {
        "chunk_count": len(chunks),
        "split_types": split_types,
        "avg_chars": sum(lengths) // len(lengths),
        "max_chars": max(lengths),
        "min_chars": min(lengths),
        "first_5_chunks": [
            {
                "chunk_id": chunk.get("chunk_id"),
                "title": chunk.get("title"),
                "parent_title": chunk.get("parent_title"),
                "chapter_title": chunk.get("chapter_title"),
                "section_title": chunk.get("section_title"),
                "chars": chunk.get("char_count"),
            }
            for chunk in chunks[:5]
        ],
    }


def analyze_split_strategy_from_extraction(extraction_id: str) -> dict[str, Any]:
    txt_path = get_extracted_text_path(extraction_id)
    text = read_txt_file(txt_path)
    split_strategy = analyze_split_strategy(text)

    strategy_path = get_split_strategy_path(extraction_id)
    payload = {
        "extraction_id": extraction_id,
        "source_txt_path": str(txt_path),
        "strategy_path": str(strategy_path),
        "strategy": split_strategy,
        "next_stage": "chunk_generation",
    }
    write_json(strategy_path, payload)

    return {
        "success": True,
        "message": "切分策略分析完成，结果已保存供后续后端流程使用",
        "extraction_id": extraction_id,
        "source_txt_path": str(txt_path),
        "strategy_path": str(strategy_path),
        "strategy": split_strategy,
        "next_stage": "chunk_generation",
    }


def execute_chunking_from_extraction(extraction_id: str) -> dict[str, Any]:
    txt_path = get_extracted_text_path(extraction_id)
    strategy_path = get_split_strategy_path(extraction_id)

    raw_text = read_txt_file(txt_path)
    text = clean_text_for_chunking(raw_text)
    strategy_payload = read_json(strategy_path)
    config = get_executable_config(strategy_payload)
    chunks = split_text_by_config(text, config)

    if not chunks:
        raise RuntimeError("切分失败：没有生成任何 chunk")

    checked_chunks = check_all_chunks(chunks)
    quality_report = build_quality_report(checked_chunks)
    problem_chunks = filter_problem_chunks(checked_chunks)
    report = build_split_report(checked_chunks)
    chunks_json_path = get_chunks_json_path(extraction_id)
    chunks_jsonl_path = get_chunks_jsonl_path(extraction_id)
    quality_report_path = get_chunk_quality_report_path(extraction_id)
    problem_chunks_jsonl_path = get_problem_chunks_jsonl_path(extraction_id)
    output_data = {
        "extraction_id": extraction_id,
        "source_file": str(txt_path),
        "strategy_file": str(strategy_path),
        "executable_split_config": config,
        "split_report": report,
        "quality_report": quality_report,
        "chunks": checked_chunks,
        "next_stage": "graph_extraction",
    }

    write_json(chunks_json_path, output_data)
    write_jsonl(checked_chunks, chunks_jsonl_path)
    write_json(quality_report_path, quality_report)
    write_quality_jsonl(problem_chunks, problem_chunks_jsonl_path)

    return {
        "success": True,
        "message": "文本切分完成，并已完成基础 chunk 质量验证",
        "extraction_id": extraction_id,
        "source_txt_path": str(txt_path),
        "strategy_path": str(strategy_path),
        "chunks_json_path": str(chunks_json_path),
        "chunks_jsonl_path": str(chunks_jsonl_path),
        "quality_report_path": str(quality_report_path),
        "problem_chunks_jsonl_path": str(problem_chunks_jsonl_path),
        "split_report": report,
        "quality_report": quality_report,
        "next_stage": "graph_extraction",
    }


def analyze_strategy_and_execute_chunking(extraction_id: str) -> dict[str, Any]:
    analyze_split_strategy_from_extraction(extraction_id)
    return execute_chunking_from_extraction(extraction_id)
