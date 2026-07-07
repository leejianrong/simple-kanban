"""Pydantic v2 schemas — the API's request/response contract (CONTEXT §4, ADR 0006).

Slice 1 only needs CardCreate and CardRead. CardUpdate / CardMove arrive in later slices.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ColumnEnum(str, Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"


STORY_POINTS = {1, 2, 3, 5, 8, 13}


class CardCreate(BaseModel):
    title: Annotated[str, Field(min_length=1)]
    description: str | None = None
    column: ColumnEnum = ColumnEnum.todo
    story_points: int | None = None
    assignee: str | None = None

    @field_validator("title")
    @classmethod
    def title_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("title must not be empty")
        return v

    @field_validator("story_points")
    @classmethod
    def story_points_in_set(cls, v: int | None) -> int | None:
        if v is not None and v not in STORY_POINTS:
            raise ValueError(f"story_points must be one of {sorted(STORY_POINTS)} or null")
        return v


class CardMove(BaseModel):
    column: ColumnEnum
    position: int | None = Field(default=None, ge=0)


class CardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_number: str
    title: str
    description: str | None
    column: ColumnEnum
    position: int
    story_points: int | None
    assignee: str | None
    created_at: datetime
    updated_at: datetime
