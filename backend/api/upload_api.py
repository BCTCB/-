import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from services.pdf_service import convert_uploaded_pdf_to_txt


router = APIRouter(tags=["upload"])


@router.get("/upload/health")
def upload_health():
    return {"module": "upload", "status": "ok"}


def parse_json_form_field(value: str | None, field_name: str):
    if not value:
        return None

    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail=f"{field_name} 不是合法 JSON") from error


async def handle_pdf_to_txt(
    file: UploadFile,
    entity_types: str | None = None,
    relations: str | None = None,
):
    try:
        result = await convert_uploaded_pdf_to_txt(
            file=file,
            entity_types=parse_json_form_field(entity_types, "entity_types"),
            relations=parse_json_form_field(relations, "relations"),
        )
        return JSONResponse(content=result)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"PDF 转 TXT 失败：{error}") from error


@router.post("/api/pdf/to-txt")
async def api_pdf_to_txt(
    file: UploadFile = File(...),
    entity_types: str | None = Form(default=None),
    relations: str | None = Form(default=None),
):
    return await handle_pdf_to_txt(file, entity_types, relations)


@router.post("/upload/pdf/to-txt")
async def upload_pdf_to_txt(
    file: UploadFile = File(...),
    entity_types: str | None = Form(default=None),
    relations: str | None = Form(default=None),
):
    return await handle_pdf_to_txt(file, entity_types, relations)
