"""Unit tests for the ``kan`` CLI.

The CLI is a thin adapter, so we mock the shared ``KanbanClient`` (patched into
``kanban_cli.cli``) and assert: each subcommand calls the right client method with
the right args, board-id default resolution, ``--json`` vs human output, and exit
codes (success, config errors, and a mapped ``KanbanApiError``). A couple of tests
drive the real client over an ``httpx.MockTransport`` to prove the HTTP wiring.
"""
from __future__ import annotations

import io
import json

import httpx
import pytest
from kanban_client import KanbanApiError

from kanban_cli import cli, config

# The real find_mcp_json, captured before the autouse fixture patches it out — so
# the test that exercises the upward walk itself can reach the genuine impl.
_REAL_FIND_MCP_JSON = config.find_mcp_json

CARD = {"ticket_number": "KAN-1", "column": "todo", "title": "Ship it", "id": 1}
EPIC = {"ticket_number": "EPIC-1", "name": "Onboarding", "description": "d", "id": 1}
BOARD = {"id": 2, "name": "Roadmap", "owner_id": None}


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

    def _call(self, method: str, **kwargs):
        self.calls.append((method, kwargs))
        if self._error is not None:
            raise self._error
        return self._result

    def warmup(self):
        return self._call("warmup")

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

    def list_boards(self):
        return self._call("list_boards")

    def create_board(self, name):
        return self._call("create_board", name=name)

    def list_epics(self, **kw):
        return self._call("list_epics", **kw)

    def create_epic(self, name, **kw):
        return self._call("create_epic", name=name, **kw)

    def update_epic(self, epic_id, **kw):
        return self._call("update_epic", epic_id=epic_id, **kw)

    def delete_epic(self, epic_id):
        return self._call("delete_epic", epic_id=epic_id)

    def list_labels(self, board_id):
        return self._call("list_labels", board_id=board_id)

    def create_label(self, board_id, name, color):
        return self._call("create_label", board_id=board_id, name=name, color=color)

    def delete_label(self, label_id):
        return self._call("delete_label", label_id=label_id)

    def dispatch(self, board_id, **kw):
        return self._call("dispatch", board_id=board_id, **kw)

    def next_ready(self, board_id, **kw):
        return self._call("next_ready", board_id=board_id, **kw)

    def flag_needs_human(self, card_id, **kw):
        return self._call("flag_needs_human", card_id=card_id, **kw)

    def resolve_card(self, card_id):
        return self._call("resolve_card", card_id=card_id)

    def board_metrics(self, board_id, **kw):
        return self._call("board_metrics", board_id=board_id, **kw)

    def list_activity(self, board_id, **kw):
        return self._call("list_activity", board_id=board_id, **kw)

    def list_views(self, board_id):
        return self._call("list_views", board_id=board_id)

    def create_view(self, board_id, name, query):
        return self._call("create_view", board_id=board_id, name=name, query=query)

    def delete_view(self, board_id, view_id):
        return self._call("delete_view", board_id=board_id, view_id=view_id)

    def update_cards(self, updates):
        return self._call("update_cards", updates=updates)

    def list_templates(self, board_id):
        return self._call("list_templates", board_id=board_id)

    def create_template(self, board_id, name, cards):
        return self._call("create_template", board_id=board_id, name=name, cards=cards)

    def delete_template(self, board_id, template_id):
        return self._call("delete_template", board_id=board_id, template_id=template_id)

    def apply_template(self, board_id, template_id):
        return self._call("apply_template", board_id=board_id, template_id=template_id)

    def add_dependency(self, card_id, blocker_id):
        return self._call("add_dependency", card_id=card_id, blocker_id=blocker_id)

    def remove_dependency(self, card_id, blocker_id):
        return self._call("remove_dependency", card_id=card_id, blocker_id=blocker_id)

    def list_dependencies(self, card_id):
        return self._call("list_dependencies", card_id=card_id)

    def add_link(self, card_id, label, url):
        return self._call("add_link", card_id=card_id, label=label, url=url)

    def remove_link(self, card_id, link_id):
        return self._call("remove_link", card_id=card_id, link_id=link_id)

    def add_comment(self, card_id, body):
        return self._call("add_comment", card_id=card_id, body=body)

    def list_comments(self, card_id):
        return self._call("list_comments", card_id=card_id)


