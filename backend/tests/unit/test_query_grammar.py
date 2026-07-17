"""Unit tests for the M5 V14 (KAN-247) query grammar — the sort-spec parser and
the CardQuery schema.

Pure validation logic — no database, no HTTP, no Docker (the ``unit`` CI job).
``app.schemas`` imports no engine, so a module-top import is safe here (unlike the
integration suite; see the PR #17 trap).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import (
    CARD_SORT_FIELDS,
    CardQuery,
    PriorityEnum,
    SavedViewCreate,
    parse_sort_spec,
)

# --- parse_sort_spec --------------------------------------------------------


def test_single_ascending_key():
    assert parse_sort_spec("priority") == [("priority", False)]


def test_leading_dash_is_descending():
    assert parse_sort_spec("-due_date") == [("due_date", True)]


def test_multiple_keys_preserve_order():
    assert parse_sort_spec("-priority,position") == [
        ("priority", True),
        ("position", False),
    ]


def test_whitespace_is_tolerated():
    assert parse_sort_spec(" -priority ,  position ") == [
        ("priority", True),
        ("position", False),
    ]


@pytest.mark.parametrize("field", CARD_SORT_FIELDS)
def test_every_allowlisted_field_parses(field):
    assert parse_sort_spec(field) == [(field, False)]


def test_unknown_field_rejected():
    with pytest.raises(ValueError):
        parse_sort_spec("bogus")


def test_empty_key_rejected():
    with pytest.raises(ValueError):
        parse_sort_spec("")
    with pytest.raises(ValueError):
        parse_sort_spec("priority,")
    with pytest.raises(ValueError):
        parse_sort_spec("-")


# --- CardQuery --------------------------------------------------------------


def test_empty_query_is_all_none():
    q = CardQuery()
    assert q.model_dump(exclude_none=True) == {}


def test_valid_filters_and_sort():
    q = CardQuery(priority="high", assignee="agent-7", sort="-priority,position")
    assert q.priority is PriorityEnum.high
    assert q.assignee == "agent-7"
    assert q.sort == "-priority,position"


def test_bad_sort_field_is_a_validation_error():
    with pytest.raises(ValidationError):
        CardQuery(sort="nope")


def test_bad_priority_is_a_validation_error():
    with pytest.raises(ValidationError):
        CardQuery(priority="critical")


def test_unknown_key_is_rejected():
    # extra='forbid' — a stored query can't smuggle an unknown key.
    with pytest.raises(ValidationError):
        CardQuery(color="red")


def test_query_dumps_json_ready_values():
    # mode="json" turns enums into their .value and datetimes into ISO strings, so
    # the stored JSON replays verbatim as GET /cards query params.
    q = CardQuery(column="todo", priority="urgent", needs_human=True)
    dumped = q.model_dump(mode="json", exclude_none=True)
    assert dumped == {"column": "todo", "priority": "urgent", "needs_human": True}


# --- SavedViewCreate --------------------------------------------------------


def test_saved_view_defaults_to_empty_query():
    v = SavedViewCreate(name="All")
    assert v.query.model_dump(exclude_none=True) == {}


def test_saved_view_name_must_be_non_empty():
    with pytest.raises(ValidationError):
        SavedViewCreate(name="   ")


def test_saved_view_rejects_bad_query():
    with pytest.raises(ValidationError):
        SavedViewCreate(name="Bad", query={"sort": "nope"})
