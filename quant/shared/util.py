"""Small shared helpers for the ``src/`` pipeline (keep this module narrow)."""

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """UTC timestamp in ISO 8601 (used for JSON audit fields and worker SSE events)."""
    return datetime.now(timezone.utc).isoformat()
