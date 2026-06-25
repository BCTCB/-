from fastapi import APIRouter, HTTPException

from schemas.agent_schema import (
    MasterAgentChatRequest,
    MasterAgentChatResponse,
    WorkflowExecutionRequest,
    WorkflowExecutionResponse,
)
from services.master_agent_service import chat_with_master_agent
from services.workflow_execution_agent_service import execute_approved_workflow


router = APIRouter(tags=["agent"])


@router.get("/agent/health")
def agent_health():
    return {"module": "agent", "status": "ok"}


@router.get("/api/agent/health")
def api_agent_health():
    return agent_health()


@router.post("/agent/master/chat", response_model=MasterAgentChatResponse)
def master_agent_chat(request: MasterAgentChatRequest):
    try:
        return chat_with_master_agent(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"主控 Agent 对话失败：{error}") from error


@router.post("/api/agent/master/chat", response_model=MasterAgentChatResponse)
def api_master_agent_chat(request: MasterAgentChatRequest):
    return master_agent_chat(request)


async def handle_workflow_execution(request: WorkflowExecutionRequest):
    try:
        return await execute_approved_workflow(request)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Workflow 执行失败：{error}") from error


@router.post("/agent/workflow/execute", response_model=WorkflowExecutionResponse)
async def execute_workflow(request: WorkflowExecutionRequest):
    return await handle_workflow_execution(request)


@router.post("/api/agent/workflow/execute", response_model=WorkflowExecutionResponse)
async def api_execute_workflow(request: WorkflowExecutionRequest):
    return await handle_workflow_execution(request)
