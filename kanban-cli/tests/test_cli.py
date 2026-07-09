"""Unit tests for the ``kan`` CLI.

The CLI is a thin adapter, so we mock the shared ``KanbanClient`` (patched into
``kanban_cli.cli``) and assert: each subcommand calls the right client method with
the right args, board-id default resolution, ``--json`` vs human output, and exit
codes (success, config errors, and a mapped ``KanbanApiError``). A couple of tests
drive the real client over an ``httpx.MockTransport`` to prove the HTTP wiring.
"""
from __future__ import annotations

import json

import httpx
import pytest
from kanban_client import KanbanApiError

from kanban_cli import cli

CARD = {"ticket_number": "KAN-1", "column": "todo", "title": "Ship it", "id": 1}


class FakeClient:
    """Records method calls; returns a canned result or raises a canned error."""

    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._result = CARD if result is None else result
        self._error = error

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def _call(self, name: str, **kwargs):
        self.calls.append((name, kwargs))
        if self._error is not None:
            raise self._error
        return self._result

    def list_cards(self, **kw):
        return self._call("list_cards", **kw)

    def get_card(self, card_id):
        return self._call("get_card", card_id=card_id)

    def create_card(self, title, **kw):
        return self._call("create_card", title=title, **kw)

    def update_card(self, card_id, **kw):
        return self._call("update_card", card_id=card_id, **kw)

    def move_card(self, card_id, column, **kw):
        return self._call("move_card", card_id=card_id, column=column, **kw)

    def delete_card(self, card_id):
        return self._call("delete_card", card_id=card_id)


@pytest.fixture
def env(monkeypatch):
    """A valid environment (token set, no default board)."""
    monkeypatch.setenv("KANBAN_TOKEN", "kanban_pat_test")
    monkeypatch.delenv("KANBAN_BOARD_ID", raising=False)
    monkeypatch.delenv("KANBAN_API_URL", raising=False)


def patch_client(monkeypatch, fake: FakeClient) -> FakeClient:
    monkeypatch.setattr(cli, "KanbanClient", lambda *a, **k: fake)
    return fake


# --- each command calls the right client method with the right args ---------


def test_list_maps_all_filters(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"cards": [CARD]}))
    code = cli.run(["list", "--board", "3", "--column", "done", "--epic", "5", "--limit", "10"])
    assert code == 0
    assert fake.calls == [
        ("list_cards", {"board_id": 3, "column": "done", "epic_id": 5, "limit": 10})
    ]


def test_get_passes_card_id(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient())
    assert cli.run(["get", "42"]) == 0
    assert fake.calls == [("get_card", {"card_id": 42})]


def test_create_maps_all_options(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient())
    code = cli.run(
        [
            "create", "My story",
            "--board", "2", "--description", "d",
            "--column", "in_progress", "--points", "5",
            "--assignee", "alice", "--epic", "9",
        ]
    )
    assert code == 0
    assert fake.calls == [
        (
            "create_card",
            {
                "title": "My story",
                "board_id": 2,
                "description": "d",
                "column": "in_progress",
                "story_points": 5,
                "assignee": "alice",
                "epic_id": 9,
            },
        )
    ]


def test_update_maps_fields(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient())
    code = cli.run(["update", "7", "--title", "New", "--points", "8", "--assignee", "bob"])
    assert code == 0
    assert fake.calls == [
        (
            "update_card",
            {
                "card_id": 7,
                "title": "New",
                "description": None,
                "story_points": 8,
                "assignee": "bob",
                "epic_id": None,
            },
        )
    ]


def test_move_passes_column_and_position(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient())
    assert cli.run(["move", "7", "done", "--position", "0"]) == 0
    assert fake.calls == [("move_card", {"card_id": 7, "column": "done", "position": 0})]


def test_move_defaults_position_to_none(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient())
    assert cli.run(["move", "7", "in_progress"]) == 0
    assert fake.calls == [("move_card", {"card_id": 7, "column": "in_progress", "position": None})]


# --- board-id default resolution --------------------------------------------


def test_list_uses_board_env_default(monkeypatch, env):
    monkeypatch.setenv("KANBAN_BOARD_ID", "7")
    fake = patch_client(monkeypatch, FakeClient(result={"cards": []}))
    cli.run(["list"])
    assert fake.calls[0][1]["board_id"] == 7


