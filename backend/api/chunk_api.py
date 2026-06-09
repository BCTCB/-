from fastapi import APIRouter, HTTPException

from schemas.chunk_schema import ChunkExecutionRequest, SplitStrategyRequest
from services.chunk_service import (
    analyze_split_strategy_from_extraction,
    analyze_strategy_and_execute_chunking,
    execute_chunking_from_extraction,
)


router = APIRouter(tags=["chunk"])


@router.get("/chunk/health")
def chunk_health():
    return {"module": "chunk", "status": "ok"}


@router.post("/chunk/strategy")
def create_split_strategy(request: SplitStrategyRequest):
    try:
        return analyze_split_strategy_from_extraction(request.extraction_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"切分策略分析失败：{error}") from error


@router.post("/api/chunk/strategy")
def api_create_split_strategy(request: SplitStrategyRequest):
    return create_split_strategy(request)


@router.post("/chunk/execute")
def execute_chunking(request: ChunkExecutionRequest):
    try:
        return execute_chunking_from_extraction(request.extraction_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"文本切分失败：{error}") from error


@router.post("/api/chunk/execute")
def api_execute_chunking(request: ChunkExecutionRequest):
    return execute_chunking(request)


@router.post("/chunk/run")
def run_strategy_and_chunking(request: ChunkExecutionRequest):
    try:
        return analyze_strategy_and_execute_chunking(request.extraction_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"切分流程失败：{error}") from error


@router.post("/api/chunk/run")
def api_run_strategy_and_chunking(request: ChunkExecutionRequest):
    return run_strategy_and_chunking(request)
