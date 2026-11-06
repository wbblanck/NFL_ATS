"""Elo rating + Poisson / negative binomial score model (nfl-betting-model docs/elo_preregistration.md).

One rating per franchise. A logistic curve turns the rating gap into a win probability; the gap also sets each
team's expected points, and Poisson or negative binomial distributions turn those into score, margin and cover
probabilities. Ratings update after every game (FiveThirtyEight form) and regress toward 1505 between seasons.
Every forecast uses only games before it.
"""
from __future__ import annotations

import math

import numpy as np
import polars as pl
from math import lgamma

FRANCHISE = {"STL": "LA", "SD": "LAC", "OAK": "LV", "JAC": "JAX", "LAR": "LA"}
START, MEAN = 1500.0, 1505.0
PRIOR_N = 128.0           # team-games of weight on last season's scoring level
MAXPTS = 100


def win_prob(d):
    return 1.0 / (1.0 + 10.0 ** (-np.asarray(d, float) / 400.0))


def mov_mult(margin: float, d_winner: float) -> float:
    if margin == 0:
        return 1.0
    return math.log(abs(margin) + 1.0) * 2.2 / (0.001 * d_winner + 2.2)


def update(rh: float, ra: float, margin: float, k: float, h: float) -> float:
    """Rating points the home team gains (away loses the same). h is the home-field term already applied."""
    d = rh - ra + h
    p = float(win_prob(d))
    s = 1.0 if margin > 0 else 0.5 if margin == 0 else 0.0
    dw = d if margin > 0 else -d
    return k * mov_mult(margin, dw) * (s - p)


def prep(sched: pl.DataFrame) -> pl.DataFrame:
    """Regular-season and playoff games with a result, franchise-mapped, in date order."""
    return sched.filter(pl.col("result").is_not_null()).with_columns(
        pl.col("home_team").replace(FRANCHISE), pl.col("away_team").replace(FRANCHISE),
        (pl.col("location") == "Neutral").alias("neutral")).sort("season", "gameday", "game_id")


def run(games: pl.DataFrame, k: float, h: float, c: float, qb: dict | None = None, q: float = 0.0) -> pl.DataFrame:
    """Pre-game ratings for every game in `games` (output of prep). Games are processed week by week within a
    season: all of a week's forecasts use ratings from before that week. qb: {(game_id, team): qb_delta}.
    Returns one row per game with r_home, r_away, d (gap incl. home field and QB term), p (logistic win prob)."""
    R: dict[str, float] = {}
    rows = []
    for season in sorted(games["season"].unique().to_list()):
        for t in list(R):
            R[t] += c * (MEAN - R[t])
        s = games.filter(pl.col("season") == season)
        for week in sorted(s["week"].unique().to_list()):
            g = s.filter(pl.col("week") == week)
            upd = []
            for r in g.iter_rows(named=True):
                ht, at = r["home_team"], r["away_team"]
                rh, ra = R.get(ht, START), R.get(at, START)
                hh = 0.0 if r["neutral"] else h
                qq = 0.0
                if qb is not None and q:
                    qq = q * (qb.get((r["game_id"], ht), 0.0) - qb.get((r["game_id"], at), 0.0))
                d = rh - ra + hh + qq
                rows.append({"game_id": r["game_id"], "season": season, "week": week, "home_team": ht, "away_team": at,
                             "r_home": rh, "r_away": ra, "d": d, "p": float(win_prob(d))})
                upd.append((ht, at, rh, ra, r["result"], hh + qq))
            for ht, at, rh, ra, m, hh in upd:
                x = update(rh, ra, m, k, hh)
                R[ht] = rh + x
                R[at] = ra - x
    out = pl.DataFrame(rows)
    out.final = dict(R)  # type: ignore[attr-defined]
    return out


def final_ratings(games: pl.DataFrame, k: float, h: float, c: float) -> dict:
    """Ratings after the last game in `games` (no end-of-season regression applied)."""
    return run(games, k, h, c).final  # type: ignore[attr-defined]


