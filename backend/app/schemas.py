"""Pydantic v2 schemas — the API's request/response contract (CONTEXT §4, ADR 0006 + 0009).

CardCreate / CardRead for create+read; CardUpdate for field edits; CardMove for move/reorder.
Epic{Create,Update,Read} are the contract for the separate epic entity (ADR 0009).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    # The target board (M3 V7). Optional for back-compat: when omitted the router
    # falls back to the default board, so pre-board clients (the MCP server, older
    # tests) keep working. The referenced board must exist (422 otherwise).
    board_id: int | None = None

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


class LinkCreate(BaseModel):
    """Attach a work-link to a card (KAN-32): ``POST /cards/{id}/links`` with a
    ``label`` (e.g. "PR", "branch", "CI") and a ``url`` (the PR URL, branch, CI run,
    …). Both are required and non-empty."""

    label: Annotated[str, Field(min_length=1)]
    url: Annotated[str, Field(min_length=1)]

    @field_validator("label", "url")
    @classmethod
    def non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be empty")
        return v


class LinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    url: str
    created_at: datetime


class CommentCreate(BaseModel):
    """Post a note to a card (KAN-33): ``POST /cards/{id}/comments`` with a
    ``body``. Human/agent-authored intentional context — distinct from Epic 4's
    SYSTEM activity log. Required and non-empty; the author is taken from the
    request principal, never the body."""

    body: Annotated[str, Field(min_length=1)]

    @field_validator("body")
    @classmethod
    def non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("body must not be empty")
        return v


class CommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    body: str
    # The authoring user (UUID), or null once that user is deleted (SET NULL).
    author_id: uuid.UUID | None
    created_at: datetime


class CardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_number: str
    board_id: int
    title: str
    description: str | None
    column: ColumnEnum
    position: int
    story_points: int | None
    assignee: str | None
    epic_id: int | None
    # Card-to-card dependencies (KAN-28), populated by the router from the
    # card_dependency table (not ORM-mapped columns): ids of cards that block this
    # one, and ids of cards this one blocks. Empty when there are none.
    blocked_by: list[int] = []
    blocks: list[int] = []
    # Derived ready/blocked signal (KAN-29): True when this card has >=1 blocker
    # that is not yet in the ``done`` column — i.e. it is *not* actionable. A card
    # with no blockers, or whose every blocker is done, is ``blocked = False``
    # (ready). Computed by the router, not an ORM column; see ``GET /api/v1/cards``.
    blocked: bool = False
    # Work-links (KAN-32) — PR / branch / CI URLs pointing at the card's real work
    # state. Populated by the router from the card_link table (not ORM-mapped
    # columns). Empty when there are none.
    links: list[LinkRead] = []
    created_at: datetime
    updated_at: datetime


class CardTrashRead(CardRead):
    """A soft-deleted card on the trash listing path (KAN-20). Identical to
    :class:`CardRead` plus the ``deleted_at`` tombstone — exposed **only** here (the
    normal card reads stay unchanged), so the Trash view can show when each item was
    deleted and order by it."""

    deleted_at: datetime


class DependencyCreate(BaseModel):
    """Add a blocker to a card (KAN-28): ``POST /cards/{id}/dependencies`` with
    ``{"blocker_id": N}`` records that card ``{id}`` is *blocked-by* card ``N``."""

    blocker_id: int


class EpicCreate(BaseModel):
    """Create an epic (ADR 0009). Epics carry only a name + optional description —
    no column/position/assignee/story_points."""

    name: Annotated[str, Field(min_length=1)]
    description: str | None = None
    # Target board (M3 V7); optional → default board when omitted (see CardCreate).
    board_id: int | None = None

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
    board_id: int
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class EpicTrashRead(EpicRead):
    """A soft-deleted epic on the trash listing path (KAN-20). :class:`EpicRead` plus
    the ``deleted_at`` tombstone, exposed only here (normal epic reads unchanged)."""

    deleted_at: datetime


class BoardCreate(BaseModel):
    """Create a board (M3 V7, ADR 0012). Carries only a name; the owner is set
    from the session, not the request body."""

    name: Annotated[str, Field(min_length=1)]

    @field_validator("name")
    @classmethod
    def name_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v


class BoardUpdate(BaseModel):
    """Rename a board and/or toggle its auto-sync opt-ins (KAN-43). ``name`` is the
    only renamable field; ownership isn't reassignable here. ``autosync_enabled``
    turns the GitHub-webhook card auto-sync on for this board (default OFF);
    ``autosync_advance_to_done`` separately allows PR-merge to move a card to
    ``done``. All optional — only the fields sent are applied."""

    name: str | None = None
    autosync_enabled: bool | None = None
    autosync_advance_to_done: bool | None = None

    @field_validator("name")
    @classmethod
    def name_non_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("name must not be empty")
        return v


class RoleEnum(str, Enum):
    viewer = "viewer"
    editor = "editor"
    owner = "owner"


class BoardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    # The owning user (UUID), or null for an unclaimed board (e.g. the migrated
    # default board). Server-enforced ownership checks arrive in V8.
    owner_id: uuid.UUID | None
    # Auto-sync opt-ins (KAN-43); both default false.
    autosync_enabled: bool
    autosync_advance_to_done: bool
    # The *caller's* effective role on this board (KAN-15): "owner" if they own it,
    # else their board_member role (viewer/editor). Attached transiently by the
    # list router (not an ORM column), mirroring MemberRead.email; the switcher
    # uses it to badge shared boards. Null when the router doesn't compute it.
    role: RoleEnum | None = None
    created_at: datetime
    updated_at: datetime


class MemberCreate(BaseModel):
    """Add a member to a board (KAN-12): identify the user by **either** ``user_id``
    or ``email`` (exactly one), with a ``role`` (defaults to ``viewer``). The user
    must already exist; the router resolves the identity and returns 404 otherwise."""

    user_id: uuid.UUID | None = None
    email: str | None = None
    role: RoleEnum = RoleEnum.viewer

    @field_validator("email")
    @classmethod
    def email_non_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("email must not be empty")
        return v

    @model_validator(mode="after")
    def exactly_one_identity(self) -> MemberCreate:
        if (self.user_id is None) == (self.email is None):
            raise ValueError("provide exactly one of user_id or email")
        return self


class MemberUpdate(BaseModel):
    """Change a member's role (KAN-12)."""

    role: RoleEnum


class MemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    board_id: int
    user_id: uuid.UUID
    # The member's email, populated by the router from the user table (not an ORM
    # column on board_member) so the list is human-readable for the coming UI.
    email: str | None = None
    role: RoleEnum
    created_at: datetime
    updated_at: datetime


class ActivityRead(BaseModel):
    """One append-only audit record of a board-domain mutation (KAN-17 write path,
    KAN-18 read side). Mirrors the ``Activity`` model's real columns; there is no
    ``ticket_number`` on an activity row (``entity_id`` is a plain int, the entity
    may already be deleted) — the human ticket, when there is one, is embedded in
    ``summary`` (e.g. ``"created KAN-3: Fix login"``)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    board_id: int
    # The acting user (UUID), or null once that user is deleted (SET NULL).
    actor_user_id: uuid.UUID | None
    # Denormalised human handle for the actor (email / assignee), survives deletion.
    actor_label: str | None
    entity_type: str
    entity_id: int
    action: str
    summary: str
    ts: datetime


class TokenCreate(BaseModel):
    """Create a personal access token (M3 V9, ADR 0014). Only a name (and an
    optional expiry); the secret is server-generated, never client-supplied."""

    name: Annotated[str, Field(min_length=1)]
    expires_at: datetime | None = None

    @field_validator("name")
    @classmethod
    def name_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v


class TokenRead(BaseModel):
    """Token metadata — never includes the secret (only shown once, on create)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    token_prefix: str
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None


class TokenCreated(TokenRead):
    """The create-only response: metadata **plus** the raw secret, returned
    exactly once. The client must copy it now — it is not stored and cannot be
    retrieved again (R7.1)."""

    token: str
