import re
import uuid
from pathlib import Path
from typing import Any, List

import fitz
from fastapi import HTTPException, UploadFile

from config import EXTRACTED_TEXT_DIR, UPLOAD_DIR
from utils.json_utils import write_json


def normalize_text(text: str) -> str:
    """处理 PDF 提取时常见的异常字符、全角字符和空格。"""

    replacements = {
        "ꎬ": "，",
        "ꎻ": "；",
        "ꎮ": "。",
        "􀆰": ".",
        "􀆺": "…",
        "､": "，",
        "｡": "。",
        "﹐": "，",
        "﹑": "、",
        "．": "。",
        "﹒": "。",
        "\u3000": " ",
        "\xa0": " ",
        "ＩＳＢＮ": "ISBN",
        "ＣＩＰ": "CIP",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    full_width_digits = "０１２３４５６７８９"
    half_width_digits = "0123456789"
    for full_width, half_width in zip(full_width_digits, half_width_digits):
        text = text.replace(full_width, half_width)

    full_width_upper = "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
    half_width_upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for full_width, half_width in zip(full_width_upper, half_width_upper):
        text = text.replace(full_width, half_width)

    full_width_lower = "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
    half_width_lower = "abcdefghijklmnopqrstuvwxyz"
    for full_width, half_width in zip(full_width_lower, half_width_lower):
        text = text.replace(full_width, half_width)

    return text


def clean_page_text(text: str) -> str:
    """清洗单页文本，删除空行、页码、页眉页脚和出版信息。"""

    lines = text.splitlines()
    cleaned_lines = []

    useless_keywords = [
        "版权所有",
        "定价",
        "ISBN",
        "CIP",
        "图书在版编目",
        "出版发行",
        "责任编辑",
        "责任校对",
        "封面设计",
        "策划编辑",
        "微信公众号",
    ]

    for line in lines:
        line = line.strip()

        if not line:
            continue

        if re.fullmatch(r"-?\s*\d+\s*-?", line):
            continue

        if re.fullmatch(r"第\s*\d+\s*页", line):
            continue

        if re.fullmatch(r"Page\s*\d+", line, flags=re.IGNORECASE):
            continue

        if re.fullmatch(r"[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+", line):
            continue

        if any(keyword in line for keyword in useless_keywords):
            continue

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def remove_repeated_lines(page_texts: List[str]) -> List[str]:
    """删除多页重复出现的短文本，常用于去除页眉、页脚。"""

    line_count = {}

    for page_text in page_texts:
        lines = {line.strip() for line in page_text.splitlines() if line.strip()}

        for line in lines:
            if len(line) <= 60:
                line_count[line] = line_count.get(line, 0) + 1

    total_pages = len(page_texts)
    repeated_lines = {
        line for line, count in line_count.items() if count >= max(3, total_pages * 0.25)
    }

    cleaned_pages = []

    for page_text in page_texts:
        new_lines = []

        for line in page_text.splitlines():
            line = line.strip()

            if not line:
                continue

            if line in repeated_lines:
                continue

            new_lines.append(line)

        cleaned_pages.append("\n".join(new_lines))

    return cleaned_pages


def merge_lines(text: str) -> str:
    """合并 PDF 提取时被错误换行的句子。"""

    lines = text.splitlines()
    merged = []
    buffer = ""

    for line in lines:
        line = line.strip()

        if not line:
            continue

        if re.match(r"第[一二三四五六七八九十\d]+章", line):
            if buffer:
                merged.append(buffer)
                buffer = ""
            merged.append(line)
            continue

        if re.match(r"[一二三四五六七八九十]+[、.．]", line):
            if buffer:
                merged.append(buffer)
                buffer = ""
            merged.append(line)
            continue

        if re.match(r"\d+[.．、]\s*", line):
            if buffer:
                merged.append(buffer)
                buffer = ""
            merged.append(line)
            continue

        if buffer and not re.search(r"[。！？；：.!?;:]$", buffer):
            buffer += line
        else:
            if buffer:
                merged.append(buffer)
            buffer = line

    if buffer:
        merged.append(buffer)

    return "\n".join(merged)


def remove_noise_lines(text: str) -> str:
    """删除明显无意义的残留行。"""

    lines = text.splitlines()
    cleaned = []

    for line in lines:
        line = line.strip()

        if not line:
            continue

        if re.fullmatch(r"[-—_=*·•●]+", line):
            continue

        if re.fullmatch(r"[A-Z\s]+", line) and len(line) > 10:
            continue

        cleaned.append(line)

    return "\n".join(cleaned)


def extract_pdf_text(pdf_path: Path) -> str:
    """从 PDF 提取文本，并进行基础清洗。"""

    if not pdf_path.exists():
        raise FileNotFoundError(f"找不到 PDF 文件：{pdf_path}")

    page_texts = []

    try:
        doc = fitz.open(pdf_path)
    except Exception as error:
        raise RuntimeError(f"PDF 打开失败：{error}") from error

    try:
        for page in doc:
            text = page.get_text("text")
            text = normalize_text(text)
            text = clean_page_text(text)
            page_texts.append(text)
    finally:
        doc.close()

    page_texts = remove_repeated_lines(page_texts)
    full_text = "\n\n".join(page_texts)
    full_text = merge_lines(full_text)
    full_text = remove_noise_lines(full_text)

    return full_text


async def save_uploaded_pdf(file: UploadFile) -> Path:
    """保存前端上传的 PDF 文件。"""

    if not file.filename:
        raise HTTPException(status_code=400, detail="没有接收到文件名")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="只支持上传 PDF 文件")

    file_id = uuid.uuid4().hex
    save_path = UPLOAD_DIR / f"{file_id}.pdf"

    content = await file.read()

    if not content:
        raise HTTPException(status_code=400, detail="上传的 PDF 文件为空")

    save_path.write_bytes(content)

    return save_path


def load_extracted_text(txt_path: str | Path) -> str:
    """供后续后端流程读取本阶段产出的 TXT。"""

    return Path(txt_path).read_text(encoding="utf-8")


async def convert_uploaded_pdf_to_txt(
    file: UploadFile,
    entity_types: List[str] | None = None,
    relations: List[dict[str, Any]] | None = None,
) -> dict:
    """保存上传的 PDF，提取文本，并写入 TXT 文件。

    本函数是后续后端流程的预处理入口。提取出的全文只写入文件，
    API 响应只返回任务和文件信息，不把全文返回给前端。
    """

    pdf_path = await save_uploaded_pdf(file)
    text = extract_pdf_text(pdf_path)

    extraction_id = pdf_path.stem
    txt_filename = f"{pdf_path.stem}.txt"
    txt_path = EXTRACTED_TEXT_DIR / txt_filename
    txt_path.write_text(text, encoding="utf-8")

    metadata_path = EXTRACTED_TEXT_DIR / f"{extraction_id}.json"
    write_json(
        metadata_path,
        {
            "extraction_id": extraction_id,
            "original_filename": file.filename,
            "pdf_path": str(pdf_path),
            "txt_path": str(txt_path),
            "text_length": len(text),
            "entity_types": entity_types or [],
            "relations": relations or [],
            "next_stage": "chunk_service",
        },
    )

    return {
        "success": True,
        "message": "PDF 已成功转换为 TXT，文本已保存供后续后端流程使用",
        "extraction_id": extraction_id,
        "original_filename": file.filename,
        "pdf_path": str(pdf_path),
        "txt_path": str(txt_path),
        "metadata_path": str(metadata_path),
        "text_length": len(text),
    }
