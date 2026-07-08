"""Human authentication wiring (Milestone 3 V6, ADR 0011).

Built on **fastapi-users** (D2): a `User` model, a GitHub OAuth login, and a
revocable **cookie session** (D3). Everything here runs on the **async** engine
(`get_async_session`) — the only part of the app that does. Board/epic/card CRUD
stays sync (ADR 0008).

Shape:
- **User store** — `SQLAlchemyUserDatabase` over the async session (users +
  OAuth accounts); `SQLAlchemyAccessTokenDatabase` for the session strategy.
- **Auth backend** — `CookieTransport` (httpOnly, SameSite=Lax, Secure in prod) +
  `DatabaseStrategy` (a row per session in `access_token`; logout deletes it →
  instant revocation).
- **GitHub OAuth** — `httpx-oauth`'s `GitHubOAuth2` + fastapi-users'
  `get_oauth_router`. Only mounted when creds are configured, so the app boots
  without them (login simply unavailable, the landing still shows).

Provider modularity (A3) falls out for free: adding Google/email later is another
OAuth client + `include_router`, not a rework.
"""
from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends, FastAPI, status
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, schemas
from fastapi_users.authentication import AuthenticationBackend, CookieTransport
from fastapi_users.authentication.strategy.db import (
    AccessTokenDatabase,
    DatabaseStrategy,
)
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from httpx_oauth.clients.github import GitHubOAuth2
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse, Response

from .auth_models import AccessToken, OAuthAccount, User
from .db import get_async_session

# --- Config (read from the environment; see CLAUDE.md §Configuration) ---------

# Signs session tokens, the OAuth state token, and password-reset/verify tokens.
# MUST be set to a strong random value in prod (a Fly secret). The dev default
# keeps local boot friction-free; it is not safe for a public deployment.
AUTH_SECRET = os.environ.get("AUTH_SECRET", "dev-insecure-secret-change-me-in-production!")

# 7-day sessions. A row lives in `access_token` for each; logout deletes it.
SESSION_LIFETIME_SECONDS = 60 * 60 * 24 * 7

# Secure cookies require HTTPS, so they're off by default and turned on in prod
# (COOKIE_SECURE=1 as a Fly secret). Dev + the test suite run over http.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "").lower() in {"1", "true", "yes"}

GITHUB_CLIENT_ID = os.environ.get("GITHUB_OAUTH_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_OAUTH_CLIENT_SECRET")


# --- User store + manager -----------------------------------------------------


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    """fastapi-users manager. Token secrets are only used by the (currently
    unmounted) reset-password / verify flows, but must be set."""

    reset_password_token_secret = AUTH_SECRET
    verification_token_secret = AUTH_SECRET


async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    yield SQLAlchemyUserDatabase(session, User, OAuthAccount)


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db)


async def get_access_token_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyAccessTokenDatabase, None]:
    yield SQLAlchemyAccessTokenDatabase(session, AccessToken)


def get_database_strategy(
    access_token_db: AccessTokenDatabase = Depends(get_access_token_db),
) -> DatabaseStrategy:
    return DatabaseStrategy(access_token_db, lifetime_seconds=SESSION_LIFETIME_SECONDS)


# --- Auth backend (cookie session) --------------------------------------------


class RedirectCookieTransport(CookieTransport):
    """A cookie transport that redirects to the SPA root on login instead of
    returning a bare ``204``.

    fastapi-users' OAuth callback returns the backend's *login response*; the
    stock cookie transport answers ``204 No Content``, which leaves the browser
    on a blank ``/auth/github/callback`` page after GitHub bounces back. A
    single-page app instead wants to land on ``/``. Overriding just the login
    response keeps the cookie behaviour identical and preserves the ``204`` logout
    response. (Build-revealed detail beyond the spike — see ADR 0011.)
    """

    async def get_login_response(self, token: str) -> Response:
        response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        return self._set_login_cookie(response, token)


cookie_transport = RedirectCookieTransport(
    cookie_name="kanbanauth",
    cookie_max_age=SESSION_LIFETIME_SECONDS,
    cookie_secure=COOKIE_SECURE,
    cookie_httponly=True,
    cookie_samesite="lax",
)

auth_backend = AuthenticationBackend(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_database_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

# The dependency the board routes will eventually use to resolve the current
# human (V8). Exported now so it's ready for board authorization.
current_active_user = fastapi_users.current_user(active=True)

# Optional variant: yields the current user when a valid session cookie is
# present, else None (never 401). V7 uses it to stamp a new board's owner from the
# session when one exists, while keeping the route reachable by tokenless clients
# (the MCP server, tests). Enforcement of ownership arrives in V8.
current_optional_user = fastapi_users.current_user(active=True, optional=True)

github_oauth_client: GitHubOAuth2 | None = None
if GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET:
    github_oauth_client = GitHubOAuth2(GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET)


# --- API schemas for the users router -----------------------------------------


class UserRead(schemas.BaseUser[uuid.UUID]):
    pass


class UserUpdate(schemas.BaseUserUpdate):
    pass


def register_auth_routes(app: FastAPI) -> None:
    """Mount the auth + users routers on ``app``.

    - ``POST /auth/login`` + ``POST /auth/logout`` (logout revokes the session).
      Login is unused by OAuth users but kept for future email/password (A3).
    - ``GET/PATCH /users/me`` — the SPA's "who am I?" check (401 when logged out).
    - ``GET /auth/github/authorize`` + ``/auth/github/callback`` — **only** when
      GitHub creds are set, so the app still boots (and the landing shows) without
      them.
    """
    app.include_router(
        fastapi_users.get_auth_router(auth_backend),
        prefix="/auth",
        tags=["auth"],
    )
    app.include_router(
        fastapi_users.get_users_router(UserRead, UserUpdate),
        prefix="/users",
        tags=["users"],
    )
    if github_oauth_client is not None:
        app.include_router(
            fastapi_users.get_oauth_router(
                github_oauth_client,
                auth_backend,
                AUTH_SECRET,
                associate_by_email=True,
                is_verified_by_default=True,
                # The CSRF cookie shares the session cookie's Secure policy so it
                # is stored over http in dev/test and only requires https in prod.
                csrf_token_cookie_secure=COOKIE_SECURE,
            ),
            prefix="/auth/github",
            tags=["auth"],
        )