def test_flag_overrides_board_env_default(monkeypatch, env):
    monkeypatch.setenv("KANBAN_BOARD_ID", "7")
    fake = patch_client(monkeypatch, FakeClient(result={"cards": []}))
    cli.run(["list", "--board", "3"])
    assert fake.calls[0][1]["board_id"] == 3


# --- delete confirmation guard ----------------------------------------------


def test_delete_requires_yes(monkeypatch, env, capsys):
    fake = patch_client(monkeypatch, FakeClient(result={"deleted": 5}))
    code = cli.run(["delete", "5"])
    assert code == cli.EXIT_ERROR
    assert fake.calls == []  # never touched the API
    assert "--yes" in capsys.readouterr().err


def test_delete_with_yes(monkeypatch, env, capsys):
    fake = patch_client(monkeypatch, FakeClient(result={"deleted": 5}))
    assert cli.run(["delete", "5", "--yes"]) == 0
    assert fake.calls == [("delete_card", {"card_id": 5})]
    assert "deleted card 5" in capsys.readouterr().out


# --- --json vs human output -------------------------------------------------


def test_json_output_is_raw(monkeypatch, env, capsys):
    patch_client(monkeypatch, FakeClient(result={"cards": [CARD]}))
    assert cli.run(["list", "--json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed == {"cards": [CARD]}


def test_json_flag_before_subcommand(monkeypatch, env, capsys):
    patch_client(monkeypatch, FakeClient())
    assert cli.run(["--json", "get", "1"]) == 0
    assert json.loads(capsys.readouterr().out) == CARD


def test_human_output_is_concise_line(monkeypatch, env, capsys):
    patch_client(monkeypatch, FakeClient(result={"cards": [CARD]}))
    cli.run(["list"])
    out = capsys.readouterr().out.strip()
    assert out == "KAN-1\ttodo\tShip it"


def test_human_output_empty_list(monkeypatch, env, capsys):
    patch_client(monkeypatch, FakeClient(result={"cards": []}))
    cli.run(["list"])
    assert capsys.readouterr().out.strip() == "(no cards)"


# --- exit codes / error mapping ---------------------------------------------


def test_missing_token_is_config_error(monkeypatch, capsys):
    monkeypatch.delenv("KANBAN_TOKEN", raising=False)
    code = cli.run(["list"])
    assert code == cli.EXIT_ERROR
    assert "KANBAN_TOKEN" in capsys.readouterr().err


@pytest.mark.parametrize(
    "status,expected",
    [
        (401, cli.EXIT_AUTH),
        (403, cli.EXIT_FORBIDDEN),
        (404, cli.EXIT_NOT_FOUND),
        (500, cli.EXIT_ERROR),
    ],
)
def test_api_error_maps_to_exit_code(monkeypatch, env, capsys, status, expected):
    patch_client(monkeypatch, FakeClient(error=KanbanApiError(status, "boom")))
    code = cli.run(["get", "1"])
    assert code == expected
    assert "kan:" in capsys.readouterr().err


def test_unexpected_error_is_general(monkeypatch, env, capsys):
    patch_client(monkeypatch, FakeClient(error=httpx.ConnectError("down")))
    assert cli.run(["get", "1"]) == cli.EXIT_ERROR
    assert "kan:" in capsys.readouterr().err


def test_usage_error_exits_two(env):
    # argparse exits (SystemExit) with code 2 on a bad invocation.
    with pytest.raises(SystemExit) as exc:
        cli.run(["move", "7", "not_a_column"])
    assert exc.value.code == cli.EXIT_USAGE


# --- real client over a MockTransport (HTTP wiring) -------------------------


def test_real_client_hits_move_endpoint(monkeypatch, env):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["content"] = json.loads(request.content)
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=CARD)

    from kanban_client import KanbanClient

    monkeypatch.setattr(
        cli,
        "KanbanClient",
        lambda url, token, **k: KanbanClient(
            url, token, transport=httpx.MockTransport(handler)
        ),
    )
    assert cli.run(["move", "7", "done", "--position", "1"]) == 0
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/v1/cards/7/move"
    assert seen["content"] == {"column": "done", "position": 1}
    assert seen["auth"] == "Bearer kanban_pat_test"
