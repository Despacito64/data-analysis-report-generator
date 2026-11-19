"""Configuration loader and models for da_agent."""

from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from da_agent.contracts import Budgets


class FindingDropPolicy(str, Enum):
    """Policy for findings containing unsupported or ambiguous claims."""

    DROP_FINDING = "drop_finding"
    REMOVE_CLAIM = "remove_claim"


class ClaimValidationConfig(BaseModel):
    """Tolerance, rounding, recomputation, and drop policy settings for claim validation."""

    model_config = ConfigDict(extra="forbid")

    rtol: float = Field(default=0.001, ge=0.0)
    atol: float = Field(default=0.01, ge=0.0)
    rounding_digits: int = Field(default=4, ge=0)
    allow_recomputation: bool = Field(default=True)
    drop_policy: FindingDropPolicy = Field(default=FindingDropPolicy.DROP_FINDING)


class RecoveryLimits(BaseModel):
    """Execution caps for retries, per-task repairs, and plan revisions."""

    model_config = ConfigDict(extra="forbid")

    identical_retry_cap: int = Field(default=2, ge=0)
    repair_attempts_per_task: int = Field(default=2, ge=0)
    replans_per_question: int = Field(default=3, ge=0)


class ModelConfig(BaseModel):
    """Model endpoint and inference settings."""

    model_config = ConfigDict(extra="forbid")

    name: str
    provider: str = "ollama"
    base_url: str = "http://localhost:11434/v1"
    temperature: float = 0.0
    top_p: float = 1.0
    seed: int = 42
    answer_narrative_enabled: bool = True


class SamplingConfig(BaseModel):
    """Sampling settings for deterministic runs."""

    model_config = ConfigDict(extra="forbid")

    seed: int = 42
    temperature: float = 0.0


class InputLimitsConfig(BaseModel):
    """Input guardrail thresholds."""

    model_config = ConfigDict(extra="forbid")

    max_file_size_mb: float = Field(default=50.0, gt=0)
    max_rows: int = Field(default=100000, gt=0)
    allowed_extensions: list[str] = Field(default_factory=lambda: [".csv", ".xlsx"])


class RunTraceConfig(BaseModel):
    """Run trace storage settings."""

    model_config = ConfigDict(extra="forbid")

    base_dir: str = "runs"


class EvaluationConfig(BaseModel):
    """Local benchmark limits and Ollama diagnostics settings."""

    model_config = ConfigDict(extra="forbid")

    per_question_budget_s: float = Field(default=300.0, gt=0)
    overall_timeout_s: float = Field(default=7200.0, gt=0)
    max_repair_attempts: int = Field(default=2, ge=0)
    max_llm_calls_per_question: int = Field(default=8, gt=0)
    thinking_enabled: bool = False
    keep_alive: str = "10m"


class AppConfig(BaseModel):
    """Root configuration model."""

    model_config = ConfigDict(extra="forbid")

    budgets: Budgets
    model: ModelConfig
    sampling: SamplingConfig
    input_limits: InputLimitsConfig
    run_trace: RunTraceConfig = Field(default_factory=RunTraceConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    claim_validation: ClaimValidationConfig = Field(default_factory=ClaimValidationConfig)
    recovery_limits: RecoveryLimits = Field(default_factory=RecoveryLimits)


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load and validate configuration from a YAML file."""
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise TypeError(f"Invalid YAML content in {config_path}: expected mapping")

    return AppConfig.model_validate(data)
