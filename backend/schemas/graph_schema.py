from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str
    label: str


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str


class GraphExtractionRequest(BaseModel):
    extraction_id: str
    mode: str = "auto"
    allowed_entity_types: list[str] = Field(default_factory=list)
    allowed_relation_types: list[str] = Field(default_factory=list)


class GraphCleanRequest(BaseModel):
    extraction_id: str


class GraphMergeRequest(BaseModel):
    extraction_id: str


class GraphRelationCleanRequest(BaseModel):
    extraction_id: str


class GraphQualityReportRequest(BaseModel):
    extraction_id: str


class FinalGraphGenerateRequest(BaseModel):
    extraction_id: str
