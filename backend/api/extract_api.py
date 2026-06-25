from fastapi import APIRouter, HTTPException

from schemas.graph_schema import GraphExtractionRequest
from services.graph_extract_service import execute_graph_extraction_from_chunks


router = APIRouter(tags=["extract"])


@router.get("/extract/health")
def extract_health():
    return {"module": "extract", "status": "ok"}


@router.post("/extract/run")
def run_graph_extraction(request: GraphExtractionRequest):
    try:
        return execute_graph_extraction_from_chunks(
            extraction_id=request.extraction_id,
            mode="ontology",
            allowed_entity_types=request.allowed_entity_types,
            allowed_relation_types=request.allowed_relation_types,
            allowed_relations=request.allowed_relations,
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"本体实例化失败：{error}") from error


@router.post("/api/extract/run")
def api_run_graph_extraction(request: GraphExtractionRequest):
    return run_graph_extraction(request)
