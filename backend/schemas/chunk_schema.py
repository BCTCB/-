from pydantic import BaseModel


class TextChunk(BaseModel):
    id: str
    text: str


class SplitStrategyRequest(BaseModel):
    extraction_id: str


class ChunkExecutionRequest(BaseModel):
    extraction_id: str
