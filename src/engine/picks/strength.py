"""Strength tiers for the picks (docs/strong_calls_report.md): Lean, Solid, Strong, Max by the size of the market move
off the pool line, with each tier's historical win rate from data/backtests/strong_calls.json.

A label is only shown when the pre-registered tests passed (move 2+, move 3+ and the trend, confirmed out of sample).
The pick itself never changes."""
from __future__ import annotations

import json

from engine import config

KEYS = ("lean", "solid", "strong", "max")
LABELS = {"lean": "Lean", "solid": "Solid", "strong": "Strong", "max": "Max"}
CUTS = (1.0, 2.0, 3.0)                     # move < 1 Lean, < 2 Solid, < 3 Strong, else Max (half-point lines)


def tier_key(drift) -> str | None:
    try:
        m = abs(float(drift))
    except (TypeError, ValueError):
        return None
    return KEYS[sum(m >= c for c in CUTS)]


def table() -> dict:
    """{'ok': bool, 'tiers': {key: {...}}} or {} when `engine strong-calls` has not been run."""
    p = config.ROOT / "data" / "backtests" / "strong_calls.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text())
    h = d["hypotheses"]
    ok = all(h[k]["real_strong_call"] for k in ("H1_move_2plus", "H2_move_3plus", "H3_trend"))
    tiers = {}
    for key, name in zip(KEYS, d["tiers"]):
        t = d["by_tier"][name]
        tiers[key] = {"label": LABELS[key], "share": t["share"], "pool": t["all"], "confirmation": t["confirmation"],
                      "close": {k: t["vs_close"][k] for k in ("win_rate", "roi", "n", "ci95")}}
    kc = h["H5_key_cross"]
    return {"ok": bool(ok), "tiers": tiers, "key_cross": {"rate": kc["rate_a"], "rest": kc["rate_b"], "pass": kc["real_strong_call"]},
            "periods": d["periods"]}


def tag(drift, tbl: dict | None = None) -> str:
    """Short label for the alert, e.g. 'Max'; empty when the tiers are not validated or the move is unknown."""
    tbl = table() if tbl is None else tbl
    k = tier_key(drift)
    return LABELS[k] if tbl.get("ok") and k else ""
