"""Configuration loader and models for da_agent."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from da_agent.contracts import Budgets


class ModelConfig(BaseModel):
    """Model endpoint and inference settings."""

    model_config = ConfigDict(extra="forbid")

    name: str
    provider: str = "ollama"
    base_url: str = "http://localhost:11434/v1"
    temperature: float = 0.0
    top_p: float = 1.0
    seed: int = 42


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


class AppConfig(BaseModel):
    """Root configuration model."""

    model_config = ConfigDict(extra="forbid")

    budgets: Budgets
    model: ModelConfig
    sampling: SamplingConfig
    input_limits: InputLimitsConfig
    run_trace: RunTraceConfig = Field(default_factory=RunTraceConfig)


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
