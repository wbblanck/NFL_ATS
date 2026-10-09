"""Bettable record for the dashboard (docs/bettable_preregistration.md): each model's pick bet at the line that was
on the board when the pick was made (`market_at_lock`: Pinnacle, or the median of books when Pinnacle had no line),
one unit at -110. Descriptive: it carries no decision rule, and with a few dozen games it cannot tell a real edge from
luck. The backtest numbers come from data/backtests/bettable.json (engine bettable)."""
from __future__ import annotations

import json
import math

import polars as pl

from engine import config
from engine.backtest.bettable import BREAK_EVEN, LOSS, WIN, wilson

LIVE_PICKS = {
    "official": lambda r: r.get("pick"),
    "keynum": lambda r: r.get("shadow_pick") or None,
    "v1": lambda r: _team(r.get("proj_proj-poisson-v1")),
    "v3": lambda r: _team(r.get("proj_proj-players-v3")),
    "hybrid": lambda r: _team(r.get("hybrid")),
}


def _team(v) -> str | None:
    v = (v or "").strip()
    return v.split(" ")[0] or None


def live(graded: list[dict], preds: list[dict], sched: pl.DataFrame) -> dict:
    """{model: {W, L, push, n, win_rate, ci95, units, roi}} for this season's graded picks against the line at the pick."""
    pred_by = {p["game_id"]: p for p in preds if not p.get("supersedes")}
    sc = {r["game_id"]: r for r in sched.filter(pl.col("result").is_not_null()).select(
        "game_id", "home_team", "home_score", "away_score").iter_rows(named=True)}
    out = {}
    for name, pick in LIVE_PICKS.items():
        w = l = push = 0
        for r in graded:
            t, g, p = pick(r), sc.get(r["game_id"]), pred_by.get(r["game_id"])
            mk = (p or {}).get("market_at_lock")
            if not t or g is None or mk in (None, ""):
                continue
            v = (g["home_score"] - g["away_score"]) + float(mk)
            if v == 0:
                push += 1
                continue
            won = (t == g["home_team"]) == (v > 0)
            w += won
            l += (not won)
        n = w + l
        lo, hi = wilson(w, n)
        out[name] = {"W": w, "L": l, "push": push, "n": n, "win_rate": w / n if n else None,
                     "ci95": [lo, hi] if n else None, "units": round(w * WIN + l * LOSS, 2),
                     "roi": (w * WIN + l * LOSS) / n if n else None}
    return out


def backtest() -> dict:
    """Per-model closing-line backtest summaries, or {} before `engine bettable` has been run."""
    p = config.ROOT / "data" / "backtests" / "bettable.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text())
    out = {}
    for k, v in d.get("models", {}).items():
        if k in ("live_sbro_frame", "v1_v3_games", "live_v3_games"):
            continue
        k = "official" if k == "live" else k            # the backtest calls the official pick "live"
        s = v.get("decision") or v["all"]
        out[k] = {"window": v["window"], **{c: s[c] for c in ("n", "W", "L", "win_rate", "ci95", "roi", "units")}}
    dec = {("official" if k == "live" else k): v for k, v in d.get("decision", {}).items()}
    return {"models": out, "break_even": BREAK_EVEN, "decision": dec}
