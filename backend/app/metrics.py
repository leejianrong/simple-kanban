"""Derived fleet-reporting metrics (M5 V17, KAN-250) — a pure computation layer.

The board metrics endpoint (``GET /api/v1/boards/{id}/metrics``) reports flow
numbers that are **entirely derived** from data already recorded elsewhere — the
:class:`app.models.Activity` audit feed (KAN-17/18) plus current card state. There
is **no new write path and no migration**: reporting rides the activity feed.

Two responsibilities live here, both pure (no DB, no I/O) so they unit-test
directly:

- :func:`parse_move_target` — recover the *destination column* of a card move from
  an activity row's ``summary`` text. The ``Activity`` model deliberately stores no
  structured target column (``summary`` is a human sentence), so we parse the two
  known producers: ``routers/cards.py``'s ``move_card`` (``"moved KAN-3 from todo
  to in_progress"``) and ``routers/boards.py``'s ``dispatch`` (``"dispatched KAN-3
  to <assignee>"`` — always a move into ``in_progress``). A same-column reorder
  (``"moved KAN-3 to done"``) is **not** a transition and yields ``None``.
- :func:`compute_metrics` — turn the parsed column transitions + current card state
  into throughput / cycle-time / aging-WIP / per-assignee numbers over a period.

Keeping these off the router keeps the derivation testable without a database and
the coupling to the summary wording documented in exactly one place.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime
from statistics import mean, median
from typing import Any

# The valid board columns (mirrors ``models.VALID_COLUMNS``; kept local so this pure
# module has no import-time dependency on the ORM). Only ``in_progress``/``done``
# transitions drive the metrics, but we accept any valid column defensively.
_VALID_COLUMNS = ("todo", "in_progress", "done")

# ``move_card`` cross-column summary: "moved <ticket> from <src> to <dst>".
_MOVE_FROM_TO = re.compile(r"^moved \S+ from (?P<src>\w+) to (?P<dst>\w+)$")


def parse_move_target(summary: str) -> str | None:
    """Return the destination column of a **cross-column** card move recorded in an
    activity ``summary``, or ``None`` when the summary is a same-column reorder or is
    not a recognised move sentence.

    Recognised producers (the only two that write ``action="moved"`` for a card):

    - ``dispatch`` → ``"dispatched <ticket> to <assignee>"`` — always a move into
      ``in_progress`` (a todo card is claimed and started).
    - ``move_card`` cross-column → ``"moved <ticket> from <src> to <dst>"`` → ``dst``.
    - ``move_card`` same-column reorder → ``"moved <ticket> to <dst>"`` — not a
      transition (``src == dst``), so ``None``.
    """
    if summary.startswith("dispatched "):
        return "in_progress"
    match = _MOVE_FROM_TO.match(summary)
    if match:
        dst = match.group("dst")
        return dst if dst in _VALID_COLUMNS else None
    return None


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Nearest-rank percentile of an already-sorted, non-empty list."""
    rank = math.ceil(pct / 100 * len(sorted_values))
    return sorted_values[max(1, min(rank, len(sorted_values))) - 1]


def _summarize_durations(values: list[float]) -> dict[str, Any]:
    """avg / median / p90 (seconds) of a duration sample, or nulls when empty."""
    if not values:
        return {
            "count": 0,
            "avg_seconds": None,
            "median_seconds": None,
            "p90_seconds": None,
        }
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "avg_seconds": mean(ordered),
        "median_seconds": median(ordered),
        "p90_seconds": _percentile(ordered, 90),
    }


