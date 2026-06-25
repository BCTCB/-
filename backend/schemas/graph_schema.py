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
    allowed_entity_types: list[str] = Field(default_factory=list)
    allowed_relation_types: list[str] = Field(default_factory=list)
    allowed_relations: list[dict[str, str]] = Field(default_factory=list)


class GraphInstantiationUpdateRequest(BaseModel):
    extraction_id: str
    nodes: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)


class OntologyDraftRequest(BaseModel):
    extraction_id: str
    document_summary: str
    user_goal: str


class OntologyUpdateRequest(BaseModel):
    extraction_id: str
    ontology: dict


class ExtractedTextUpdateRequest(BaseModel):
    extraction_id: str
    text: str


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
