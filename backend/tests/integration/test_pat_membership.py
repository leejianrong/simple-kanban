"""A PAT inherits its owner's *membership* access (KAN-16).

This is a confirmation card, not a feature: since a personal access token resolves
to its **owning user** (``app.authz._resolve_pat`` → ``get_principal``) and board
authorization is centralized and role-aware (``authorize_board`` / ``_effective_access``,
KAN-13, ADR 0013), a PAT SHOULD reach any board its owner can access *via a
``board_member`` row* — not just boards the owner owns — with no code change.

These tests lock that in. The setup: **Alice** owns board B; **Bob** is added as a
member of B with some role R; Bob mints a PAT. Then a cookie-less client carrying
only ``Authorization: Bearer <bob-pat>`` performs **direct** operations on B (GET /
PATCH / POST on the board and its cards). We assert the PAT gets exactly the access
Bob's role grants:

- ``viewer`` → READ: reads OK, writes 403.
- ``editor`` → WRITE: reads + card create/update/move OK, board/member manage 403.
- ``owner`` (member row) → MANAGE: rename board / manage members OK.
- no membership + not owner → 403 on B.

Scope: this is about *direct access to a known board id* through the PAT branch of
the resolver, NOT list visibility of member boards (that is KAN-15). Per the suite
convention, all ``app.*`` imports live inside test bodies.
"""
from __future__ import annotations

TOKENS = "/api/v1/tokens"
BOARDS = "/api/v1/boards"
CARDS = "/api/v1/cards"
EPICS = "/api/v1/epics"

ALICE = ("alice@example.com", "gh-alice")
BOB = ("bob@example.com", "gh-bob")
CAROL = ("carol@example.com", "gh-carol")


def _members_url(board_id: int) -> str:
    return f"{BOARDS}/{board_id}/members"


class _Pat:
    """A cookie-less client wrapper that carries a fixed ``Bearer <pat>`` on every
    request and otherwise behaves like ``TestClient`` (methods return the Response).

    This exercises the PAT branch of the principal resolver in isolation (no cookie
    session), which is exactly what KAN-16 is confirming.
    """

    def __init__(self, client, raw: str):
        self._client = client
        self._h = {"Authorization": f"Bearer {raw}"}

    def get(self, url: str, **kw):
        return self._client.get(url, headers=self._h, **kw)

    def post(self, url: str, **kw):
        return self._client.post(url, headers=self._h, **kw)

    def patch(self, url: str, **kw):
        return self._client.patch(url, headers=self._h, **kw)

    def delete(self, url: str, **kw):
        return self._client.delete(url, headers=self._h, **kw)


def _setup_member_pat(login_as, client, role: str):
    """Alice owns the default board; add Bob to it as ``role`` and mint Bob a PAT.

    Returns ``(alice, board_id, a_card, a_epic, pat)`` where ``pat`` is a
    :class:`_Pat` acting as Bob. The card + epic are Alice's rows on board B, so the
    PAT can exercise read/write/manage against them. Board B is a board Bob does
    **not** own; his only path to it is the member row.
    """
    alice = login_as(*ALICE)  # first login claims the default board
    board_id = alice.get(BOARDS).json()[0]["id"]
    a_card = alice.post(CARDS, json={"title": "seed", "board_id": board_id}).json()
    a_epic = alice.post(EPICS, json={"name": "seed-epic", "board_id": board_id}).json()

    bob = login_as(*BOB)  # creates Bob's user, who owns nothing
    added = alice.post(_members_url(board_id), json={"email": BOB[0], "role": role})
    assert added.status_code == 201
    raw = bob.post(TOKENS, json={"name": "bob-agent"}).json()["token"]
    return alice, board_id, a_card, a_epic, _Pat(client, raw)


# --- viewer member: PAT reads B, cannot write --------------------------------


def test_pat_viewer_member_can_read(login_as, client):
    _alice, board_id, a_card, a_epic, pat = _setup_member_pat(login_as, client, "viewer")

    # A board Bob only reaches through a viewer membership row is READable via the PAT.
    assert pat.get(f"{BOARDS}/{board_id}").status_code == 200
    assert pat.get(f"{CARDS}/{a_card['id']}").status_code == 200
    assert pat.get(f"{EPICS}/{a_epic['id']}").status_code == 200
    assert pat.get(CARDS, params={"board_id": board_id}).status_code == 200
    assert pat.get(EPICS, params={"board_id": board_id}).status_code == 200
    assert pat.get(_members_url(board_id)).status_code == 200