@pytest.fixture(autouse=True)
def isolate_config(monkeypatch, tmp_path):
    """Keep every test hermetic w.r.t. config *discovery*. The suite runs inside the
    repo tree, which has a real ``.mcp.json`` (and a developer may have a real
    ``~/.config/kan/config.toml``); without this, ``load_config`` would silently
    resolve a token from those and defeat the 'no token → error' tests. Point
    ``XDG_CONFIG_HOME`` at an empty tmp dir and disable ``.mcp.json`` discovery by
    default; tests exercising those sources re-enable them explicitly."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr("kanban_cli.config.find_mcp_json", lambda *a, **k: None)


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
        (
            "list_cards",
            {
                "board_id": 3,
                "column": "done",
                "epic_id": 5,
                "priority": None,
                "label": None,
                "due_before": None,
                "overdue": None,
                "needs_human": None,
                "assignee": None,
                "q": None,
                "sort": None,
                "limit": 10,
            },
        )
    ]


def test_list_maps_card_field_filters(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"cards": [CARD]}))
    code = cli.run(
        ["list", "--priority", "high", "--label", "4", "--due-before", "2026-08-01", "--overdue"]
    )
    assert code == 0
    call = fake.calls[0][1]
    assert call["priority"] == "high"
    assert call["label"] == 4
    assert call["due_before"] == "2026-08-01"
    assert call["overdue"] is True


def test_list_maps_assignee_and_sort(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"cards": [CARD]}))
    code = cli.run(["list", "--assignee", "agent-7", "--sort=-priority,position"])
    assert code == 0
    call = fake.calls[0][1]
    assert call["assignee"] == "agent-7"
    assert call["sort"] == "-priority,position"


def test_list_maps_q_search(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"cards": [CARD]}))
    code = cli.run(["list", "--q", "login flow"])
    assert code == 0
    assert fake.calls[0][1]["q"] == "login flow"


def test_view_list_calls_client(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"views": []}))
    code = cli.run(["view", "list", "--board", "3"])
    assert code == 0
    assert fake.calls == [("list_views", {"board_id": 3})]


def test_view_create_assembles_query_from_flags(monkeypatch, env):
    fake = patch_client(
        monkeypatch, FakeClient(result={"id": 1, "name": "mine", "query": {}})
    )
    code = cli.run(
        ["view", "create", "mine", "--board", "3", "--priority", "high",
         "--assignee", "me", "--sort=-priority"]
    )
    assert code == 0
    assert fake.calls == [
        (
            "create_view",
            {
                "board_id": 3,
                "name": "mine",
                "query": {"priority": "high", "assignee": "me", "sort": "-priority"},
            },
        )
    ]


def test_view_delete_requires_yes(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"deleted": 5}))
    # Without --yes the CLI refuses (config error → exit 1), no client call.
    assert cli.run(["view", "delete", "5", "--board", "3"]) == 1
    assert fake.calls == []
    # With --yes it deletes.
    assert cli.run(["view", "delete", "5", "--board", "3", "--yes"]) == 0
    assert fake.calls == [("delete_view", {"board_id": 3, "view_id": 5})]


# --- batch update + templates (M5 V19 / KAN-252) ---------------------------


def test_batch_update_parses_json_array(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"updated": []}))
    code = cli.run(["batch-update", '[{"id": 1, "assignee": "me"}, {"id": 2, "priority": "high"}]'])
    assert code == 0
    assert fake.calls == [
        (
            "update_cards",
            {"updates": [{"id": 1, "assignee": "me"}, {"id": 2, "priority": "high"}]},
        )
    ]


def test_batch_update_rejects_non_array(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"updated": []}))
    # A JSON object (not an array) is a usage error → exit 1, no client call.
    assert cli.run(["batch-update", '{"id": 1}']) == 1
    assert fake.calls == []


def test_template_list_calls_client(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"templates": []}))
    assert cli.run(["template", "list", "--board", "3"]) == 0
    assert fake.calls == [("list_templates", {"board_id": 3})]


def test_template_create_parses_cards_json(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"id": 7}))
    code = cli.run(
        ["template", "create", "sprint", "--board", "3", "--cards", '[{"title": "A"}]']
    )
    assert code == 0
    assert fake.calls == [
        ("create_template", {"board_id": 3, "name": "sprint", "cards": [{"title": "A"}]})
    ]


def test_template_apply_calls_client(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"created": []}))
    assert cli.run(["template", "apply", "7", "--board", "3"]) == 0
    assert fake.calls == [("apply_template", {"board_id": 3, "template_id": 7})]


def test_template_delete_requires_yes(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"deleted": 7}))
    assert cli.run(["template", "delete", "7", "--board", "3"]) == 1
    assert fake.calls == []
    assert cli.run(["template", "delete", "7", "--board", "3", "--yes"]) == 0
    assert fake.calls == [("delete_template", {"board_id": 3, "template_id": 7})]


def test_list_needs_human_filter(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"cards": [CARD]}))
    assert cli.run(["list", "--needs-human"]) == 0
    assert fake.calls[0][1]["needs_human"] is True


def test_needs_human_with_note(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient())
    assert cli.run(["needs-human", "1", "--note", "decide the region"]) == 0
    assert fake.calls == [
        ("flag_needs_human", {"card_id": 1, "attention_note": "decide the region"})
    ]


def test_needs_human_without_note(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient())
    assert cli.run(["needs-human", "2"]) == 0
    assert fake.calls == [("flag_needs_human", {"card_id": 2, "attention_note": None})]


METRICS = {
    "board_id": 2,
    "generated_at": "2026-07-17T12:00:00Z",
    "since": None,
    "until": "2026-07-17T12:00:00Z",
    "throughput": 2,
    "cycle_time": {
        "count": 2,
        "avg_seconds": 7200.0,
        "median_seconds": 7200.0,
        "p90_seconds": 10800.0,
    },
    "aging_wip": {
        "count": 1,
        "avg_seconds": 1800.0,
        "max_seconds": 1800.0,
        "items": [
            {
                "card_id": 3,
                "ticket_number": "KAN-3",
                "assignee": "agent-b",
                "age_seconds": 1800.0,
            }
        ],
    },
    "by_assignee": [{"assignee": "agent-a", "throughput": 2, "wip": 0}],
}


def test_metrics_maps_board_and_window(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result=METRICS))
    assert cli.run(["metrics", "--board", "2", "--window", "7d"]) == 0
    assert fake.calls == [
        ("board_metrics", {"board_id": 2, "since": None, "window": "7d"})
    ]


def test_metrics_requires_a_board(monkeypatch, env, capsys):
    patch_client(monkeypatch, FakeClient(result=METRICS))
    assert cli.run(["metrics"]) == 1  # no --board, no KANBAN_BOARD_ID → refused
    assert "board is required" in capsys.readouterr().err


def test_metrics_human_output(monkeypatch, env, capsys):
    patch_client(monkeypatch, FakeClient(result=METRICS))
    assert cli.run(["metrics", "--board", "2"]) == 0
    out = capsys.readouterr().out
    assert "throughput:  2 done" in out
    assert "cycle time:" in out
    assert "KAN-3" in out and "agent-b" in out
    assert "agent-a\tdone 2\twip 0" in out


ACTIVITY = [
    {
        "id": 9,
        "board_id": 2,
        "actor_label": "agent-a",
        "action": "moved",
        "summary": "moved KAN-3 to done",
        "ts": "2026-07-17T12:00:00Z",
    }
]


def test_activity_maps_board_and_filters(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"activity": ACTIVITY}))
    code = cli.run(
        ["activity", "--board", "2", "--actor", "agent-a", "--action", "moved", "--limit", "10"]
    )
    assert code == 0
    assert fake.calls == [
        (
            "list_activity",
            {
                "board_id": 2,
                "limit": 10,
                "cursor": None,
                "actor": "agent-a",
                "action": "moved",
            },
        )
    ]


def test_activity_requires_a_board(monkeypatch, env, capsys):
    patch_client(monkeypatch, FakeClient(result={"activity": []}))
    assert cli.run(["activity"]) == 1  # no --board, no KANBAN_BOARD_ID → refused
    assert "board is required" in capsys.readouterr().err


def test_activity_human_output(monkeypatch, env, capsys):
    patch_client(monkeypatch, FakeClient(result={"activity": ACTIVITY}))
    assert cli.run(["activity", "--board", "2"]) == 0
    out = capsys.readouterr().out
    assert "agent-a" in out and "moved" in out and "moved KAN-3 to done" in out


def test_resolve(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient())
    assert cli.run(["resolve", "7"]) == 0
    assert fake.calls == [("resolve_card", {"card_id": 7})]


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
                "priority": None,
                "due_date": None,
                "label_ids": None,
            },
        )
    ]


def test_create_maps_card_fields(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient())
    code = cli.run(
        [
            "create", "S",
            "--priority", "urgent", "--due", "2026-08-01T00:00:00Z",
            "--label", "1", "--label", "2",
        ]
    )
    assert code == 0
    call = fake.calls[0][1]
    assert call["priority"] == "urgent"
    assert call["due_date"] == "2026-08-01T00:00:00Z"
    assert call["label_ids"] == [1, 2]


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
                "priority": None,
                "due_date": None,
                "label_ids": None,
            },
        )
    ]


def test_update_maps_card_fields(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient())
    code = cli.run(["update", "7", "--priority", "low", "--due", "2026-09-01", "--label", "3"])
    assert code == 0
    call = fake.calls[0][1]
    assert call["priority"] == "low"
    assert call["due_date"] == "2026-09-01"
    assert call["label_ids"] == [3]


# --- label subcommands ------------------------------------------------------


def test_label_list_maps_board(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"labels": []}))
    assert cli.run(["label", "list", "--board", "2"]) == 0
    assert fake.calls == [("list_labels", {"board_id": 2})]


def test_label_create_passes_name_and_color(monkeypatch, env):
    fake = patch_client(
        monkeypatch,
        FakeClient(result={"id": 1, "board_id": 2, "name": "bug", "color": "#ef4444"}),
    )
    assert cli.run(["label", "create", "bug", "#ef4444", "--board", "2"]) == 0
    assert fake.calls == [
        ("create_label", {"board_id": 2, "name": "bug", "color": "#ef4444"})
    ]


def test_label_delete_requires_yes(monkeypatch, env, capsys):
    fake = patch_client(monkeypatch, FakeClient(result={"deleted": 5}))
    assert cli.run(["label", "delete", "5"]) == 1  # no --yes → refused
    assert fake.calls == []
    assert cli.run(["label", "delete", "5", "--yes"]) == 0
    assert fake.calls == [("delete_label", {"label_id": 5})]


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


# --- board subcommands ------------------------------------------------------


def test_board_list_calls_client(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"boards": [BOARD]}))
    assert cli.run(["board", "list"]) == 0
    assert fake.calls == [("list_boards", {})]


def test_board_create_passes_name(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result=BOARD))
    assert cli.run(["board", "create", "Roadmap"]) == 0
    assert fake.calls == [("create_board", {"name": "Roadmap"})]


def test_board_list_human_output(monkeypatch, env, capsys):
    patch_client(monkeypatch, FakeClient(result={"boards": [BOARD]}))
    cli.run(["board", "list"])
    assert capsys.readouterr().out.strip() == "2\tRoadmap"


def test_board_list_empty(monkeypatch, env, capsys):
    patch_client(monkeypatch, FakeClient(result={"boards": []}))
    cli.run(["board", "list"])
    assert capsys.readouterr().out.strip() == "(no boards)"


def test_board_list_json(monkeypatch, env, capsys):
    patch_client(monkeypatch, FakeClient(result={"boards": [BOARD]}))
    assert cli.run(["board", "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"boards": [BOARD]}


# --- epic subcommands -------------------------------------------------------


def test_epic_list_maps_board_filter(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"epics": [EPIC]}))
    assert cli.run(["epic", "list", "--board", "3"]) == 0
    assert fake.calls == [("list_epics", {"board_id": 3})]


def test_epic_list_uses_board_env_default(monkeypatch, env):
    monkeypatch.setenv("KANBAN_BOARD_ID", "7")
    fake = patch_client(monkeypatch, FakeClient(result={"epics": []}))
    cli.run(["epic", "list"])
    assert fake.calls[0][1]["board_id"] == 7


def test_epic_create_maps_all_options(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result=EPIC))
    code = cli.run(
        ["epic", "create", "Onboarding", "--board", "2", "--description", "d"]
    )
    assert code == 0
    assert fake.calls == [
        ("create_epic", {"name": "Onboarding", "board_id": 2, "description": "d"})
    ]


def test_epic_update_maps_fields(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result=EPIC))
    assert cli.run(["epic", "update", "1", "--name", "New", "--description", "x"]) == 0
    assert fake.calls == [
        ("update_epic", {"epic_id": 1, "name": "New", "description": "x"})
    ]


def test_epic_delete_requires_yes(monkeypatch, env, capsys):
    fake = patch_client(monkeypatch, FakeClient(result={"deleted": 1}))
    code = cli.run(["epic", "delete", "1"])
    assert code == cli.EXIT_ERROR
    assert fake.calls == []  # never touched the API
    assert "--yes" in capsys.readouterr().err


def test_epic_delete_with_yes(monkeypatch, env, capsys):
    fake = patch_client(monkeypatch, FakeClient(result={"deleted": 1}))
    assert cli.run(["epic", "delete", "1", "--yes"]) == 0
    assert fake.calls == [("delete_epic", {"epic_id": 1})]
    assert "deleted epic 1" in capsys.readouterr().out


def test_epic_list_human_output(monkeypatch, env, capsys):
    patch_client(monkeypatch, FakeClient(result={"epics": [EPIC]}))
    cli.run(["epic", "list"])
    assert capsys.readouterr().out.strip() == "EPIC-1\tOnboarding"


def test_epic_single_human_output(monkeypatch, env, capsys):
    patch_client(monkeypatch, FakeClient(result=EPIC))
    cli.run(["epic", "create", "Onboarding"])
    assert capsys.readouterr().out.strip() == "EPIC-1\tOnboarding"


def test_epic_missing_subcommand_is_usage_error(env):
    with pytest.raises(SystemExit) as exc:
        cli.run(["epic"])
    assert exc.value.code == cli.EXIT_USAGE


# --- warmup -----------------------------------------------------------------


def test_warmup_calls_client(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"status": "ok", "health": {}}))
    assert cli.run(["warmup"]) == cli.EXIT_OK
    assert fake.calls == [("warmup", {})]


def test_warmup_ok_exits_zero(monkeypatch, env):
    patch_client(monkeypatch, FakeClient(result={"status": "ok", "health": {"status": "ok"}}))
    assert cli.run(["warmup"]) == cli.EXIT_OK


@pytest.mark.parametrize(
    "status", ["waking", "error"]
)
def test_warmup_not_ok_exits_nonzero(monkeypatch, env, status):
    patch_client(monkeypatch, FakeClient(result={"status": status, "detail": "not yet"}))
    assert cli.run(["warmup"]) == cli.EXIT_ERROR


def test_warmup_needs_no_token(monkeypatch, capsys):
    # No KANBAN_TOKEN set — warmup hits the public /api/health, so it must not
    # error out on a missing token like the other (auth-required) commands do.
    monkeypatch.delenv("KANBAN_TOKEN", raising=False)
    monkeypatch.delenv("KANBAN_BOARD_ID", raising=False)
    monkeypatch.delenv("KANBAN_API_URL", raising=False)
    patch_client(monkeypatch, FakeClient(result={"status": "ok", "health": {}}))
    assert cli.run(["warmup"]) == cli.EXIT_OK


def test_warmup_human_output_ok(monkeypatch, env, capsys):
    patch_client(monkeypatch, FakeClient(result={"status": "ok", "health": {}}))
    cli.run(["warmup"])
    assert capsys.readouterr().out.strip() == "ok\tAPI is awake"


def test_warmup_human_output_waking(monkeypatch, env, capsys):
    patch_client(monkeypatch, FakeClient(result={"status": "waking", "detail": "retry shortly"}))
    cli.run(["warmup"])
    assert capsys.readouterr().out.strip() == "waking\tretry shortly"


def test_warmup_json_output(monkeypatch, env, capsys):
    result = {"status": "ok", "health": {"status": "ok"}}
    patch_client(monkeypatch, FakeClient(result=result))
    assert cli.run(["warmup", "--json"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out) == result


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


def test_real_client_warmup_hits_unversioned_health(monkeypatch):
    # No token in the env: warmup must still reach the unversioned /api/health
    # (not /api/v1/...) and send no Authorization header.
    monkeypatch.delenv("KANBAN_TOKEN", raising=False)
    monkeypatch.delenv("KANBAN_BOARD_ID", raising=False)
    monkeypatch.delenv("KANBAN_API_URL", raising=False)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"status": "ok"})

    from kanban_client import KanbanClient

    monkeypatch.setattr(
        cli,
        "KanbanClient",
        lambda url, token, **k: KanbanClient(
            url, token, transport=httpx.MockTransport(handler)
        ),
    )
    assert cli.run(["warmup"]) == cli.EXIT_OK
    assert seen["method"] == "GET"
    assert seen["path"] == "/api/health"
    assert seen["auth"] is None


# --- dependency / link / comment subcommands (KAN-270) ----------------------


def test_dep_add_maps_card_and_blocker(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient())
    assert cli.run(["dep", "add", "7", "--blocked-by", "3"]) == 0
    assert fake.calls == [("add_dependency", {"card_id": 7, "blocker_id": 3})]


def test_dep_rm_maps_card_and_blocker(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient())
    assert cli.run(["dep", "rm", "7", "--blocked-by", "3"]) == 0
    assert fake.calls == [("remove_dependency", {"card_id": 7, "blocker_id": 3})]


def test_dep_add_requires_blocked_by(env):
    # --blocked-by is required → argparse usage error (exit 2).
    with pytest.raises(SystemExit) as exc:
        cli.run(["dep", "add", "7"])
    assert exc.value.code == cli.EXIT_USAGE


def test_dep_list_calls_client(monkeypatch, env):
    fake = patch_client(
        monkeypatch, FakeClient(result={"card_id": 7, "blocked_by": [3], "blocks": [9]})
    )
    assert cli.run(["dep", "list", "7"]) == 0
    assert fake.calls == [("list_dependencies", {"card_id": 7})]


def test_dep_list_human_output(monkeypatch, env, capsys):
    patch_client(
        monkeypatch, FakeClient(result={"card_id": 7, "blocked_by": [3, 4], "blocks": []})
    )
    assert cli.run(["dep", "list", "7"]) == 0
    out = capsys.readouterr().out
    assert "card 7" in out
    assert "blocked_by:\t3, 4" in out
    assert "blocks:\t(none)" in out


def test_dep_list_json_output(monkeypatch, env, capsys):
    result = {"card_id": 7, "blocked_by": [3], "blocks": []}
    patch_client(monkeypatch, FakeClient(result=result))
    assert cli.run(["dep", "list", "7", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == result


def test_link_add_maps_label_and_url(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient())
    code = cli.run(
        ["link", "add", "7", "--url", "https://github.com/o/r/pull/1", "--label", "PR"]
    )
    assert code == 0
    assert fake.calls == [
        ("add_link", {"card_id": 7, "label": "PR", "url": "https://github.com/o/r/pull/1"})
    ]


def test_link_add_requires_label_and_url(env):
    # Both --url and --label are required (the API's LinkCreate demands both).
    with pytest.raises(SystemExit) as exc:
        cli.run(["link", "add", "7", "--url", "https://x"])
    assert exc.value.code == cli.EXIT_USAGE


def test_dep_add_human_output_shows_edges(monkeypatch, env, capsys):
    # add_dependency returns the refreshed card; the verb projects just its edges.
    patch_client(
        monkeypatch,
        FakeClient(result={"ticket_number": "KAN-7", "blocked_by": [3], "blocks": [], "id": 7}),
    )
    assert cli.run(["dep", "add", "7", "--blocked-by", "3"]) == 0
    out = capsys.readouterr().out
    assert "card 7" in out
    assert "blocked_by:\t3" in out


def test_link_rm_maps_link_id(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient())
    assert cli.run(["link", "rm", "7", "--link-id", "2"]) == 0
    assert fake.calls == [("remove_link", {"card_id": 7, "link_id": 2})]


def test_link_add_human_output_shows_links(monkeypatch, env, capsys):
    # add_link returns the refreshed card; the verb projects just its links.
    link = {"id": 2, "label": "PR", "url": "https://github.com/o/r/pull/1"}
    patch_client(
        monkeypatch,
        FakeClient(result={"ticket_number": "KAN-7", "links": [link], "labels": [], "id": 7}),
    )
    assert cli.run(["link", "add", "7", "--url", link["url"], "--label", "PR"]) == 0
    out = capsys.readouterr().out
    assert "card 7" in out
    assert "2\tPR\thttps://github.com/o/r/pull/1" in out


def test_comment_add_maps_body(monkeypatch, env):
    fake = patch_client(
        monkeypatch,
        FakeClient(result={"id": 1, "body": "looks good", "author_id": None}),
    )
    assert cli.run(["comment", "add", "7", "--body", "looks good"]) == 0
    assert fake.calls == [("add_comment", {"card_id": 7, "body": "looks good"})]


def test_comment_add_human_output(monkeypatch, env, capsys):
    patch_client(
        monkeypatch,
        FakeClient(
            result={
                "id": 1,
                "body": "looks good",
                "author_id": None,
                "created_at": "2026-07-20T00:00:00Z",
            }
        ),
    )
    assert cli.run(["comment", "add", "7", "--body", "looks good"]) == 0
    assert "looks good" in capsys.readouterr().out


def test_comment_list_calls_client(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"comments": []}))
    assert cli.run(["comment", "list", "7"]) == 0
    assert fake.calls == [("list_comments", {"card_id": 7})]


def test_comment_list_human_output(monkeypatch, env, capsys):
    comment = {
        "id": 5,
        "body": "please rebase",
        "author_id": None,
        "created_at": "2026-07-20T00:00:00Z",
    }
    patch_client(monkeypatch, FakeClient(result={"comments": [comment]}))
    assert cli.run(["comment", "list", "7"]) == 0
    out = capsys.readouterr().out.strip()
    assert out == "5\t2026-07-20T00:00:00Z\tplease rebase"


def test_comment_list_empty_human_output(monkeypatch, env, capsys):
    patch_client(monkeypatch, FakeClient(result={"comments": []}))
    assert cli.run(["comment", "list", "7"]) == 0
    assert capsys.readouterr().out.strip() == "(no comments)"


# --- config resolution chain (KAN-199) --------------------------------------
# Precedence per value: env > ~/.config/kan/config.toml > nearest .mcp.json.
# The point is that a PAT can live in a file and never touch the command line.
# (``isolate_config`` autouse fixture keeps the repo's real .mcp.json out of view;
# these tests opt individual sources back in.)


def _write_mcp_json(monkeypatch, tmp_path, env: dict) -> None:
    """Drop a .mcp.json carrying ``env`` and point discovery at it."""
    path = tmp_path / ".mcp.json"
    path.write_text(json.dumps({"mcpServers": {"kanban": {"env": env}}}), encoding="utf-8")
    monkeypatch.setattr("kanban_cli.config.find_mcp_json", lambda *a, **k: path)


def test_token_from_config_file_when_env_unset(monkeypatch):
    monkeypatch.delenv("KANBAN_TOKEN", raising=False)
    config.write_config_file(token="kanban_pat_fromfile", board_id="9")
    cfg = config.load_config()
    assert cfg.token == "kanban_pat_fromfile"
    assert cfg.board_id == 9


def test_token_from_mcp_json_when_env_and_file_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("KANBAN_TOKEN", raising=False)
    _write_mcp_json(
        monkeypatch,
        tmp_path,
        {
            "KANBAN_TOKEN": "kanban_pat_frommcp",
            "KANBAN_API_URL": "https://mcp.example",
            "KANBAN_BOARD_ID": 42,  # a JSON number — must be coerced to int 42
        },
    )
    cfg = config.load_config()
    assert cfg.token == "kanban_pat_frommcp"
    assert cfg.api_url == "https://mcp.example"
    assert cfg.board_id == 42


def test_env_overrides_config_file_and_mcp_json(monkeypatch, tmp_path):
    _write_mcp_json(monkeypatch, tmp_path, {"KANBAN_TOKEN": "kanban_pat_mcp", "KANBAN_BOARD_ID": 1})
    config.write_config_file(token="kanban_pat_file", board_id="2")
    monkeypatch.setenv("KANBAN_TOKEN", "kanban_pat_env")
    monkeypatch.setenv("KANBAN_BOARD_ID", "3")
    cfg = config.load_config()
    assert cfg.token == "kanban_pat_env"
    assert cfg.board_id == 3


def test_config_file_overrides_mcp_json(monkeypatch, tmp_path):
    monkeypatch.delenv("KANBAN_TOKEN", raising=False)
    monkeypatch.delenv("KANBAN_BOARD_ID", raising=False)
    _write_mcp_json(monkeypatch, tmp_path, {"KANBAN_TOKEN": "kanban_pat_mcp", "KANBAN_BOARD_ID": 1})
    config.write_config_file(token="kanban_pat_file", board_id="2")
    cfg = config.load_config()
    assert cfg.token == "kanban_pat_file"
    assert cfg.board_id == 2


def test_missing_token_everywhere_raises(monkeypatch):
    monkeypatch.delenv("KANBAN_TOKEN", raising=False)
    with pytest.raises(config.ConfigError):
        config.load_config()


def test_warmup_allows_missing_token_everywhere(monkeypatch):
    monkeypatch.delenv("KANBAN_TOKEN", raising=False)
    cfg = config.load_config(require_token=False)  # warmup path
    assert cfg.token == ""


def test_malformed_sources_are_ignored(monkeypatch, tmp_path):
    """A broken config file / .mcp.json must not crash — it's just skipped, so the
    normal 'token required' error still surfaces rather than a traceback."""
    monkeypatch.delenv("KANBAN_TOKEN", raising=False)
    config.config_file_path().parent.mkdir(parents=True, exist_ok=True)
    config.config_file_path().write_text("this is not = valid toml [", encoding="utf-8")
    bad = tmp_path / ".mcp.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr("kanban_cli.config.find_mcp_json", lambda *a, **k: bad)
    with pytest.raises(config.ConfigError):
        config.load_config()


def test_write_config_file_is_owner_only_and_merges(monkeypatch):
    p1 = config.write_config_file(api_url="https://a.example", board_id="5")
    assert (p1.stat().st_mode & 0o777) == 0o600
    # A later write of just the token must preserve api_url + board_id.
    config.write_config_file(token="kanban_pat_x")
    monkeypatch.delenv("KANBAN_TOKEN", raising=False)
    cfg = config.load_config()
    assert cfg.api_url == "https://a.example"
    assert cfg.board_id == 5
    assert cfg.token == "kanban_pat_x"


def test_find_mcp_json_walks_up(monkeypatch, tmp_path):
    (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    assert _REAL_FIND_MCP_JSON(deep) == tmp_path / ".mcp.json"


def test_config_show_redacts_token(monkeypatch, tmp_path, capsys):
    _write_mcp_json(monkeypatch, tmp_path, {"KANBAN_TOKEN": "kanban_pat_supersecret1234"})
    monkeypatch.delenv("KANBAN_TOKEN", raising=False)
    assert cli.run(["config", "show"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "kanban_pat_supersecret1234" not in out  # never print the raw token
    assert "1234" in out  # but the last 4 identify it


def test_config_set_token_stdin_never_needs_argv(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("kanban_pat_viastdin\n"))
    assert cli.run(["config", "set", "--token-stdin", "--board-id", "8"]) == cli.EXIT_OK
    monkeypatch.delenv("KANBAN_TOKEN", raising=False)
    cfg = config.load_config()
    assert cfg.token == "kanban_pat_viastdin"
    assert cfg.board_id == 8


def test_config_set_rejects_non_integer_board_id():
    assert cli.run(["config", "set", "--board-id", "abc"]) == cli.EXIT_ERROR


# --- next / dispatch (M5 V12, KAN-245) -------------------------------------


def test_next_peeks_by_default(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"card": CARD}))
    code = cli.run(["next", "--board", "3", "--priority", "high", "--label", "4"])
    assert code == 0
    assert fake.calls == [("next_ready", {"board_id": 3, "label": 4, "priority": "high"})]


def test_next_claim_dispatches(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"card": CARD}))
    code = cli.run(["next", "--board", "3", "--claim", "--assignee", "agent-7"])
    assert code == 0
    assert fake.calls == [
        ("dispatch", {"board_id": 3, "assignee": "agent-7", "label": None, "priority": None})
    ]


def test_next_requires_a_board(monkeypatch, env):
    fake = patch_client(monkeypatch, FakeClient(result={"card": CARD}))
    code = cli.run(["next"])
    # No --board and no KANBAN_BOARD_ID → config error, no client call.
    assert code == cli.EXIT_ERROR
    assert fake.calls == []


def test_next_humanizes_empty(monkeypatch, env, capsys):
    patch_client(monkeypatch, FakeClient(result={"card": None}))
    code = cli.run(["next", "--board", "3"])
    assert code == 0
    assert capsys.readouterr().out.strip() == "(no card ready)"
