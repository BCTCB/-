import os
import re
import shutil
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, List

import fitz
from fastapi import HTTPException, UploadFile

from config import EXTRACTED_TEXT_DIR, UPLOAD_DIR
from utils.json_utils import read_json, write_json

OCR_LANGUAGE = os.getenv("PDF_OCR_LANGUAGE", "chi_sim")
OCR_DPI = int(os.getenv("PDF_OCR_DPI", "300"))
MIN_EXTRACTED_PAGE_CHARS = int(os.getenv("PDF_MIN_EXTRACTED_PAGE_CHARS", "20"))
TESSERACT_CMD = os.getenv("PDF_TESSERACT_CMD", "")
TESSDATA_DIR = os.getenv("PDF_TESSDATA_DIR", "")
COMMON_TESSERACT_PATHS = (
    "/opt/homebrew/bin/tesseract",
    "/usr/local/bin/tesseract",
    "/usr/bin/tesseract",
)


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


def is_table_of_contents_line(line: str) -> bool:
    if not line:
        return False

    normalized = line.replace("…", ".").replace("·", ".")

    if re.fullmatch(r"目\s*录", normalized):
        return True

    has_trailing_page = bool(
        re.search(r"(?:\(|（)?\s*[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ\d]+\s*(?:\)|）)?\s*$", normalized)
    )
    has_toc_leader = bool(re.search(r"[.\-_\s]{4,}", normalized))

    return has_trailing_page and has_toc_leader


def remove_table_of_contents_lines(page_texts: List[str]) -> List[str]:
    cleaned_pages = []
    in_toc_block = False
    toc_line_count = 0

    for page_text in page_texts:
        new_lines = []

        for line in page_text.splitlines():
            line = line.strip()

            if not line:
                continue

            if re.fullmatch(r"目\s*录", line):
                in_toc_block = True
                toc_line_count = 0
                continue

            if in_toc_block:
                if is_table_of_contents_line(line):
                    toc_line_count += 1
                    continue

                if toc_line_count >= 3 and re.match(
                    r"^第\s*[一二三四五六七八九十百千万\d]+\s*章",
                    line,
                ):
                    in_toc_block = False
                elif toc_line_count < 3:
                    in_toc_block = False
                else:
                    continue

            if is_table_of_contents_line(line):
                continue

            new_lines.append(line)

        cleaned_pages.append("\n".join(new_lines))

    return cleaned_pages


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


def count_meaningful_chars(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text))


def should_use_ocr(text: str) -> bool:
    return count_meaningful_chars(text) < MIN_EXTRACTED_PAGE_CHARS


def ocr_pdf_page(page: fitz.Page) -> str:
    """将单页 PDF 渲染为图片，并用中文 OCR 识别文本。"""

    try:
        import pytesseract
        from PIL import Image
    except ImportError as error:
        raise RuntimeError(
            "PDF 文本提取结果为空，已尝试启用 OCR，但缺少 Python 依赖。"
            "请先安装 requirements.txt 中的 pytesseract 和 Pillow。"
        ) from error

    tesseract_cmd = TESSERACT_CMD or shutil.which("tesseract")
    if not tesseract_cmd:
        for candidate in COMMON_TESSERACT_PATHS:
            if Path(candidate).exists():
                tesseract_cmd = candidate
                break

    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    zoom = OCR_DPI / 72
    matrix = fitz.Matrix(zoom, zoom)
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    image = Image.open(BytesIO(pixmap.tobytes("png")))
    config = f'--tessdata-dir "{TESSDATA_DIR}"' if TESSDATA_DIR else ""

    try:
        return pytesseract.image_to_string(image, lang=OCR_LANGUAGE, config=config)
    except pytesseract.TesseractNotFoundError as error:
        raise RuntimeError(
            "PDF 文本提取结果为空，已尝试启用 OCR，但后端运行环境找不到 tesseract。"
            "请确认已安装 tesseract，或在 backend/.env 中配置 PDF_TESSERACT_CMD。"
        ) from error
    except pytesseract.TesseractError as error:
        raise RuntimeError(
            f"中文 OCR 识别失败，请确认 tesseract 已安装中文语言包 {OCR_LANGUAGE}：{error}"
        ) from error


