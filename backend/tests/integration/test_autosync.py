"""API tests for GitHub → board auto-sync mapping (KAN-43, app.autosync).

The webhook receiver is authenticated by its HMAC signature, not the board
principal resolver, so these tests drive signed webhook POSTs (no cookie) and
verify the resulting card side effects through the owner-authenticated API.

Covered: ticket parsing from the PR branch, the per-board opt-out gate
(``autosync_enabled`` false → no writes), PR link attach + idempotency, a CI
comment on check_suite / status, and the merge→done move ONLY when the separate
``autosync_advance_to_done`` flag is on.

Per the suite convention, every ``import app...`` lives inside a test/fixture body.
"""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest

CARDS = "/api/v1/cards"
BOARDS = "/api/v1/boards"
WEBHOOK = "/api/v1/webhooks/github"
SECRET = "shhh-autosync-secret"


@pytest.fixture(autouse=True)
def _webhook_secret(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)


@pytest.fixture
def owner(logged_in_client):
    """Board-owning session client — it claimed the default board (id=1) on login."""
    return logged_in_client


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def _send(client, event: str, payload: dict):
    body = json.dumps(payload).encode()
    return client.post(
        WEBHOOK,
        content=body,
        headers={"X-GitHub-Event": event, "X-Hub-Signature-256": _sign(body)},
    )


def _default_board_id(owner) -> int:
    return owner.get(BOARDS).json()[0]["id"]


