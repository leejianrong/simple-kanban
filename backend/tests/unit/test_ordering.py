"""Unit tests for the dispatch priority ranking (app.ordering, M5 V12 / KAN-245).

Pure logic — no database, no HTTP, no Docker. The dispatch selection orders ready
cards by ``priority DESC`` then position, mapping the ``priority`` varchar to an
integer rank; this exercises that mapping (``priority_rank`` / ``PRIORITY_RANK``)
directly so a regression in the ordering is caught in the fast `unit` CI job.
"""
from __future__ import annotations

from app.ordering import PRIORITY_RANK, priority_rank


def test_rank_is_monotonic_none_to_urgent():
    # none < low < medium < high < urgent — the exact dispatch order.
    ranks = [priority_rank(p) for p in ("none", "low", "medium", "high", "urgent")]
    assert ranks == sorted(ranks)
    assert ranks == [0, 1, 2, 3, 4]


def test_urgent_outranks_low():
    assert priority_rank("urgent") > priority_rank("low")


def test_sorting_by_rank_desc_puts_urgent_first():
    # A shuffled set of priorities, sorted by rank descending (how dispatch picks).
    priorities = ["low", "urgent", "none", "high", "medium"]
    ordered = sorted(priorities, key=priority_rank, reverse=True)
    assert ordered == ["urgent", "high", "medium", "low", "none"]


def test_unknown_priority_ranks_as_none():
    # A value outside the vocabulary never jumps the queue — it ranks like ``none``.
    assert priority_rank("bogus") == priority_rank("none") == 0


def test_rank_covers_exactly_the_vocabulary():
    assert set(PRIORITY_RANK) == {"none", "low", "medium", "high", "urgent"}
