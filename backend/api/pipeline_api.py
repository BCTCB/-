import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from services.pipeline_service import run_pdf_to_final_graph_pipeline
from services.pipeline_skill_service import list_pipeline_skills


router = APIRouter(tags=["pipeline"])


@router.get("/pipeline/health")
def pipeline_health():
    return {"module": "pipeline", "status": "ok"}


@router.get("/pipeline/skills")
def pipeline_skills():
    return {
        "success": True,
        "skills": list_pipeline_skills(),
    }


@router.get("/api/pipeline/skills")
def api_pipeline_skills():
    return pipeline_skills()


def parse_json_form_field(value: str | None, field_name: str):
    if not value:
        return None

    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail=f"{field_name} 不是合法 JSON") from error


async def handle_pdf_to_final_graph(
    file: UploadFile,
    document_summary: str,
    user_goal: str,
    entity_types: str | None = None,
    relations: str | None = None,
    allowed_entity_types: str | None = None,
    allowed_relation_types: str | None = None,
):
    try:
        return await run_pdf_to_final_graph_pipeline(
            file=file,
            document_summary=document_summary,
            user_goal=user_goal,
            entity_types=parse_json_form_field(entity_types, "entity_types"),
            relations=parse_json_form_field(relations, "relations"),
            allowed_entity_types=parse_json_form_field(
                allowed_entity_types,
                "allowed_entity_types",
            ),
            allowed_relation_types=parse_json_form_field(
                allowed_relation_types,
                "allowed_relation_types",
            ),
        )
    except HTTPException:
        raise
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"一键知识图谱生成失败：{error}") from error


@router.post("/pipeline/pdf-to-graph")
async def pdf_to_final_graph(
    file: UploadFile = File(...),
    document_summary: str = Form(...),
    user_goal: str = Form(...),
    entity_types: str | None = Form(default=None),
    relations: str | None = Form(default=None),
    allowed_entity_types: str | None = Form(default=None),
    allowed_relation_types: str | None = Form(default=None),
):
    return await handle_pdf_to_final_graph(
        file=file,
        document_summary=document_summary,
        user_goal=user_goal,
        entity_types=entity_types,
        relations=relations,
        allowed_entity_types=allowed_entity_types,
        allowed_relation_types=allowed_relation_types,
    )


@router.post("/api/pipeline/pdf-to-graph")
async def api_pdf_to_final_graph(
    file: UploadFile = File(...),
    document_summary: str = Form(...),
    user_goal: str = Form(...),
    entity_types: str | None = Form(default=None),
    relations: str | None = Form(default=None),
    allowed_entity_types: str | None = Form(default=None),
    allowed_relation_types: str | None = Form(default=None),
):
    return await handle_pdf_to_final_graph(
        file=file,
        document_summary=document_summary,
        user_goal=user_goal,
        entity_types=entity_types,
        relations=relations,
        allowed_entity_types=allowed_entity_types,
        allowed_relation_types=allowed_relation_types,
    )
