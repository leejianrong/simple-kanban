"""Activity-log write path (KAN-17, M4 audit trail — R5.1).

A single flat helper the mutation routers call to append one :class:`app.models.Activity`
row per successful board-domain change (create / update / delete / move of a card,
epic or board). Matches the deliberately flat backend style (ADR 0008 — no
service/repository layer): routers call :func:`record_activity` directly.

**This is the write path only.** The read API + feed UI are KAN-18; nothing here
serves activity rows.

The helper *adds* the row to the caller's session but does **not** commit — the
router commits it in the **same transaction** as the mutation it describes, so the
audit row and the change it records land (or roll back) atomically. On create, the
router commits the new entity first (to obtain its server-assigned id / ticket
number), then records the activity and commits again — still exactly one row.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .auth_models import User
from .models import Activity


def record_activity(
    db: Session,
    principal: User,
    *,
    board_id: int,
    entity_type: str,
    entity_id: int,
    action: str,
    summary: str,
    from_column: str | None = None,
    to_column: str | None = None,
) -> Activity:
    """Append one activity row for a board-domain mutation (added, not committed).

    ``principal`` is the acting user (``app.authz.get_principal``): its id is stored
    as ``actor_user_id`` and its email as the denormalised ``actor_label``.
    ``entity_type`` ∈ {``card``, ``epic``, ``board``}; ``action`` ∈ {``created``,
    ``updated``, ``deleted``, ``moved``, ``restored``, ``attention``, ``resolved``,
    ``purged``} — both CHECK-constrained on the table.
    ``summary`` is a short human sentence (e.g. ``"created KAN-3: Fix login"``).

    ``from_column`` / ``to_column`` (M5 V17, KAN-260) record the **structured** column
    transition of a ``moved`` event, so the metrics layer reads them instead of
    parsing ``summary``. The move/dispatch handlers pass them; every other caller
    leaves them ``None`` (they only apply to moves).
    """
    activity = Activity(
        board_id=board_id,
        actor_user_id=principal.id,
        actor_label=principal.email,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        summary=summary,
        from_column=from_column,
        to_column=to_column,
    )
    db.add(activity)
    return activity
