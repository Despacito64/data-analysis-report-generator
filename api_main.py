"""Run the FastAPI backend: uv run uvicorn api_main:app --reload --port 8000"""

from da_agent.api.app import app

__all__ = ["app"]