def _enable_autosync(owner, board_id, *, advance=False):
    r = owner.patch(
        f"{BOARDS}/{board_id}",
        json={"autosync_enabled": True, "autosync_advance_to_done": advance},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _make_card(owner, **fields):
    r = owner.post(CARDS, json={"title": "auto", **fields})
    assert r.status_code == 201, r.text
    return r.json()


def _pr_opened(ticket: str, url: str, action: str = "opened") -> dict:
    return {
        "action": action,
        "pull_request": {
            "head": {"ref": f"feat/{ticket.lower()}-work"},
            "title": f"{ticket}: do the thing",
            "html_url": url,
            "merged": False,
        },
    }


# --- schema / defaults -------------------------------------------------------


def test_board_autosync_flags_default_off(owner):
    board = owner.get(BOARDS).json()[0]
    assert board["autosync_enabled"] is False
    assert board["autosync_advance_to_done"] is False


# --- PR opened → work-link ---------------------------------------------------


def test_pr_opened_attaches_pr_link(owner):
    board_id = _default_board_id(owner)
    _enable_autosync(owner, board_id)
    card = _make_card(owner)
    url = "https://github.com/acme/repo/pull/1"

    resp = _send(owner, "pull_request", _pr_opened(card["ticket_number"], url))
    assert resp.status_code == 200

    detail = owner.get(f"{CARDS}/{card['id']}").json()
    assert [(link["label"], link["url"]) for link in detail["links"]] == [("PR", url)]


def test_pr_link_attach_is_idempotent(owner):
    board_id = _default_board_id(owner)
    _enable_autosync(owner, board_id)
    card = _make_card(owner)
    url = "https://github.com/acme/repo/pull/2"
    payload = _pr_opened(card["ticket_number"], url)

    _send(owner, "pull_request", payload)
    _send(owner, "pull_request", payload)  # same URL again

    detail = owner.get(f"{CARDS}/{card['id']}").json()
    assert len(detail["links"]) == 1  # not duplicated


def test_pr_reopened_also_attaches(owner):
    board_id = _default_board_id(owner)
    _enable_autosync(owner, board_id)
    card = _make_card(owner)
    url = "https://github.com/acme/repo/pull/3"

    _send(owner, "pull_request", _pr_opened(card["ticket_number"], url, action="reopened"))
    detail = owner.get(f"{CARDS}/{card['id']}").json()
    assert len(detail["links"]) == 1


# --- the opt-out gate --------------------------------------------------------


def test_autosync_disabled_is_a_noop(owner):
    # Board left with autosync OFF (the default): the webhook must not write.
    card = _make_card(owner)
    url = "https://github.com/acme/repo/pull/4"

    resp = _send(owner, "pull_request", _pr_opened(card["ticket_number"], url))
    assert resp.status_code == 200  # still acked

    detail = owner.get(f"{CARDS}/{card['id']}").json()
    assert detail["links"] == []  # nothing attached


def test_unknown_ticket_is_a_noop(owner):
    board_id = _default_board_id(owner)
    _enable_autosync(owner, board_id)
    resp = _send(
        owner,
        "pull_request",
        _pr_opened("KAN-999999", "https://github.com/acme/repo/pull/5"),
    )
    assert resp.status_code == 200  # no such card → acked, nothing written


# --- check_suite / status → comment ------------------------------------------


def test_check_suite_posts_comment(owner):
    board_id = _default_board_id(owner)
    _enable_autosync(owner, board_id)
    card = _make_card(owner)

    resp = _send(
        owner,
        "check_suite",
        {
            "action": "completed",
            "check_suite": {
                "status": "completed",
                "conclusion": "success",
                "head_branch": f"feat/{card['ticket_number'].lower()}-work",
            },
        },
    )
    assert resp.status_code == 200

    comments = owner.get(f"{CARDS}/{card['id']}/comments").json()
    assert len(comments) == 1
    assert "success" in comments[0]["body"]
    assert comments[0]["author_id"] is None  # system-authored


def test_status_posts_comment(owner):
    board_id = _default_board_id(owner)
    _enable_autosync(owner, board_id)
    card = _make_card(owner)

    resp = _send(
        owner,
        "status",
        {
            "state": "failure",
            "context": "ci/build",
            "branches": [{"name": f"feat/{card['ticket_number'].lower()}-work"}],
        },
    )
    assert resp.status_code == 200

    comments = owner.get(f"{CARDS}/{card['id']}/comments").json()
    assert len(comments) == 1
    assert "failure" in comments[0]["body"]


def test_check_suite_noop_when_disabled(owner):
    card = _make_card(owner)  # board autosync OFF
    _send(
        owner,
        "check_suite",
        {
            "check_suite": {
                "conclusion": "success",
                "head_branch": f"feat/{card['ticket_number'].lower()}",
            }
        },
    )
    assert owner.get(f"{CARDS}/{card['id']}/comments").json() == []


# --- PR merged → move to done (only when advance flag on) --------------------


def _pr_merged(ticket: str) -> dict:
    return {
        "action": "closed",
        "pull_request": {
            "head": {"ref": f"feat/{ticket.lower()}"},
            "title": f"{ticket}: done",
            "merged": True,
        },
    }


def test_merge_does_not_advance_without_flag(owner):
    board_id = _default_board_id(owner)
    _enable_autosync(owner, board_id, advance=False)  # enabled, but advance OFF
    card = _make_card(owner, column="todo")

    _send(owner, "pull_request", _pr_merged(card["ticket_number"]))

    detail = owner.get(f"{CARDS}/{card['id']}").json()
    assert detail["column"] == "todo"  # left where the human put it


def test_merge_advances_to_done_with_flag(owner):
    board_id = _default_board_id(owner)
    _enable_autosync(owner, board_id, advance=True)
    card = _make_card(owner, column="in_progress")

    _send(owner, "pull_request", _pr_merged(card["ticket_number"]))

    detail = owner.get(f"{CARDS}/{card['id']}").json()
    assert detail["column"] == "done"


def test_merge_noop_when_autosync_disabled(owner):
    # advance_to_done is irrelevant while the master switch is off.
    card = _make_card(owner, column="todo")
    _send(owner, "pull_request", _pr_merged(card["ticket_number"]))
    assert owner.get(f"{CARDS}/{card['id']}").json()["column"] == "todo"
