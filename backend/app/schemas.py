from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class CloneRequest(BaseModel):
    repo_url: str
    repo_name: str


class RepositoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    url: str
    status: str
    created_at: datetime
    file_count: int = 0
    symbol_count: int = 0


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    repository_id: int | None
    kind: str
    status: str
    message: str
    error: str | None
    result: dict | None
    created_at: datetime
    finished_at: datetime | None


class AskRequest(BaseModel):
    question: str


class TestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    symbol_id: int
    code: str
    source: str
    status: str
    output: str
    exit_code: int | None
    created_at: datetime
