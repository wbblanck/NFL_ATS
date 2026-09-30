"""Tracked comparison, never used to pick (docs/hybrid_tracking.md): the live pick when the market moved 1+ point
off the pool line, otherwise the proj-poisson-v1 pick against the pool line. Derived from rows written at lock
(predictions.csv drift and pick, projections.csv v1 pick), so it cannot use anything after the lock."""
from __future__ import annotations

VERSION = "hybrid-v1-lowmove"
MIN_MOVE = 1.0


def _drift(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def pick(live_pick: str | None, drift, v1_pick: str | None) -> tuple[str | None, str]:
    """(team, source): source is 'market' (moved 1+ pt, or no usable drift or v1 pick) or 'v1'."""
    d = _drift(drift)
    if d is None or abs(d) >= MIN_MOVE or not v1_pick:
        return live_pick, "market"
    return v1_pick, "v1"
