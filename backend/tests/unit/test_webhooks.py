"""Unit tests for the GitHub webhook receiver (KAN-42, app.routers.webhooks).

No database, no Postgres, no Docker — the endpoint is standalone (its auth is the
HMAC signature, not the board principal resolver), so we mount just its router on
a bare FastAPI app and drive it with TestClient. Covers signature verification
(valid → 200, bad → 401, missing header → 401, secret unset → 503) and event
dispatch (pull_request / check_suite / status routed, unknown ignored but 200).
"""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import webhooks

SECRET = "shhh-test-secret"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    app = FastAPI()
    app.include_router(webhooks.router, prefix="/api/v1")
    return TestClient(app)


def _sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _post(client: TestClient, event: str, payload: dict, *, secret: str = SECRET):
    body = json.dumps(payload).encode()
    headers = {
        "X-GitHub-Event": event,
        "X-Hub-Signature-256": _sign(body, secret),
        "Content-Type": "application/json",
    }
    return client.post("/api/v1/webhooks/github", content=body, headers=headers)


# --- signature verification --------------------------------------------------


def test_valid_signature_is_accepted(client):
    resp = _post(client, "pull_request", {"action": "opened", "number": 1})
    assert resp.status_code == 200
    assert resp.json()["handled"] is True


def test_bad_signature_is_rejected(client):
    body = json.dumps({"action": "opened"}).encode()
    headers = {
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": "sha256=" + "0" * 64,
    }
    resp = client.post("/api/v1/webhooks/github", content=body, headers=headers)
    assert resp.status_code == 401


def test_missing_signature_header_is_rejected(client):
    body = json.dumps({"action": "opened"}).encode()
    resp = client.post(
        "/api/v1/webhooks/github",
        content=body,
        headers={"X-GitHub-Event": "pull_request"},
    )
    assert resp.status_code == 401


def test_wrong_secret_signature_is_rejected(client):
    resp = _post(client, "pull_request", {"action": "opened"}, secret="wrong-secret")
    assert resp.status_code == 401


def test_unconfigured_secret_returns_503(monkeypatch):
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    app = FastAPI()
    app.include_router(webhooks.router, prefix="/api/v1")
    unconfigured = TestClient(app)
    body = json.dumps({"action": "opened"}).encode()
    resp = unconfigured.post(
        "/api/v1/webhooks/github",
        content=body,
        headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": _sign(body)},
    )
    assert resp.status_code == 503


# --- event dispatch ----------------------------------------------------------


@pytest.mark.parametrize(
    "event,payload",
    [
        ("pull_request", {"action": "closed", "number": 7, "pull_request": {"merged": True}}),
        ("check_suite", {"action": "completed", "check_suite": {"conclusion": "success"}}),
        ("status", {"state": "success", "sha": "abc123", "context": "ci/test"}),
    ],
)
def test_handled_events_are_routed(client, event, payload):
    resp = _post(client, event, payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["event"] == event
    assert body["handled"] is True


def test_unknown_event_is_acknowledged_but_ignored(client):
    resp = _post(client, "ping", {"zen": "hello"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["event"] == "ping"
    assert body["handled"] is False


def test_dispatch_invokes_the_matching_handler(client, monkeypatch):
    calls: list[dict] = []
    monkeypatch.setitem(webhooks._DISPATCH, "pull_request", lambda p: calls.append(p))
    _post(client, "pull_request", {"action": "opened", "number": 42})
    assert calls == [{"action": "opened", "number": 42}]
