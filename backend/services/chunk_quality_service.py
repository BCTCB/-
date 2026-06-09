import json
import re
from pathlib import Path
from typing import Any


MIN_CHARS = 80
IDEAL_MAX_CHARS = 4000
MAX_CHARS = 6000
MIN_CONTENT_DENSITY = 0.45
PROBLEM_LEVELS = {"warning", "bad"}

INCOMPLETE_START_PATTERNS = [
    r"^(因此|所以|然后|此外|同时|另外|进一步|由此可见|综上|这说明)",
    r"^(该|其|上述|前述|这种|这些|他们|它们|为此)",
]

INCOMPLETE_END_PATTERNS = [
    r"(为|包括|如下|分别为|主要有|原因是|方法是|措施是|步骤如下|例如|即)[:：]?$",
]

GENERIC_HEADING_PATTERNS = [
    r"^第[一二三四五六七八九十百千万\d]+[章节篇部分].{0,80}$",
    r"^\d+(?:\.\d+)*[、.．]?\s+.{2,80}$",
    r"^[一二三四五六七八九十]+[、.．]\s*.{2,80}$",
    r"^[（(][一二三四五六七八九十\d]+[）)]\s*.{2,80}$",
    r"^[A-Z][、.．]\s+.{2,80}$",
]


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_non_empty_lines(text: str) -> list[str]:
    return [line.strip() for line in text.split("\n") if line.strip()]


def is_heading_line(line: str) -> bool:
    line = line.strip()

    if not line or len(line) > 160:
        return False

    return any(re.match(pattern, line) for pattern in GENERIC_HEADING_PATTERNS)


def calculate_content_density(text: str) -> float:
    lines = get_non_empty_lines(text)

    if not lines:
        return 0.0

    useful_lines = 0

    for line in lines:
        if re.fullmatch(r"\d+", line):
            continue

        if re.fullmatch(r"[\W_]+", line):
            continue

        if re.search(r"\.{3,}\s*\d+$", line):
            continue

        if len(line) <= 8 and is_heading_line(line):
            continue

        useful_lines += 1

    return useful_lines / len(lines)


def check_chunk_quality(chunk: dict[str, Any]) -> dict[str, Any]:
    checked_chunk = dict(chunk)
    content = normalize_text(str(chunk.get("content", "")))
    title = str(chunk.get("title", "")).strip()
    issues: list[str] = []

    if not content:
        issues.append("missing_content")

    if not title:
        issues.append("missing_title")

    char_count = len(content)

    if content:
        if char_count < MIN_CHARS:
            issues.append("too_short")

        if char_count > MAX_CHARS:
            issues.append("too_long")
        elif char_count > IDEAL_MAX_CHARS:
            issues.append("slightly_long")

        start_text = content[:80]
        end_text = content[-80:]

        if any(re.search(pattern, start_text) for pattern in INCOMPLETE_START_PATTERNS):
            issues.append("possible_incomplete_start")

        if any(re.search(pattern, end_text) for pattern in INCOMPLETE_END_PATTERNS):
            issues.append("possible_incomplete_end")

        if not re.search(r"[。！？.!?；;）)]$", end_text):
            issues.append("end_without_clear_punctuation")

        if calculate_content_density(content) < MIN_CONTENT_DENSITY:
            issues.append("low_content_density")

    score = calculate_score(issues)
    level = get_quality_level(score)

    checked_chunk["quality"] = {
        "score": score,
        "level": level,
        "issues": issues,
        "suggestion": get_suggestion(level, issues),
        "char_count": char_count,
        "content_density": round(calculate_content_density(content), 3) if content else 0.0,
    }

    return checked_chunk


def calculate_score(issues: list[str]) -> int:
    score = 100
    penalty_map = {
        "missing_content": 100,
        "missing_title": 15,
        "too_short": 30,
        "too_long": 30,
        "slightly_long": 10,
        "possible_incomplete_start": 15,
        "possible_incomplete_end": 15,
        "end_without_clear_punctuation": 8,
        "low_content_density": 20,
    }

    for issue in issues:
        score -= penalty_map.get(issue, 5)

    return max(0, min(100, score))


def get_quality_level(score: int) -> str:
    if score >= 90:
        return "excellent"

    if score >= 70:
        return "good"

    if score >= 50:
        return "warning"

    return "bad"


def get_suggestion(level: str, issues: list[str]) -> str:
    issue_set = set(issues)

    if "missing_content" in issue_set:
        return "discard"

    if "too_long" in issue_set:
        return "split_again"

    if "too_short" in issue_set:
        return "review_or_merge"

    if "possible_incomplete_start" in issue_set:
        return "review_or_merge_with_previous"

    if "possible_incomplete_end" in issue_set:
        return "review_or_merge_with_next"

    if "low_content_density" in issue_set:
        return "review_or_discard"

    if level in {"excellent", "good"}:
        return "keep"

    return "review"


def check_all_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [check_chunk_quality(chunk) for chunk in chunks]


def filter_problem_chunks(checked_chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        chunk
        for chunk in checked_chunks
        if chunk.get("quality", {}).get("level") in PROBLEM_LEVELS
    ]


def build_quality_report(checked_chunks: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(checked_chunks)
    problem_chunks = filter_problem_chunks(checked_chunks)
    level_count: dict[str, int] = {}
    issue_count: dict[str, int] = {}
    suggestion_count: dict[str, int] = {}
    scores: list[int] = []

    for chunk in checked_chunks:
        quality = chunk.get("quality", {})
        level = quality.get("level", "unknown")
        suggestion = quality.get("suggestion", "unknown")
        level_count[level] = level_count.get(level, 0) + 1
        suggestion_count[suggestion] = suggestion_count.get(suggestion, 0) + 1

        score = quality.get("score")
        if isinstance(score, int):
            scores.append(score)

        for issue in quality.get("issues", []):
            issue_count[issue] = issue_count.get(issue, 0) + 1

    return {
        "summary": {
            "total_chunks": total,
            "problem_chunks": len(problem_chunks),
            "problem_ratio": round(len(problem_chunks) / total, 4) if total else 0,
            "average_score": round(sum(scores) / len(scores), 2) if scores else 0,
        },
        "level_count": level_count,
        "issue_count": dict(sorted(issue_count.items(), key=lambda item: item[1], reverse=True)),
        "suggestion_count": suggestion_count,
        "problem_preview_first_20": [
            {
                "chunk_id": chunk.get("chunk_id"),
                "title": chunk.get("title"),
                "score": chunk.get("quality", {}).get("score"),
                "level": chunk.get("quality", {}).get("level"),
                "issues": chunk.get("quality", {}).get("issues"),
                "suggestion": chunk.get("quality", {}).get("suggestion"),
            }
            for chunk in problem_chunks[:20]
        ],
    }


def write_jsonl(data: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        for item in data:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")
