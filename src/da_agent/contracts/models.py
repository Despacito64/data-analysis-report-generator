"""Pydantic v2 data contracts shared across all da_agent modules."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONTRACT_VERSION = "0.1.0"


class SemanticType(str, Enum):
    """Semantic data type for a tabular column."""

    IDENTIFIER = "identifier"
    NUMERIC_MEASURE = "numeric_measure"
    CATEGORY = "category"
    DATE = "date"
    TEXT = "text"


class ColumnProfile(BaseModel):
    """Profile of a single dataset column."""

    model_config = ConfigDict(extra="forbid")

    name: str
    physical_type: str
    semantic_type: SemanticType
    missing_count: int = Field(ge=0)
    distinct_count: int = Field(ge=0)
    examples: list[Any] = Field(default_factory=list)


class DateCoverage(BaseModel):
    """Date span and parse diagnostic for a datetime/date column."""

    model_config = ConfigDict(extra="forbid")

    column: str
    min: str | None = None
    max: str | None = None
    parse_failures: int = Field(default=0, ge=0)


class StatBlock(BaseModel):
    """Descriptive statistics for a numeric column."""

    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=0)
    mean: float | None = None
    std: float | None = None
    min: float | None = None
    q25: float | None = None
    median: float | None = None
    q75: float | None = None
    max: float | None = None


class DatasetProfile(BaseModel):
    """Complete structural and statistical profile of an ingested dataset."""

    model_config = ConfigDict(extra="forbid")

    dataset_hash: str
    transformation_version: str
    source_name: str
    row_count: int = Field(ge=0)
    columns: list[ColumnProfile]
    duplicate_row_count: int = Field(ge=0)
    date_coverage: list[DateCoverage] = Field(default_factory=list)
    descriptive_stats: dict[str, StatBlock] = Field(default_factory=dict)
    parsing_diagnostics: list[str] = Field(default_factory=list)


class AmbiguityDecision(BaseModel):
    """Recorded resolution of an ambiguous element in a natural-language question."""

    model_config = ConfigDict(extra="forbid")

    field: str
    issue: str
    decision: str
    assumption: str | None = None


class PeriodSpec(BaseModel):
    """Temporal window specification for analysis."""

    model_config = ConfigDict(extra="forbid")

    column: str
    start: str | None = None
    end: str | None = None
    grain: str | None = None


class FilterSpec(BaseModel):
    """Deterministic filter criteria on a column."""

    model_config = ConfigDict(extra="forbid")

    column: str
    operator: str
    value: Any


class ResolvedQuestion(BaseModel):
    """Structured interpretation of a user's analytical question."""

    model_config = ConfigDict(extra="forbid")

    question_text: str
    intent: str
    metric: str | None = None
    period: PeriodSpec | None = None
    grouping: list[str] = Field(default_factory=list)
    filters: list[FilterSpec] = Field(default_factory=list)
    ambiguity_decisions: list[AmbiguityDecision] = Field(default_factory=list)
    answerable: bool
    decline_reason: str | None = None

    @model_validator(mode="after")
    def validate_answerable_and_decline_reason(self) -> "ResolvedQuestion":
        if not self.answerable and not (self.decline_reason and self.decline_reason.strip()):
            raise ValueError("decline_reason is required when answerable is False")
        return self


class ToolSpec(BaseModel):
    """Exported metadata for an allowlisted analytical tool."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    args_model: str
    args_schema: dict[str, Any]
    result_schema: dict[str, Any]
    invariants: list[str] = Field(default_factory=list)


class TaskStatus(str, Enum):
    """Lifecycle status of a plan task."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task(BaseModel):
    """Individual analytical operation in an execution plan."""

    model_config = ConfigDict(extra="forbid")

    id: str
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    plan_version: int = 1
    rationale: str


class EvidenceRecord(BaseModel):
    """Immutable audit record produced by executing a tool."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    task_id: str
    tool: str
    args_hash: str
    dataset_hash: str
    input_row_count: int = Field(ge=0)
    result_summary: dict[str, Any]
    result_schema_version: str
    invariants_checked: list[str] = Field(default_factory=list)
    valid: bool = True
    invalidated_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FailureClass(str, Enum):
    """Taxonomy of execution failures."""

    INVALID_ARGS = "invalid_args"
    UNKNOWN_TOOL = "unknown_tool"
    EMPTY_RESULT = "empty_result"
    SCHEMA_VIOLATION = "schema_violation"
    INVARIANT_VIOLATION = "invariant_violation"
    TRANSIENT = "transient"
    NO_PROGRESS = "no_progress"
    BUDGET_EXHAUSTED = "budget_exhausted"


class Failure(BaseModel):
    """Structured failure description with recovery classification."""

    model_config = ConfigDict(extra="forbid")

    failure_class: FailureClass
    recoverable: bool
    message: str
    context: dict[str, Any] = Field(default_factory=dict)
    task_id: str | None = None


class RevisionChangeType(str, Enum):
    """Type of modification applied in a plan revision."""

    ADDED = "added"
    REPLACED = "replaced"
    CANCELLED = "cancelled"


class PlanRevision(BaseModel):
    """Record of dynamic changes applied to a plan."""

    model_config = ConfigDict(extra="forbid")

    from_version: int = Field(ge=1)
    to_version: int = Field(ge=1)
    trigger_evidence_id: str | None = None
    change: RevisionChangeType
    observed_result: str
    affected_tasks: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_revision(self) -> "PlanRevision":
        if self.to_version <= self.from_version:
            raise ValueError(
                f"to_version ({self.to_version}) must be greater than from_version ({self.from_version})"
            )
        if not self.affected_tasks:
            raise ValueError("affected_tasks must not be empty in a valid PlanRevision")
        return self


class Budgets(BaseModel):
    """Execution bounds shared between baseline and dynamic agent."""

    model_config = ConfigDict(extra="forbid")

    max_llm_calls: int = Field(gt=0)
    max_tool_calls: int = Field(gt=0)
    max_replans: int = Field(ge=0)
    max_identical_retries: int = Field(ge=0)
    per_call_timeout_s: float = Field(gt=0)
    max_total_tokens: int = Field(gt=0)


class ExecutionStatus(str, Enum):
    """Terminal outcome of an analytical run."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class RunStatus(BaseModel):
    """High-level completion status and claim audit for a run."""

    model_config = ConfigDict(extra="forbid")

    status: ExecutionStatus
    reason_code: str | None = None
    reason_text: str | None = None
    dropped_claims: list[str] = Field(default_factory=list)
    unvalidated_claims: list[str] = Field(default_factory=list)


class NumericClaim(BaseModel):
    """Specific numerical claim asserted in a report finding."""

    model_config = ConfigDict(extra="forbid")

    value: float | int | str
    unit: str | None = None
    label: str
    evidence_id: str

    @field_validator("evidence_id")
    @classmethod
    def validate_evidence_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("NumericClaim must link to a non-empty evidence_id")
        return v


class Finding(BaseModel):
    """Analytical finding supported by verified numeric claims."""

    model_config = ConfigDict(extra="forbid")

    statement: str
    numeric_claims: list[NumericClaim] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    caveat: str | None = None


class Report(BaseModel):
    """Final output artifact presenting findings, charts, methods and limitations."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    dataset_hash: str
    question: str
    summary: str
    findings: list[Finding] = Field(default_factory=list)
    charts: list[dict[str, Any]] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    evidence_appendix: list[EvidenceRecord] = Field(default_factory=list)
    status: RunStatus
