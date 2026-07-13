"""SQLAlchemy ORM models: Board, Card (a story on a board) and Epic (CONTEXT §3,
ADR 0006 + ADR 0009 + ADR 0012).

Three tables. A **board** owns a set of cards + epics (M3 V7, ADR 0012); a
**card** is a story on a board; an **epic** is a separate grouping a story can
belong to (ADR 0009). Key mechanisms:
- Each table's ``ticket_number`` is assigned atomically at INSERT from its own
  Postgres SEQUENCE via a server_default — ``'KAN-' || nextval('card_ticket_seq')``
  for cards, ``'EPIC-' || nextval('epic_ticket_seq')`` for epics — immutable, never
  reused, and independent (KAN-1 and EPIC-1 can coexist). Ticket sequences stay
  **global** across boards (D4) — no per-board prefixes.
- ``column`` is a plain ``varchar`` guarded by a CHECK constraint (not a native PG
  enum) so new column values need no ``ALTER TYPE`` migration (ADR 0008).
- Every card + epic belongs to exactly one board via a NOT NULL ``board_id`` FK
  (R2.3). ``ON DELETE CASCADE`` — deleting a board removes its cards + epics.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

VALID_COLUMNS = ("todo", "in_progress", "done")
# Board-membership roles (KAN-12), aligned with ADR 0013's ownership language.
# A plain varchar guarded by a CHECK constraint (the same pattern as ``card.column``)
# so adding a role later needs no ``ALTER TYPE`` migration.
VALID_ROLES = ("viewer", "editor", "owner")
# Activity-log vocabulary (KAN-17, M4 audit trail). Both are plain varchars guarded
# by CHECK constraints (the ``card.column`` pattern) so a new entity type or action
# needs no ``ALTER TYPE`` migration.
VALID_ACTIVITY_ENTITY_TYPES = ("card", "epic", "board")
VALID_ACTIVITY_ACTIONS = ("created", "updated", "deleted", "moved")


class Board(Base):
    """A board owns a set of cards + epics (M3 V7, ADR 0012). ``owner_id`` is the
    human who owns it (nullable — the migrated default board is unclaimed until a
    user takes it; board authorization on ownership arrives in V8)."""

    __tablename__ = "board"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # FK → user.id (a UUID). ON DELETE SET NULL: deleting a user unclaims their
    # boards rather than cascading away the boards + all their cards.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    # Auto-sync opt-in (KAN-43): the GitHub webhook only touches a board's cards
    # when ``autosync_enabled`` is true — per-board opt-in, default OFF, so the
    # webhook is a no-op for any board that hasn't turned it on. ``advance_to_done``
    # is a SEPARATE opt-in gating only the "move card to done on PR merge" action,
    # keeping the human in the loop for 'done' even with auto-sync otherwise on.
    autosync_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    autosync_advance_to_done: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class BoardMember(Base):
    """A user's membership of a board with a role (KAN-12).

    Grants a user (other than the board owner) some access to a board. Roles are
    ``viewer`` / ``editor`` / ``owner`` (``VALID_ROLES``), guarded by a CHECK
    constraint in the ``card.column`` varchar style. A ``UNIQUE(board_id, user_id)``
    keeps a user's membership of a board singular.

    Both FKs ``ON DELETE CASCADE`` — deleting a board or a user removes the
    membership row (consistent with the app's hard-delete model). Role-based
    enforcement is live (KAN-13): ``app.authz.authorize_board`` maps a member's role
    to an :class:`app.authz.Access` level (viewer→READ, editor→WRITE, owner→MANAGE)
    and gates each route accordingly. List-visibility scoping (KAN-15) is separate.
    """

    __tablename__ = "board_member"
    __table_args__ = (
        UniqueConstraint("board_id", "user_id", name="uq_board_member"),
        CheckConstraint(
            "role IN ('viewer', 'editor', 'owner')",
            name="ck_board_member_role",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    board_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("board.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The member user (a UUID). CASCADE: deleting a user removes their memberships.
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Epic(Base):
    """A board-less grouping of stories (ADR 0009). No column/position/assignee/
    story_points — an epic is not a board card and is too large to estimate or
    own individually."""

    __tablename__ = "epic"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ticket_number: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
        # Assigned by the DB at INSERT; the sequence is created in the migration.
        server_default=text("'EPIC-' || nextval('epic_ticket_seq')"),
    )
    # The board this epic belongs to (M3 V7). NOT NULL; cascade on board delete.
    board_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("board.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CardDependency(Base):
    """A directed blocker→blocked edge between two cards on the same board
    (KAN-28, the foundation for the dependency line).

    ``blocker_id`` blocks ``blocked_id`` — i.e. the blocked card is *blocked-by*
    the blocker. Both FKs ``ON DELETE CASCADE`` so deleting a card removes any edge
    it participates in (consistent with the app's hard-delete model). A
    ``UNIQUE(blocker_id, blocked_id)`` constraint keeps an edge singular. The
    same-board rule, self-link ban and cycle prevention are enforced in the router
    (``routers/cards.py``), not the schema — they can't be a table constraint.
    """

    __tablename__ = "card_dependency"
    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id", name="uq_card_dependency_edge"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    blocker_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("card.id", ondelete="CASCADE"), nullable=False
    )
    blocked_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("card.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CardLink(Base):
    """A work-link on a card (KAN-32): a ``label`` (e.g. "PR", "branch", "CI") and
    a ``url`` pointing at the card's real work state, so the board reflects git
    reality without manual reconciliation.

    ``card_id`` FK ``ON DELETE CASCADE`` — deleting a card removes its links
    (consistent with the app's hard-delete model). The non-empty ``label``/``url``
    rule is enforced by the Pydantic schema (``schemas.LinkCreate``), not the table.
    """

    __tablename__ = "card_link"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    card_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("card.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CardComment(Base):
    """A human/agent-authored note on a card (KAN-33): intentional context — a
    decision, a handoff, "why this is blocked". **Distinct from Epic 4's SYSTEM
    activity log** (KAN-17..20, not yet built): those are machine-generated audit
    events; a ``CardComment`` is a deliberate note written by a real principal.

    ``card_id`` FK ``ON DELETE CASCADE`` — deleting a card removes its comments
    (consistent with the app's hard-delete model). ``author_id`` FK → ``user`` is
    nullable with ``ON DELETE SET NULL``, so deleting the author keeps the note
    (mirrors ``Board.owner_id``). The non-empty ``body`` rule is enforced by the
    Pydantic schema (``schemas.CommentCreate``), not the table.
    """

    __tablename__ = "card_comment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    card_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("card.id", ondelete="CASCADE"), nullable=False
    )
    # The authoring user (a UUID). Nullable + SET NULL so a deleted author leaves
    # the note in place, unattributed (mirrors Board.owner_id).
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Card(Base):
    __tablename__ = "card"
    __table_args__ = (
        CheckConstraint(
            "\"column\" IN ('todo', 'in_progress', 'done')",
            name="ck_card_column",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ticket_number: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
        # Assigned by the DB at INSERT; the sequence is created in the migration.
        server_default=text("'KAN-' || nextval('card_ticket_seq')"),
    )
    # The board this story lives on (M3 V7). NOT NULL; cascade on board delete.
    board_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("board.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    column: Mapped[str] = mapped_column(String(32), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # Optional link to the story's parent epic. ON DELETE SET NULL so deleting an
    # epic detaches (rather than blocks or cascades) its stories — consistent with
    # the app's hard-delete model.
    epic_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("epic.id", ondelete="SET NULL"), nullable=True
    )
    story_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assignee: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Activity(Base):
    """An append-only audit record of a board-domain mutation (KAN-17, M4 R5.1).

    One row per successful create / update / delete / move of a card, epic or
    board — the seed of the activity feed KAN-18 will read (this card is the model
    + write path only; there is no read API or UI here yet).

    Design notes:
    - ``board_id`` FK → ``board`` (``ON DELETE CASCADE``): an activity always
      belongs to a board, and a board's whole audit trail is hard-deleted with it
      (consistent with the app's hard-delete model). A **board deletion** event is
      therefore intentionally ephemeral — recorded, then cascaded away with the
      board it describes.
    - ``entity_id`` is a plain integer, **not** an FK — the referenced card/epic may
      already be deleted (that's precisely a ``deleted`` event), so the audit row
      must outlive it.
    - ``actor_user_id`` FK → ``user`` (``ON DELETE SET NULL``, nullable, mirroring
      ``Board.owner_id`` / ``CardComment.author_id``) records the acting principal —
      always a real ``User`` today (``app.authz.get_principal``), but kept nullable so
      deleting the user leaves the history in place, unattributed. ``actor_label`` is
      a denormalised human handle (the principal's email / an assignee string) so the
      feed reads without a user join even after the user is gone.
    - ``entity_type`` / ``action`` are varchars guarded by CHECK constraints (the
      ``card.column`` pattern) rather than native PG enums.
    """

    __tablename__ = "activity"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('card', 'epic', 'board')",
            name="ck_activity_entity_type",
        ),
        CheckConstraint(
            "action IN ('created', 'updated', 'deleted', 'moved')",
            name="ck_activity_action",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    board_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("board.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The acting principal (a UUID). Nullable + SET NULL so a deleted user leaves the
    # audit row in place (mirrors Board.owner_id / CardComment.author_id).
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    # Denormalised human handle for the actor (email / assignee string), so the feed
    # reads without a user join and survives the user's deletion.
    actor_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # The affected card/epic/board id. NOT an FK — the entity may already be deleted.
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
