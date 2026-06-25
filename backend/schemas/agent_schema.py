from typing import Any

from pydantic import BaseModel, Field


class AgentChatMessage(BaseModel):
    role: str
    content: str


class WorkflowStep(BaseModel):
    id: str
    title: str
    description: str
    required_inputs: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)


class WorkflowPlan(BaseModel):
    id: str
    title: str
    intent: str
    summary: str
    steps: list[WorkflowStep] = Field(default_factory=list)
    start_question: str = "是否开始这个流程？"


class MasterAgentChatRequest(BaseModel):
    message: str
    project_id: str | None = None
    extraction_id: str | None = None
    document_summary: str | None = None
    document_text_preview: str | None = None
    user_goal: str | None = None
    selected_feature: str | None = None
    history: list[AgentChatMessage] = Field(default_factory=list)


class MasterAgentChatResponse(BaseModel):
    success: bool
    role: str = "assistant"
    agent: str = "master"
    message: str
    project_id: str | None = None
    extraction_id: str | None = None
    document_summary: str | None = None
    user_goal: str | None = None
    skill_invocation: None = None
    workflow: WorkflowPlan | None = None


class WorkflowExecutionRequest(BaseModel):
    """An explicitly approved workflow plus the project inputs needed to run it."""

    workflow: WorkflowPlan
    approved: bool = False
    project_id: str | None = None
    extraction_id: str | None = None
    document_summary: str | None = None
    user_goal: str | None = None
    entity_types: list[str] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowExecutionStep(BaseModel):
    workflow_step_id: str
    stage: str
    skill: str
    title: str
    status: str
    success: bool
    message: str = ""
    output_path: str = ""
    result: dict[str, Any] = Field(default_factory=dict)


class WorkflowExecutionResponse(BaseModel):
    success: bool
    agent: str = "workflow-executor"
    message: str
    workflow_id: str
    project_id: str | None = None
    extraction_id: str | None = None
    selected_skills: list[str] = Field(default_factory=list)
    steps: list[WorkflowExecutionStep] = Field(default_factory=list)
    final_result: dict[str, Any] = Field(default_factory=dict)
