"""SQLite-backed cache for SERP and scrape results (keyed per keyword/country/day)."""

import hashlib
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import CacheEntry


def make_key(kind: str, keyword: str, country: str, day: str | None = None) -> str:
    """Stable cache key: sha256(kind|keyword|country|YYYY-MM-DD)."""
    day = day or datetime.now(UTC).strftime("%Y-%m-%d")
    raw = f"{kind}|{' '.join(keyword.lower().split())}|{country.lower()}|{day}"
    return hashlib.sha256(raw.encode()).hexdigest()


def get_cached(db: Session | None, kind: str, keyword: str, country: str) -> dict | None:
    """Return today's cached payload or None."""
    if db is None:
        return None
    entry = db.get(CacheEntry, make_key(kind, keyword, country))
    return entry.payload if entry else None


def set_cached(db: Session | None, kind: str, keyword: str, country: str, payload: dict) -> None:
    """Store/overwrite today's payload."""
    if db is None:
        return
    key = make_key(kind, keyword, country)
    entry = db.get(CacheEntry, key)
    if entry:
        entry.payload = payload
    else:
        db.add(CacheEntry(key=key, kind=kind, payload=payload))
    db.commit()
