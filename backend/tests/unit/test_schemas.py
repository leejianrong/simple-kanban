"""Unit tests for the Pydantic request schemas (app.schemas).

Pure validation logic — no database, no HTTP, no Docker. These exercise the
CardCreate/CardUpdate validators (title non-empty, story_points in the allowed
set, column enum) directly, so they run in milliseconds in the `unit` CI job.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import (
    CardCreate,
    CardRead,
    CardUpdate,
    ColumnEnum,
    DependencyCreate,
    EpicCreate,
)


def test_create_minimal_defaults_to_todo():
    card = CardCreate(title="Write docs")
    assert card.column is ColumnEnum.todo
    assert card.description is None
    assert card.story_points is None
    # No epic link by default (that the id references an existing epic is checked
    # in the router, not here).
    assert card.epic_id is None


def test_create_accepts_epic_id():
    assert CardCreate(title="ok", epic_id=7).epic_id == 7


def test_epic_create_requires_non_empty_name():
    assert EpicCreate(name="Mobile Checkout").description is None
    for bad_name in ("", "   ", "\t\n"):
        with pytest.raises(ValidationError):
            EpicCreate(name=bad_name)


@pytest.mark.parametrize("bad_title", ["", "   ", "\t\n"])
def test_create_rejects_empty_or_whitespace_title(bad_title):
    with pytest.raises(ValidationError):
        CardCreate(title=bad_title)


@pytest.mark.parametrize("points", [1, 2, 3, 5, 8, 13, None])
def test_create_accepts_valid_story_points(points):
    assert CardCreate(title="ok", story_points=points).story_points == points


@pytest.mark.parametrize("points", [0, 4, 6, 7, 100, -1])
def test_create_rejects_story_points_outside_set(points):
    with pytest.raises(ValidationError):
        CardCreate(title="ok", story_points=points)


def test_create_rejects_unknown_column():
    with pytest.raises(ValidationError):
        CardCreate(title="ok", column="archived")


def test_update_allows_none_title_but_not_empty():
    # None means "field not being edited" and is allowed.
    assert CardUpdate(title=None).title is None
    # An explicit empty/whitespace title is a validation error.
    with pytest.raises(ValidationError):
        CardUpdate(title="   ")


# --- card dependencies (KAN-28) --------------------------------------------


def test_card_read_dependency_arrays_default_empty():
    # The router populates these from the card_dependency table; when it can't
    # (or there are none) they default to empty rather than error out.
    card = CardRead(
        id=1,
        ticket_number="KAN-1",
        board_id=1,
        title="t",
        description=None,
        column=ColumnEnum.todo,
        position=0,
        story_points=None,
        assignee=None,
        epic_id=None,
        created_at="2026-07-09T00:00:00Z",
        updated_at="2026-07-09T00:00:00Z",
    )
    assert card.blocked_by == []
    assert card.blocks == []


def test_dependency_create_requires_blocker_id():
    assert DependencyCreate(blocker_id=5).blocker_id == 5
    with pytest.raises(ValidationError):
        DependencyCreate()
