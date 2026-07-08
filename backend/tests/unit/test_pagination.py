"""Unit tests for the keyset cursor codec (app.pagination).

Pure logic — no database, no HTTP. The cursor is opaque base64 of
``"<updated_at ISO>|<id>"``; these pin the round-trip and that malformed input
raises ValueError (which the router turns into a 422).
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone

import pytest

from app.pagination import decode_cursor, encode_cursor


def _b64(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode()).decode()


def test_cursor_round_trips():
    dt = datetime(2026, 7, 8, 1, 2, 3, 456789, tzinfo=timezone.utc)
    decoded_dt, decoded_id = decode_cursor(encode_cursor(dt, 42))
    assert decoded_dt == dt
    assert decoded_id == 42


def test_cursor_is_opaque_base64_not_the_raw_key():
    token = encode_cursor(datetime(2026, 1, 1, tzinfo=timezone.utc), 7)
    # No raw separator/timestamp leaking through — it's encoded.
    assert "|" not in token
    assert "2026" not in token


@pytest.mark.parametrize(
    "bad",
    [
        "not-base64!!",                              # not valid base64
        "",                                          # empty
        _b64("no-separator-here"),                   # decodes but has no '|'
        _b64("2026-07-08T00:00:00+00:00|not-int"),   # good timestamp, bad id
        _b64("nonsense|123"),                        # bad timestamp, good id
        _b64("|123"),                                # empty timestamp
    ],
)
def test_decode_rejects_malformed(bad):
    with pytest.raises(ValueError):
        decode_cursor(bad)
