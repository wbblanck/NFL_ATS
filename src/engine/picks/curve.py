"""Season path for the dashboard: cumulative (wins - losses) game by game against the pool line for the official
pick, the hybrid and two no-skill baselines (always the pool-line favorite, always the home team), with the 95% band
a coin-flipper lands in. Live games use the picks recorded at lock; games without a live pick (2026 weeks 1-2 and
ATL@GB) use the backtest in data/backtests/early2026.json and are marked."""
from __future__ import annotations

import json
import math

import polars as pl

from engine import config
from engine.data import league_lines, store
from engine.picks import final
from engine.picks.grading import Result, grade_league

SERIES = [("official", "Official pick"), ("hybrid", "Hybrid (tracked)"), ("favorite", "Always the favorite"),
          ("home", "Always the home team")]


def _backtest(season: int) -> dict:
    p = config.ROOT / "data" / "backtests" / "early2026.json"
    if season != 2026 or not p.exists():
        return {}
    return {g["game_id"]: g for g in json.loads(p.read_text())["games"]}


def build(sched: pl.DataFrame, season: int, live_rows: list[dict]) -> dict:
    """{'games': [{i, id, label, kind, d: {series: +1/-1}}], 'cum': {series: [..]}, 'band': [..], 'verdict': str}"""
    lines = {r["game_id"]: r for r in league_lines.load()}
    preds = {p["game_id"]: p for p in store.read_rows(final.predictions_path()) if not p.get("supersedes")}
    graded = {r["game_id"]: r for r in live_rows}
    bt = _backtest(season)
    done = sched.filter(pl.col("season") == season, pl.col("result").is_not_null()).sort("kickoff_utc", "game_id")
    games, cum = [], {k: [] for k, _ in SERIES}
    tot = {k: 0 for k, _ in SERIES}
    for g in done.iter_rows(named=True):
        gid = g["game_id"]
        ln = lines.get(gid)
        if ln is None:
            continue
        line = float(ln["spread"])
        res = grade_league(g["home_score"], g["away_score"], line)
        if res is Result.PUSH:
            continue
        home_cov = res is Result.HOME_COVER
        win = lambda team: None if team is None else (team == g["home_team"]) == home_cov
        live = gid in preds and gid in graded
        if live:
            off = preds[gid]["pick_team"]
            hy = graded[gid].get("hybrid", "").split(" ")[0] or None
        else:
            b = bt.get(gid, {})
            off, hy = b.get("official"), b.get("hybrid")
        fav = g["home_team"] if line < 0 else g["away_team"]
        picks = {"official": off, "hybrid": hy, "favorite": fav, "home": g["home_team"]}
        d = {}
        for k, team in picks.items():
            w = win(team)
            if w is not None:
                tot[k] += 1 if w else -1
                d[k] = 1 if w else -1
            cum[k].append(tot[k])
        games.append({"id": gid, "label": f"{g['away_team']} @ {g['home_team']}", "week": int(g["week"]),
                      "kind": "live" if live else "backtest", "d": d})
    n = len(games)
    band = [round(1.96 * math.sqrt(i + 1), 2) for i in range(n)]
    out = {"games": games, "cum": cum, "band": band}
    if n:
        z = tot["official"] / math.sqrt(n)
        out["verdict"] = ("Above the luck band" if z > 1.96 else "Below the luck band" if z < -1.96 else
                          "Inside the luck band: too early to tell skill from luck") + \
            f" ({n} games, official {tot['official']:+d} net wins, a coin-flipper would be within ±{round(1.96 * math.sqrt(n))})"
    return out
