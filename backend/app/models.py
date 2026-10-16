"""Request models for the public RepoPilot API."""

from pydantic import BaseModel, Field


class RepositoryRequest(BaseModel):
    repo_url: str = Field(min_length=1, max_length=500)
    force_refresh: bool = False


class FileRequest(RepositoryRequest):
    path: str = Field(min_length=1, max_length=500)


class AskRequest(RepositoryRequest):
    question: str = Field(min_length=2, max_length=2000)
    selected_path: str | None = Field(default=None, max_length=500)


class ExplainRequest(FileRequest):
    question: str | None = Field(default=None, max_length=1000)