def clean_extracted_pages(page_texts: List[str]) -> str:
    page_texts = remove_table_of_contents_lines(page_texts)
    page_texts = remove_repeated_lines(page_texts)
    full_text = "\n\n".join(page_texts)
    full_text = merge_lines(full_text)
    full_text = remove_noise_lines(full_text)

    return full_text


def extract_pdf_text_with_metadata(pdf_path: Path) -> tuple[str, dict[str, Any]]:
    """从 PDF 提取文本；PyMuPDF 无可用文字的页面自动使用中文 OCR。"""

    if not pdf_path.exists():
        raise FileNotFoundError(f"找不到 PDF 文件：{pdf_path}")

    page_texts = []
    page_results = []
    ocr_page_count = 0
    ocr_errors = []

    try:
        doc = fitz.open(pdf_path)
    except Exception as error:
        raise RuntimeError(f"PDF 打开失败：{error}") from error

    try:
        for page in doc:
            text = page.get_text("text")
            text = normalize_text(text)
            text = clean_page_text(text)
            extraction_method = "pymupdf"

            if should_use_ocr(text):
                try:
                    ocr_text = ocr_pdf_page(page)
                    ocr_text = normalize_text(ocr_text)
                    ocr_text = clean_page_text(ocr_text)

                    if count_meaningful_chars(ocr_text) > count_meaningful_chars(text):
                        text = ocr_text
                        extraction_method = "ocr"
                        ocr_page_count += 1
                except RuntimeError as error:
                    ocr_errors.append({"page": page.number + 1, "error": str(error)})

            page_texts.append(text)
            page_results.append(
                {
                    "page": page.number + 1,
                    "method": extraction_method,
                    "text_length": len(text),
                    "meaningful_chars": count_meaningful_chars(text),
                }
            )
    finally:
        doc.close()

    full_text = clean_extracted_pages(page_texts)
    if should_use_ocr(full_text) and ocr_errors:
        raise RuntimeError(ocr_errors[0]["error"])

    metadata = {
        "extraction_method": "ocr_fallback" if ocr_page_count else "pymupdf",
        "ocr_language": OCR_LANGUAGE,
        "ocr_dpi": OCR_DPI,
        "page_count": len(page_results),
        "ocr_page_count": ocr_page_count,
        "ocr_error_count": len(ocr_errors),
        "ocr_errors": ocr_errors[:10],
        "pages": page_results,
    }

    return full_text, metadata


def extract_pdf_text(pdf_path: Path) -> str:
    """从 PDF 提取文本，并进行基础清洗。"""

    text, _metadata = extract_pdf_text_with_metadata(pdf_path)
    return text


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


def get_extracted_text_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return EXTRACTED_TEXT_DIR / f"{safe_id}.txt"


def update_extracted_text(extraction_id: str, text: str) -> dict[str, Any]:
    safe_id = Path(extraction_id).name
    txt_path = get_extracted_text_path(safe_id)
    metadata_path = EXTRACTED_TEXT_DIR / f"{safe_id}.json"

    if not txt_path.exists():
        raise FileNotFoundError(f"找不到提取文本文件：{txt_path}")

    text = str(text or "").strip()
    if not text:
        raise ValueError("提取文本不能为空")

    txt_path.write_text(text, encoding="utf-8")

    if metadata_path.exists():
        metadata = read_json(metadata_path)
        if isinstance(metadata, dict):
            metadata["text_length"] = len(text)
            metadata["text_manually_edited"] = True
            write_json(metadata_path, metadata)

    return {
        "success": True,
        "message": "提取文本已更新",
        "extraction_id": safe_id,
        "txt_path": str(txt_path),
        "metadata_path": str(metadata_path),
        "text": text,
        "text_preview": text[:3000],
        "text_length": len(text),
        "next_stage": "chunk_service",
    }


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
    text, extraction_metadata = extract_pdf_text_with_metadata(pdf_path)

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
            **extraction_metadata,
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
        "text": text,
        "text_length": len(text),
        "text_preview": text[:3000],
        "extraction_method": extraction_metadata["extraction_method"],
        "ocr_page_count": extraction_metadata["ocr_page_count"],
        "ocr_error_count": extraction_metadata["ocr_error_count"],
    }
