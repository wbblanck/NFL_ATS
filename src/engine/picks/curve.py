"""Season path for the dashboard: cumulative (wins - losses) game by game against the pool line for the official
pick, the four tracked models (hybrid, team-only v1, player v3, key-number variant) and two no-skill baselines (always the pool-line favorite, always the home team), with the 95% band
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

SERIES = [("official", "Official pick"), ("hybrid", "Hybrid"), ("v1", "Team-only projection"),
          ("v3", "Player projection"), ("keynum", "Key-number variant"), ("favorite", "Always the favorite"),
          ("home", "Always the home team")]
# graded live row field per tracked model ('TEAM W' or a bare 'W'/'L' for keynum, see engine.picks.live).
# v3 games without a published injury report are left out of its score there, so they are left out here too.
LIVE_FIELD = {"hybrid": "hybrid", "v1": "proj_proj-poisson-v1", "v3": "proj_proj-players-v3"}


def _team(v) -> str | None:
    v = (v or "").strip()
    return v.split(" ")[0] or None


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
            gr = graded[gid]
            picks = {"official": preds[gid]["pick_team"], "keynum": gr.get("shadow_pick") or None,
                     **{k: _team(gr.get(f)) for k, f in LIVE_FIELD.items()}}
        else:
            b = bt.get(gid, {})
            picks = {k: b.get(k) for k in ("official", "hybrid", "v1", "v3", "keynum")}
        picks["favorite"] = g["home_team"] if line < 0 else g["away_team"]
        picks["home"] = g["home_team"]
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
