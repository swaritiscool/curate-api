from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from enum import Enum


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Task(BaseModel):
    task: str
    priority: Priority
    deadline: Optional[str] = None
    source: str


class TaskData(BaseModel):
    tasks: List[Task]
    summary: str


class Meta(BaseModel):
    chunks_used: int
    tokens_used: int
    docs_processed: int


class TaskResponse(BaseModel):
    status: Literal["success", "error"]
    data: TaskData
    meta: Meta


class SummaryV1(BaseModel):
    summary: str
    key_points: List[str]


class SummaryResponse(BaseModel):
    status: Literal["success", "error"]
    data: SummaryV1
    meta: Meta


class EntityType(str, Enum):
    PERSON = "person"
    ORGANIZATION = "organization"
    DATE = "date"
    LOCATION = "location"
    OTHER = "other"


class Entity(BaseModel):
    name: str
    type: EntityType
    source: str


class EntityData(BaseModel):
    entities: List[Entity]


class EntityResponse(BaseModel):
    status: Literal["success", "error"]
    data: EntityData
    meta: Meta


class CompressChunk(BaseModel):
    chunk_id: str
    doc_id: str
    position: int
    content: str
    score: float
    doc_type: str
    tokens: int


class CompressMeta(BaseModel):
    chunks_returned: int
    tokens_before_filter: int
    tokens_after_filter: int
    reduction_pct: float
    docs_processed: int
    processing_time_ms: int


class CompressResponse(BaseModel):
    status: Literal["success", "error"]
    chunks: List[CompressChunk]
    meta: CompressMeta


class Document(BaseModel):
    id: str
    content: str


class TransformRequest(BaseModel):
    documents: List[Document]
    task: str
    schema_type: Literal["tasks_v1", "summary_v1", "entities_v1"] = Field(alias="schema")

    class Config:
        populate_by_name = True