def scoring_level(games: pl.DataFrame) -> pl.DataFrame:
    """Per game: league points per team-game known before the game's week (prev season blended with season to date)."""
    reg = games.filter(pl.col("game_type") == "REG") if "game_type" in games.columns else games
    rows = []
    for season in sorted(games["season"].unique().to_list()):
        prev = reg.filter(pl.col("season") == season - 1)
        pm = float(((prev["home_score"] + prev["away_score"]) / 2).mean()) if prev.height else 21.0
        cur = games.filter(pl.col("season") == season)
        for week in sorted(cur["week"].unique().to_list()):
            done = reg.filter(pl.col("season") == season, pl.col("week") < week)
            tot, n = float((done["home_score"] + done["away_score"]).sum()), 2 * done.height
            lvl = (PRIOR_N * pm + tot) / (PRIOR_N + n)
            for gid in cur.filter(pl.col("week") == week)["game_id"].to_list():
                rows.append({"game_id": gid, "level": lvl})
    return pl.DataFrame(rows)


def means(d, level, b):
    a = np.log(np.asarray(level, float))
    x = b * np.asarray(d, float) / 100.0
    return np.exp(a + x), np.exp(a - x)


# ---------- count distributions
def pois_pmf(mu):
    k = np.arange(MAXPTS + 1)
    mu = np.asarray(mu, float)[:, None]
    lg = np.array([lgamma(i + 1) for i in k])
    return np.exp(k * np.log(mu) - mu - lg)


def nb_pmf(mu, theta):
    k = np.arange(MAXPTS + 1)
    mu = np.asarray(mu, float)[:, None]
    lc = np.array([lgamma(i + theta) - lgamma(theta) - lgamma(i + 1) for i in k])
    return np.exp(lc + theta * np.log(theta / (theta + mu)) + k * np.log(mu / (theta + mu)))


def margin_dist(ph, pa):
    """Rows: games. Returns (margins array -MAXPTS..MAXPTS, probs (G, 2*MAXPTS+1)) of home − away."""
    G = ph.shape[0]
    out = np.zeros((G, 2 * MAXPTS + 1))
    for i in range(G):
        out[i] = np.convolve(ph[i], pa[i][::-1])
    return np.arange(-MAXPTS, MAXPTS + 1), out


def probs(ph, pa, line):
    """P(home win incl. half of ties), P(home covers line | no push)."""
    m, pm = margin_dist(ph, pa)
    line = np.asarray(line, float)[:, None]
    win = (pm * (m > 0)).sum(1) + 0.5 * (pm * (m == 0)).sum(1)
    over = (pm * (m > line)).sum(1)
    push = (pm * (m == line)).sum(1)
    return win, over / (1.0 - push)


def nll_pois(y, mu):
    return float(-(y * np.log(mu) - mu - np.array([lgamma(v + 1) for v in y])).sum())


def nll_nb(y, mu, th):
    return float(-np.sum([lgamma(v + th) - lgamma(th) - lgamma(v + 1) for v in y]
                         + th * np.log(th / (th + mu)) + y * np.log(mu / (th + mu))))


def fit_b(d, level, hs, as_):
    """Poisson ML for b (golden-section on [0, 2])."""
    y = np.r_[hs, as_].astype(float)

    def f(b):
        mh, ma = means(d, level, b)
        return nll_pois(y, np.r_[mh, ma])
    return _golden(f, 0.0, 2.0)


def fit_theta(d, level, hs, as_, b):
    y = np.r_[hs, as_].astype(float)
    mh, ma = means(d, level, b)
    mu = np.r_[mh, ma]
    lt = _golden(lambda t: nll_nb(y, mu, math.exp(t)), math.log(0.5), math.log(500.0))
    return math.exp(lt)


def _golden(f, lo, hi, tol=1e-5):
    g = (math.sqrt(5) - 1) / 2
    a, b = lo, hi
    c, d = b - g * (b - a), a + g * (b - a)
    fc, fd = f(c), f(d)
    while b - a > tol:
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - g * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + g * (b - a)
            fd = f(d)
    return (a + b) / 2


def logloss(p, y):
    p = np.clip(np.asarray(p, float), 1e-9, 1 - 1e-9)
    y = np.asarray(y, float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))
