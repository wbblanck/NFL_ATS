"""Season table for the dashboard: each model's record by week. Live weeks come from the graded picks;
2026 weeks 1-2 (before live tracking) come from the backtest in data/backtests/early2026.json and are marked."""
from __future__ import annotations

import json

from engine import config

MODELS = [("official", "Official pick"), ("keynum", "Key-number variant"), ("v3", "Player projection"),
          ("v1", "Team-only projection"), ("hybrid", "Hybrid")]
LIVE_KEY = {"official": "result", "keynum": "shadow_result", "v1": "proj_proj-poisson-v1",
            "v3": "proj_proj-players-v3", "hybrid": "hybrid"}


def _wl(v) -> str | None:
    v = (v or "").strip()
    return v[-1] if v[-1:] in ("W", "L") else None


def backtest_rows(season: int) -> list[dict]:
    p = config.ROOT / "data" / "backtests" / "early2026.json"
    if season != 2026 or not p.exists():
        return []
    return json.loads(p.read_text())["games"]


def build(graded: list[dict], season: int) -> list[dict]:
    """[{week, kind: 'backtest'|'live', n, rec: {model: [W, L]}}] in week order."""
    weeks: dict[tuple[int, str], dict] = {}
    for r in backtest_rows(season):
        w = weeks.setdefault((int(r["week"]), "backtest"), {m: [0, 0] for m, _ in MODELS})
        for m, _ in MODELS:
            if r.get(m):
                w[m][0 if r[m] == r["covered"] else 1] += 1
    for r in graded:
        if int(r["season"]) != season:
            continue
        w = weeks.setdefault((int(r["week"]), "live"), {m: [0, 0] for m, _ in MODELS})
        for m, _ in MODELS:
            x = _wl(r.get(LIVE_KEY[m]))
            if x:
                w[m][0 if x == "W" else 1] += 1
    return [{"week": wk, "kind": kind, "rec": rec} for (wk, kind), rec in sorted(weeks.items())]