def compute_metrics(
    transitions: list[tuple[int, str, datetime]],
    cards: list[dict[str, Any]],
    *,
    now: datetime,
    since: datetime | None,
) -> dict[str, Any]:
    """Compute the derived board metrics — pure, no DB.

    ``transitions`` is the parsed list of cross-column card moves as
    ``(card_id, target_column, ts)`` (see :func:`parse_move_target`). ``cards`` is
    the board's current card state — dicts with ``id``, ``ticket_number``,
    ``column``, ``assignee``, ``created_at`` and ``deleted`` (a bool). ``now`` is the
    reference time (period end + aging clock); ``since`` bounds the period
    (``None`` → all time).

    Returns the ``throughput`` / ``cycle_time`` / ``aging_wip`` / ``by_assignee``
    payload the ``BoardMetricsRead`` schema wraps. Metrics are derived so:

    - **throughput** — count of distinct cards that first reached ``done`` within
      ``[since, now]`` (from ``done`` transitions).
    - **cycle_time** — for those done-in-period cards that also have a first
      ``in_progress`` transition at/before their ``done``, the seconds between the
      two; reported as count/avg/median/p90.
    - **aging_wip** — cards *currently* ``in_progress`` (live rows), aged from their
      last ``in_progress`` transition (falling back to ``created_at`` when a card
      entered progress without a recorded move).
    - **by_assignee** — per current-assignee throughput (done in period) and open
      WIP (currently in progress), the "which agent did what" view.
    """
    first_in_progress: dict[int, datetime] = {}
    last_in_progress: dict[int, datetime] = {}
    first_done: dict[int, datetime] = {}
    for card_id, column, ts in transitions:
        if column == "in_progress":
            if card_id not in first_in_progress or ts < first_in_progress[card_id]:
                first_in_progress[card_id] = ts
            if card_id not in last_in_progress or ts > last_in_progress[card_id]:
                last_in_progress[card_id] = ts
        elif column == "done":
            if card_id not in first_done or ts < first_done[card_id]:
                first_done[card_id] = ts

    def in_period(ts: datetime) -> bool:
        return (since is None or ts >= since) and ts <= now

    # Throughput: distinct cards that first reached done within the period.
    done_in_period = {cid for cid, ts in first_done.items() if in_period(ts)}

    # Cycle time: first in_progress → done, for done-in-period cards that were ever
    # in progress at/before completion.
    cycle_seconds: list[float] = []
    for cid in done_in_period:
        started = first_in_progress.get(cid)
        done_ts = first_done[cid]
        if started is not None and started <= done_ts:
            cycle_seconds.append((done_ts - started).total_seconds())

    # Aging WIP: cards currently in_progress (live only), aged from their last entry
    # into in_progress (or created_at when there's no recorded move).
    card_by_id = {c["id"]: c for c in cards}
    wip_cards = [
        c for c in cards if c["column"] == "in_progress" and not c["deleted"]
    ]
    aging_items = []
    for card in wip_cards:
        entered = last_in_progress.get(card["id"]) or card["created_at"]
        aging_items.append(
            {
                "card_id": card["id"],
                "ticket_number": card["ticket_number"],
                "assignee": card["assignee"],
                "age_seconds": (now - entered).total_seconds(),
            }
        )
    aging_items.sort(key=lambda item: item["age_seconds"], reverse=True)
    ages = [item["age_seconds"] for item in aging_items]
    aging_wip = {
        "count": len(wip_cards),
        "avg_seconds": mean(ages) if ages else None,
        "max_seconds": max(ages) if ages else None,
        "items": aging_items,
    }

    # Per-assignee: throughput (done in period) + open WIP, keyed on the card's
    # *current* assignee (None → unassigned).
    tallies: dict[str | None, dict[str, int]] = defaultdict(
        lambda: {"throughput": 0, "wip": 0}
    )
    for cid in done_in_period:
        card = card_by_id.get(cid)
        assignee = card["assignee"] if card else None
        tallies[assignee]["throughput"] += 1
    for card in wip_cards:
        tallies[card["assignee"]]["wip"] += 1
    # Stable, readable order: busiest first (throughput+wip), unassigned last.
    by_assignee = [
        {"assignee": assignee, "throughput": t["throughput"], "wip": t["wip"]}
        for assignee, t in tallies.items()
    ]
    by_assignee.sort(
        key=lambda row: (
            row["assignee"] is None,
            -(row["throughput"] + row["wip"]),
            row["assignee"] or "",
        )
    )

    return {
        "throughput": len(done_in_period),
        "cycle_time": _summarize_durations(cycle_seconds),
        "aging_wip": aging_wip,
        "by_assignee": by_assignee,
    }
