"""2026 weeks 1-2, before live tracking began: every tracked model re-run as it would have been at lock.
No pool lines were recorded for these weeks, so the line is a stand-in (CBS odds-page Open, or the user's pool
lines when supplied in `lines`); the market at lock is the nflverse closing spread and total."""
from __future__ import annotations

import datetime as dt
import glob
import re

import polars as pl

from engine import config
from engine.data import cbs_lines
from engine.models import projection as P
from engine.models.margin_dist import MarginDist
from engine.picks import final, hybrid
from engine.picks.grading import Result, grade_league, is_half_point

WEEKS = (1, 2)


def cbs_open_2026(sched: pl.DataFrame) -> dict[str, float]:
    out = {}
    reg = sched.filter(pl.col("season") == 2026)
    for f in sorted(glob.glob(str(config.ROOT / "docs/evidence/probe/*/cbs_odds_2026_w*.html"))):
        if int(re.search(r"_w(\d+)\.html", f).group(1)) not in WEEKS:
            continue
        for r in cbs_lines.match_games(cbs_lines.parse_odds_page(open(f).read()), reg):
            if r.get("game_id") and r.get("spread") is not None:
                out.setdefault(r["game_id"], float(r["spread"]))
    return out


def run(sched: pl.DataFrame, proj_games: pl.DataFrame, v3_loader=None, lines: dict | None = None) -> list[dict]:
    games = sched.filter(pl.col("season") == 2026, pl.col("week").is_in(list(WEEKS)),
                         pl.col("result").is_not_null()).sort("kickoff_utc")
    source = "pool" if lines else "cbs_open"
    lines = lines or cbs_open_2026(sched)
    v3 = None
    if v3_loader is not None:
        v3 = v3_loader(games["game_id"].to_list())
        feats = {(r["game_id"], r["team"]): r for r in v3["features"].iter_rows(named=True)}
    rows = []
    for g in games.iter_rows(named=True):
        line = lines.get(g["game_id"])
        if line is None or not is_half_point(line):
            continue
        now = g["lock_utc"]
        tdist = final.fit_total_dist(sched, now)
        dist, _ = final.fit_dist(sched, now)
        mkt, T = -g["spread_line"], g["total_line"]
        d = final.decide(line, mkt, None, lambda a, b: tdist.cover_probs(a, b, T))
        home, away = g["home_team"], g["away_team"]
        live = home if d["pick"] == "home" else away
        kp = MarginDist(kind=final.SHADOW).fit(dist.c, dist.m).cover_probs(mkt, line)[0]
        rt = P.fit(proj_games, 2026 * 25 + g["week"], 2026, final.PROJ_H, final.PROJ_LAM)
        h, a = P.FRANCHISE.get(home, home), P.FRANCHISE.get(away, away)
        q = rt.rates(h, a)
        v1p = P.Projection(P.points_pmf(q["home_td"], q["home_fg"], rt.p_xp, rt.p_2),
                           P.points_pmf(q["away_td"], q["away_fg"], rt.p_xp, rt.p_2)).p_home_cover(line)
        v3p = None
        if v3 is not None:
            from engine.models import players_v3_live as L
            fh, fa, m = feats.get((g["game_id"], h)), feats.get((g["game_id"], a)), v3["model"]
            if fh and fa and all(f[c] is not None for f in (fh, fa) for c in m["features"]):
                q3 = {"home_td": q["home_td"] * L.multiplier(fh, m, "td"), "home_fg": q["home_fg"] * L.multiplier(fh, m, "fg"),
                      "away_td": q["away_td"] * L.multiplier(fa, m, "td"), "away_fg": q["away_fg"] * L.multiplier(fa, m, "fg")}
                v3p = P.Projection(P.points_pmf(q3["home_td"], q3["home_fg"], rt.p_xp, rt.p_2),
                                   P.points_pmf(q3["away_td"], q3["away_fg"], rt.p_xp, rt.p_2)).p_home_cover(line)
        pick_of = lambda p: None if p is None else (home if p > 0.5 else away)
        v1 = pick_of(v1p)
        hy, _ = hybrid.pick(live, d["drift"], v1)
        res = grade_league(g["home_score"], g["away_score"], line)
        cov = home if res is Result.HOME_COVER else away
        rows.append({"game_id": g["game_id"], "week": g["week"], "line": line, "line_source": source, "market": mkt,
                     "drift": d["drift"], "covered": cov, "official": live, "keynum": pick_of(kp), "v1": v1,
                     "v3": pick_of(v3p), "hybrid": hy})
    return rows


MODELS = ("official", "keynum", "v1", "v3", "hybrid")


def summary(rows: list[dict]) -> dict:
    out = {}
    for m in MODELS:
        for wk in (*WEEKS, "all"):
            rs = [r for r in rows if r[m] and (wk == "all" or r["week"] == wk)]
            w = sum(r[m] == r["covered"] for r in rs)
            out.setdefault(m, {})[wk] = (w, len(rs) - w)
    return out