def test_pat_viewer_member_cannot_write(login_as, client):
    _alice, board_id, a_card, a_epic, pat = _setup_member_pat(login_as, client, "viewer")
    cid, eid = a_card["id"], a_epic["id"]

    assert pat.post(CARDS, json={"title": "x", "board_id": board_id}).status_code == 403
    assert pat.patch(f"{CARDS}/{cid}", json={"title": "x"}).status_code == 403
    assert pat.post(f"{CARDS}/{cid}/move", json={"column": "done"}).status_code == 403
    assert pat.delete(f"{CARDS}/{cid}").status_code == 403
    assert pat.post(EPICS, json={"name": "x", "board_id": board_id}).status_code == 403
    assert pat.patch(f"{EPICS}/{eid}", json={"name": "x"}).status_code == 403
    assert pat.delete(f"{EPICS}/{eid}").status_code == 403


# --- editor member: PAT reads + writes B, cannot manage ----------------------


def test_pat_editor_member_can_read_and_write(login_as, client):
    _alice, board_id, a_card, a_epic, pat = _setup_member_pat(login_as, client, "editor")
    cid, eid = a_card["id"], a_epic["id"]

    # Reads.
    assert pat.get(f"{BOARDS}/{board_id}").status_code == 200
    assert pat.get(f"{CARDS}/{cid}").status_code == 200
    # Writes: create / edit / move / delete cards + epics on a *member* board.
    made = pat.post(CARDS, json={"title": "via-pat", "board_id": board_id})
    assert made.status_code == 201
    assert pat.patch(f"{CARDS}/{cid}", json={"title": "edited"}).status_code == 200
    assert pat.post(f"{CARDS}/{cid}/move", json={"column": "done"}).status_code == 200
    assert pat.delete(f"{CARDS}/{made.json()['id']}").status_code == 204
    epic = pat.post(EPICS, json={"name": "via-pat", "board_id": board_id})
    assert epic.status_code == 201
    assert pat.patch(f"{EPICS}/{eid}", json={"name": "e2"}).status_code == 200
    assert pat.delete(f"{EPICS}/{epic.json()['id']}").status_code == 204


def test_pat_editor_member_cannot_manage(login_as, client):
    alice, board_id, _card, _epic, pat = _setup_member_pat(login_as, client, "editor")
    # A member row the PAT might try to touch (added by the owner, Alice).
    carol = login_as(*CAROL)
    carol_id = carol.get("/users/me").json()["id"]
    member_id = alice.post(
        _members_url(board_id), json={"user_id": carol_id, "role": "viewer"}
    ).json()["id"]
    member_url = f"{_members_url(board_id)}/{member_id}"

    # Board rename / delete are MANAGE (owner-only) — an editor PAT is forbidden.
    assert pat.patch(f"{BOARDS}/{board_id}", json={"name": "x"}).status_code == 403
    assert pat.delete(f"{BOARDS}/{board_id}").status_code == 403
    # Member management (add / change-role / remove) is MANAGE too.
    assert pat.post(_members_url(board_id), json={"email": CAROL[0]}).status_code == 403
    assert pat.patch(member_url, json={"role": "editor"}).status_code == 403
    assert pat.delete(member_url).status_code == 403


# --- owner-role member: PAT gets full MANAGE access --------------------------


def test_pat_owner_role_member_can_manage(login_as, client):
    _alice, board_id, _card, _epic, pat = _setup_member_pat(login_as, client, "owner")

    # Board rename works for an owner-role member's PAT.
    assert pat.patch(f"{BOARDS}/{board_id}", json={"name": "renamed"}).status_code == 200
    # Member management works too.
    carol = login_as(*CAROL)
    carol_id = carol.get("/users/me").json()["id"]
    added = pat.post(_members_url(board_id), json={"user_id": carol_id, "role": "viewer"})
    assert added.status_code == 201
    member_url = f"{_members_url(board_id)}/{added.json()['id']}"
    assert pat.patch(member_url, json={"role": "editor"}).status_code == 200
    assert pat.delete(member_url).status_code == 204


# --- non-member, non-owner PAT is still forbidden on B -----------------------


def test_pat_non_member_non_owner_is_403(login_as, client):
    alice = login_as(*ALICE)  # owns the default board
    board_id = alice.get(BOARDS).json()[0]["id"]
    a_card = alice.post(CARDS, json={"title": "secret", "board_id": board_id}).json()

    bob = login_as(*BOB)  # not a member of B, owns nothing on it
    raw = bob.post(TOKENS, json={"name": "outsider"}).json()["token"]
    pat = _Pat(client, raw)

    assert pat.get(f"{BOARDS}/{board_id}").status_code == 403
    assert pat.get(f"{CARDS}/{a_card['id']}").status_code == 403
    assert pat.get(CARDS, params={"board_id": board_id}).status_code == 403
    assert pat.post(CARDS, json={"title": "x", "board_id": board_id}).status_code == 403
    assert pat.get(_members_url(board_id)).status_code == 403
