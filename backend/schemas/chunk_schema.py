from pydantic import BaseModel


class TextChunk(BaseModel):
    id: str
    text: str


class SplitStrategyRequest(BaseModel):
    extraction_id: str


class ChunkExecutionRequest(BaseModel):
    extraction_id: str


class RagSearchRequest(BaseModel):
    extraction_id: str
    query: str
    top_k: int = 5
    min_score: float | None = None
