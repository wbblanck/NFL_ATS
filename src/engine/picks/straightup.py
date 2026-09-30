"""Straight-up (winner) tracker (docs/straightup_preregistration.md). Tracked only; never affects the ATS pick.

Pickers: Market (the side the spread at lock favors, win probability from the live margin distribution), v1 and v3
(the side with more projected points). Live games use what was recorded at lock (predictions.csv market and total,
projections.csv points). Games without live rows are back-filled from the closing line and point-in-time
projections (`backfill`, cached in data/backtests/su_backfill_<season>.json) and marked as backtest.
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl

from engine import config
from engine.data import store
from engine.picks import final

MODELS = [("market", "Market favorite"), ("v3", "Player projection"), ("v1", "Team-only projection")]
V1, V3 = "proj-poisson-v1", "proj-players-v3"


def backfill_path(season: int):
    return config.ROOT / "data" / "backtests" / f"su_backfill_{season}.json"


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def backfill(sched: pl.DataFrame, proj_games: pl.DataFrame, v3_loader, game_ids: list[str]) -> dict:
    """game_id -> {v1_margin, v3_margin} from point-in-time projections (for games with no row recorded at lock)."""
    from engine.models import projection as P
    g = sched.filter(pl.col("game_id").is_in(game_ids))
    feats, m = {}, None
    if v3_loader is not None:
        got = v3_loader(game_ids)
        m = got["model"]
        feats = {(r["game_id"], r["team"]): r for r in got["features"].iter_rows(named=True)}
    out = {}
    for r in g.iter_rows(named=True):
        rt = P.fit(proj_games, r["season"] * 25 + r["week"], r["season"], final.PROJ_H, final.PROJ_LAM)
        h, a = P.FRANCHISE.get(r["home_team"], r["home_team"]), P.FRANCHISE.get(r["away_team"], r["away_team"])
        q = rt.rates(h, a)
        hs, as_ = P.Projection(P.points_pmf(q["home_td"], q["home_fg"], rt.p_xp, rt.p_2),
                               P.points_pmf(q["away_td"], q["away_fg"], rt.p_xp, rt.p_2)).mean_scores()
        row = {"v1_margin": hs - as_, "v3_margin": None}
        fh, fa = feats.get((r["game_id"], h)), feats.get((r["game_id"], a))
        if m is not None and fh and fa and all(f[c] is not None for f in (fh, fa) for c in m["features"]):
            from engine.models import players_v3_live as L
            q3 = {"home_td": q["home_td"] * L.multiplier(fh, m, "td"), "home_fg": q["home_fg"] * L.multiplier(fh, m, "fg"),
                  "away_td": q["away_td"] * L.multiplier(fa, m, "td"), "away_fg": q["away_fg"] * L.multiplier(fa, m, "fg")}
            h3, a3 = P.Projection(P.points_pmf(q3["home_td"], q3["home_fg"], rt.p_xp, rt.p_2),
                                  P.points_pmf(q3["away_td"], q3["away_fg"], rt.p_xp, rt.p_2)).mean_scores()
            row["v3_margin"] = h3 - a3
        out[r["game_id"]] = row
    return out


def rows(sched: pl.DataFrame, season: int, cache: dict | None = None) -> list[dict]:
    """One row per completed regular-season game: week, kind, winner and each picker's pick (None if unavailable)."""
    preds = {p["game_id"]: p for p in store.read_rows(final.predictions_path()) if not p.get("supersedes")}
    projs: dict[tuple[str, str], dict] = {}
    for p in sorted(store.read_rows(final.projections_path()), key=lambda r: r.get("created_at", "")):
        projs[(p["game_id"], p.get("model_version") or V1)] = p
    if cache is None:
        bp = backfill_path(season)
        cache = json.loads(bp.read_text()) if bp.exists() else {}
    done = sched.filter(pl.col("season") == season, pl.col("result").is_not_null(), pl.col("result") != 0) \
        .sort("kickoff_utc")
    out = []
    for g in done.iter_rows(named=True):
        gid, home, away = g["game_id"], g["home_team"], g["away_team"]
        p = preds.get(gid)
        live = p is not None and _f(p.get("market_at_lock")) is not None
        mkt = _f(p["market_at_lock"]) if live else (None if g["spread_line"] is None else -float(g["spread_line"]))
        tot = (_f(p.get("market_total")) if live else None) or _f(g.get("total_line"))
        pw = None
        if mkt is not None:
            td = final.fit_total_dist(sched, g["kickoff_utc"])
            if td is not None and tot is not None:
                pw = float(td.sf(np.zeros(1), np.array([mkt]), np.array([tot]))[0])
            else:
                pw = 0.5 - 0.03 * mkt                                    # rough fallback, flagged by kind
        pick = lambda margin: None if margin is None else (home if margin > 0 else away)
        v1m = v3m = None
        if (gid, V1) in projs:
            r1 = projs[(gid, V1)]
            v1m = _f(r1["proj_home_pts"]) - _f(r1["proj_away_pts"])
        if (gid, V3) in projs:
            r3 = projs[(gid, V3)]
            v3m = _f(r3["proj_home_pts"]) - _f(r3["proj_away_pts"])
        c = cache.get(gid, {})
        v1m = v1m if v1m is not None else c.get("v1_margin")
        v3m = v3m if v3m is not None else c.get("v3_margin")
        out.append({"game_id": gid, "week": int(g["week"]), "kind": "live" if live else "backtest",
                    "winner": home if g["result"] > 0 else away, "p_market_pick": None if pw is None else max(pw, 1 - pw),
                    "market": None if pw is None else (home if pw > 0.5 else away), "v1": pick(v1m), "v3": pick(v3m)})
    return out


def table(rs: list[dict]) -> list[dict]:
    """[{week, kind, rec: {model: [W, L]}, expected}] by week; a week is 'backtest' if any of its games is."""
    weeks: dict[int, dict] = {}
    for r in rs:
        w = weeks.setdefault(r["week"], {"week": r["week"], "kind": "live", "rec": {m: [0, 0] for m, _ in MODELS},
                                         "expected": 0.0})
        if r["kind"] == "backtest":
            w["kind"] = "backtest" if all(x["kind"] == "backtest" for x in rs if x["week"] == r["week"]) else "mixed"
        for m, _ in MODELS:
            if r[m]:
                w["rec"][m][0 if r[m] == r["winner"] else 1] += 1
        if r["p_market_pick"] is not None:
            w["expected"] += r["p_market_pick"]
    return [weeks[k] for k in sorted(weeks)]
