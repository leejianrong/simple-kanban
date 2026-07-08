"""Pydantic v2 schemas — the API's request/response contract (CONTEXT §4, ADR 0006 + 0009).

CardCreate / CardRead for create+read; CardUpdate for field edits; CardMove for move/reorder.
Epic{Create,Update,Read} are the contract for the separate epic entity (ADR 0009).
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
    # Optional parent epic. That the id references an existing epic is checked in
    # the router (routers/cards.py), which returns 422 on violation.
    epic_id: int | None = None

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


class CardUpdate(BaseModel):
    """Field edits (BREADBOARD §3). All optional — only sent fields are applied.

    Column is intentionally absent: moving a card is done via /move, not PATCH
    (ADR 0006). ticket_number and position are not editable either. `title` may
    not be set empty/null; description/story_points/assignee accept null to clear.
    """

    title: str | None = None
    description: str | None = None
    story_points: int | None = None
    assignee: str | None = None
    # Re-link the story to a different epic, or clear it with null. The referenced
    # epic must exist; enforced in the router.
    epic_id: int | None = None

    @field_validator("title")
    @classmethod
    def title_non_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
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
    epic_id: int | None
    created_at: datetime
    updated_at: datetime


class EpicCreate(BaseModel):
    """Create an epic (ADR 0009). Epics carry only a name + optional description —
    no column/position/assignee/story_points."""

    name: Annotated[str, Field(min_length=1)]
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v


class EpicUpdate(BaseModel):
    """Field edits for an epic. All optional — only sent fields are applied."""

    name: str | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_non_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("name must not be empty")
        return v


class EpicRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_number: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
