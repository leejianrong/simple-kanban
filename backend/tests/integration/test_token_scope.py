"""Scoped-token tests (M5 V18, KAN-251).

A PAT carries a ``scope``: ``read`` (observer — GET only) or ``write`` (operator —
the owning user's full board access, the default and the legacy behaviour). The
principal resolver (:func:`app.authz.get_principal`) is the one chokepoint: a
``read`` PAT may make safe reads but any write (POST/PATCH/DELETE/move, and even
POST /tokens) is **403** — authenticated but not authorized. Cookie-session humans
and ``write``/legacy PATs are unaffected.

Per the suite convention, all ``import app.*`` live inside test bodies.
"""
from __future__ import annotations

TOKENS = "/api/v1/tokens"
BOARDS = "/api/v1/boards"
CARDS = "/api/v1/cards"

ALICE = ("alice@example.com", "gh-alice")


def _bearer(raw: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw}"}


def _seed(login_as):
    """Alice logs in (claiming the default board), and seeds one card on it.

    Returns ``(alice, board_id, card_id)``.
    """
    alice = login_as(*ALICE)
    board_id = alice.get(BOARDS).json()[0]["id"]
    card_id = alice.post(
        CARDS, json={"title": "seed", "board_id": board_id}
    ).json()["id"]
    return alice, board_id, card_id


# --- scope round-trips through create + list ---------------------------------


def test_create_defaults_to_write_and_list_reports_scope(login_as):
    alice = login_as(*ALICE)
    default = alice.post(TOKENS, json={"name": "no-scope"}).json()
    assert default["scope"] == "write"

    reader = alice.post(TOKENS, json={"name": "obs", "scope": "read"}).json()
    assert reader["scope"] == "read"

    listed = {t["name"]: t["scope"] for t in alice.get(TOKENS).json()}
    assert listed == {"no-scope": "write", "obs": "read"}


def test_create_rejects_unknown_scope(login_as):
    alice = login_as(*ALICE)
    r = alice.post(TOKENS, json={"name": "bad", "scope": "admin"})
    assert r.status_code == 422


# --- a read PAT: reads pass, every write is 403 ------------------------------


def test_read_pat_can_read(login_as, client):
    alice, board_id, card_id = _seed(login_as)
    raw = alice.post(TOKENS, json={"name": "obs", "scope": "read"}).json()["token"]
    h = _bearer(raw)

    assert client.get(BOARDS, headers=h).status_code == 200
    assert client.get(CARDS, params={"board_id": board_id}, headers=h).status_code == 200
    assert client.get(f"{CARDS}/{card_id}", headers=h).status_code == 200


def test_read_pat_is_forbidden_from_every_write(login_as, client):
    alice, board_id, card_id = _seed(login_as)
    raw = alice.post(TOKENS, json={"name": "obs", "scope": "read"}).json()["token"]
    h = _bearer(raw)

    # create / edit / move / delete a card
    assert client.post(
        CARDS, json={"title": "x", "board_id": board_id}, headers=h
    ).status_code == 403
    assert client.patch(f"{CARDS}/{card_id}", json={"title": "y"}, headers=h).status_code == 403
    assert client.post(
        f"{CARDS}/{card_id}/move", json={"column": "doing", "position": 0}, headers=h
    ).status_code == 403
    assert client.delete(f"{CARDS}/{card_id}", headers=h).status_code == 403

    # per-user write: minting a token via a read PAT is also denied (one chokepoint)
    assert client.post(TOKENS, json={"name": "nope"}, headers=h).status_code == 403

    # ...and the card is untouched (the delete really was refused)
    assert alice.get(f"{CARDS}/{card_id}").status_code == 200


# --- a write PAT + a legacy (pre-migration) PAT: writes pass -----------------


def test_write_pat_can_write(login_as, client):
    alice, board_id, card_id = _seed(login_as)
    raw = alice.post(TOKENS, json={"name": "op", "scope": "write"}).json()["token"]
    h = _bearer(raw)

    created = client.post(CARDS, json={"title": "by-op", "board_id": board_id}, headers=h)
    assert created.status_code == 201
    edit = client.patch(f"{CARDS}/{card_id}", json={"title": "edited"}, headers=h)
    assert edit.status_code == 200


def test_legacy_pat_without_scope_defaults_to_write(login_as, client):
    """A row inserted without a ``scope`` (as if predating the migration) picks up
    the ``server_default 'write'`` and behaves as an operator (back-compat, R5.3)."""
    from sqlalchemy import text

    from app.db import engine
    from app.tokens import generate_token

    alice, board_id, card_id = _seed(login_as)
    # Learn alice's user_id from a normally-created token, then insert a legacy row
    # that omits `scope` entirely so only the DB server_default fills it.
    alice.post(TOKENS, json={"name": "probe"})
    raw, prefix, token_hash = generate_token()
    with engine.begin() as conn:
        user_id = conn.execute(
            text("SELECT user_id FROM personal_access_token LIMIT 1")
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO personal_access_token "
                "(user_id, name, token_hash, token_prefix) "
                "VALUES (:uid, :name, :hash, :prefix)"
            ),
            {"uid": user_id, "name": "legacy", "hash": token_hash, "prefix": prefix},
        )
        stored_scope = conn.execute(
            text("SELECT scope FROM personal_access_token WHERE name = 'legacy'")
        ).scalar_one()
    assert stored_scope == "write"

    h = _bearer(raw)
    assert client.post(
        CARDS, json={"title": "by-legacy", "board_id": board_id}, headers=h
    ).status_code == 201


# --- a cookie-session human is never scope-limited ---------------------------


def test_cookie_session_user_is_unaffected(login_as):
    alice, board_id, card_id = _seed(login_as)
    # No bearer, just the cookie session — writes succeed as before.
    assert alice.patch(f"{CARDS}/{card_id}", json={"title": "human-edit"}).status_code == 200
