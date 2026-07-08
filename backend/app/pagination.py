"""Keyset (seek) pagination helpers for the card query API (Milestone 2 V3, P4).

The list endpoint pages by an opaque cursor over the stable sort key
``(updated_at, id)`` — not offset/limit — so pages stay disjoint and gap-free
even as rows change between requests. A cursor is just the last-seen row's
``(updated_at, id)`` encoded as URL-safe base64 of ``"<updated_at ISO>|<id>"``;
it is deliberately opaque to clients (they echo back the ``X-Next-Cursor``
header, nothing more).

Kept as a tiny pure module so the codec is unit-testable without a database.
"""
from __future__ import annotations

import base64
import binascii
from datetime import datetime

# The header a paginated response uses to hand back the next page's cursor.
NEXT_CURSOR_HEADER = "X-Next-Cursor"


def encode_cursor(updated_at: datetime, card_id: int) -> str:
    """Encode a ``(updated_at, id)`` sort key into an opaque cursor string."""
    raw = f"{updated_at.isoformat()}|{card_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    """Decode a cursor back into ``(updated_at, id)``.

    Raises ``ValueError`` on any malformed input (bad base64, missing separator,
    unparseable timestamp or id) so the caller can turn it into a 422.
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise ValueError("malformed cursor") from exc
    # rsplit: the ISO timestamp itself contains no '|', so the last '|' splits
    # cleanly even though the timestamp has colons/plus signs.
    updated_at_str, sep, id_str = raw.rpartition("|")
    if not sep:
        raise ValueError("malformed cursor: missing separator")
    try:
        return datetime.fromisoformat(updated_at_str), int(id_str)
    except ValueError as exc:
        raise ValueError("malformed cursor: bad key") from exc
