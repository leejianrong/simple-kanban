"""Human auth integration tests (Milestone 3 V6, ADR 0011).

Exercises the fastapi-users cookie-session + GitHub OAuth wiring end to end
against the throwaway Postgres, with the **GitHub network calls mocked** (no real
token exchange / userinfo). Covers: unauthenticated `/users/me` → 401; the OAuth
callback creates a `User` + `OAuthAccount` and sets a session cookie; an
authenticated request is recognised; logout revokes the session.

These run on the **async** auth engine (unlike the sync board tests) but share the
same TestClient/DB fixtures — the async work happens inside the app, under the
TestClient's event loop. (V4's env-token write-guard lives in test_auth.py.)
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import text

from app.db import engine

# The OAuth identity the mocked GitHub hands back.
FAKE_ACCOUNT_ID = "gh-12345"
FAKE_EMAIL = "octocat@example.com"


@pytest.fixture
def mock_github(monkeypatch):
    """Stub the GitHub client's two network calls so the callback needs no network."""
    from app import users

    async def fake_get_access_token(code, redirect_uri, code_verifier=None):
        return {"access_token": "gh-access-token", "expires_at": None}

    async def fake_get_id_email(access_token):
        return FAKE_ACCOUNT_ID, FAKE_EMAIL

    monkeypatch.setattr(users.github_oauth_client, "get_access_token", fake_get_access_token)
    monkeypatch.setattr(users.github_oauth_client, "get_id_email", fake_get_id_email)


def _login_via_github(client) -> None:
    """Drive authorize → callback so the client ends up holding a session cookie.

    The authorize step both returns the state token (in the authorization URL) and
    sets the CSRF cookie in the client's jar; the callback validates both.
    """
    authorize = client.get("/auth/github/authorize")
    assert authorize.status_code == 200
    state = parse_qs(urlparse(authorize.json()["authorization_url"]).query)["state"][0]

    callback = client.get(
        "/auth/github/callback",
        params={"code": "fake-code", "state": state},
        follow_redirects=False,
    )
    # Our RedirectCookieTransport lands the browser back on the SPA root (302) and
    # sets the httpOnly session cookie.
    assert callback.status_code == 302
    assert callback.headers["location"] == "/"
    assert "kanbanauth" in callback.cookies


def test_users_me_unauthenticated_is_401(client):
    assert client.get("/users/me").status_code == 401


def test_oauth_callback_creates_user_and_session(client, mock_github):
    _login_via_github(client)

    # The session is recognised on a subsequent request.
    me = client.get("/users/me")
    assert me.status_code == 200
    assert me.json()["email"] == FAKE_EMAIL

    # Exactly one user + one linked GitHub account were created.
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM "user"')).scalar() == 1
        oauth = conn.execute(
            text("SELECT oauth_name, account_id, account_email FROM oauth_account")
        ).one()
    assert oauth == ("github", FAKE_ACCOUNT_ID, FAKE_EMAIL)


def test_repeat_login_is_idempotent(client, mock_github):
    """A second GitHub login for the same account links to the existing user."""
    _login_via_github(client)
    client.cookies.clear()  # forget the first session; log in fresh
    _login_via_github(client)

    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM "user"')).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM oauth_account")).scalar() == 1


def test_logout_revokes_the_session(client, mock_github):
    _login_via_github(client)
    assert client.get("/users/me").status_code == 200

    # There is a live session row; logout deletes it (revocable, D3).
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM access_token")).scalar() == 1

    assert client.post("/auth/logout").status_code == 204

    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM access_token")).scalar() == 0

    # The cookie the client still holds no longer resolves to a user.
    assert client.get("/users/me").status_code == 401
