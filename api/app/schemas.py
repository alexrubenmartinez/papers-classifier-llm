from typing import Literal

from pydantic import BaseModel, Field


class ScoreBreakdown(BaseModel):
    keyword: float = Field(..., ge=0, le=1)
    tfidf: float = Field(..., ge=0, le=1)
    sbert: float = Field(..., ge=0, le=1)
    weighted: float = Field(..., ge=0, le=1)


class PaperSummary(BaseModel):
    paper_id: str
    title: str
    year: int
    score_final: int = Field(..., ge=0, le=5)
    decision: str


class Paper(PaperSummary):
    abstract: str | None = None
    score_breakdown: ScoreBreakdown
    justification: str | None = None
    created_at: str
    minio_key: str | None = None
    tier_minio_key: str | None = None


class UploadResponse(BaseModel):
    job_id: str
    paper_id: str
    status: Literal["queued", "running", "completed", "failed"]
    stream_url: str


class JobStatus(BaseModel):
    job_id: str
    paper_id: str
    status: Literal["queued", "running", "completed", "failed"]
    stage: str
    filename: str | None = None
    created_at: str
    updated_at: str
    error: str | None = None
    type: str | None = None
    total: int | None = None
    processed: int | None = None


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]


class ChatResponse(BaseModel):
    model: str
    message: str
    total_duration_ms: int
    eval_count: int


class QueryConfig(BaseModel):
    """Configuracion de la query de scoring. Singleton en Mongo (collection `config`)."""
    topic_name: str
    query_text: str
    axes: dict[str, list[str]]
    weights: dict[str, float]
    year_range: list[int] = Field(..., min_length=2, max_length=2)
    thresholds: dict[str, float] | None = None
    updated_at: str | None = None


class QueryConfigUpdate(BaseModel):
    """Body de PUT /config. Todos los campos opcionales."""
    topic_name: str | None = None
    query_text: str | None = None
    axes: dict[str, list[str]] | None = None
    weights: dict[str, float] | None = None
    year_range: list[int] | None = None
    thresholds: dict[str, float] | None = None


class ReclassifyResponse(BaseModel):
    job_id: str
    type: Literal["reclassify_all"]
    total: int
    stream_url: str


class ImportRequest(BaseModel):
    """Body de POST /papers/import. Recorre un prefijo de MinIO e ingesta cada PDF."""
    source_prefix: str = Field(..., description="Prefijo del bucket. Ej: 'grupo3_ciberseguridad/bronze/papers/'")
    justify: Literal["none", "lazy", "auto"] = "none"
    limit: int | None = Field(None, ge=1, le=5000, description="Si se da, importa solo los primeros N PDFs del prefijo.")


class ImportResponse(BaseModel):
    job_id: str
    type: Literal["import_batch"]
    total: int
    stream_url: str


class JustifyRequest(BaseModel):
    """Body de POST /justify (batch). Pasar uno de los tres filtros."""
    paper_ids: list[str] | None = None
    top: int | None = Field(None, ge=1, le=2000)
    min_score: int | None = Field(None, ge=0, le=5)


class JustifyResponse(BaseModel):
    paper_id: str
    justification: str
    generated_in_ms: int


class JustifyBatchResponse(BaseModel):
    job_id: str
    type: Literal["justify_batch"]
    total: int
    stream_url: str
