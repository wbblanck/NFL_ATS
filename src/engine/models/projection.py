"""Score-projection model proj-poisson-v1 (docs/projection_preregistration.md).

Team strength: two time-decayed, ridge-penalized Poisson regressions (TDs and FGs),
each with home effect and team attack/defense terms. Scores: TD ~ Poisson, FG ~ Poisson,
per-TD extra points {0,1,2}; the margin distribution is computed exactly by convolution.
All fits use only games that kicked off before the game being projected.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from engine.picks.grading import validate_league_line

FRANCHISE = {"OAK": "LV", "SD": "LAC", "STL": "LA", "LAR": "LA", "JAC": "JAX"}
MAXP = 90


def _poisson_pmf(k: np.ndarray, lam: float) -> np.ndarray:
    from math import lgamma
    return np.exp(k * np.log(max(lam, 1e-12)) - lam - np.array([lgamma(x + 1) for x in k]))


def team_games(team_stats: pl.DataFrame, sched: pl.DataFrame) -> pl.DataFrame:
    """One row per team-game: season, week, gameday, team, opp, home, td, fg, pts."""
    ts = team_stats.filter(pl.col("season_type") == "REG").with_columns(
        [pl.col(c).fill_null(0) for c in ("passing_tds", "rushing_tds", "special_teams_tds", "def_tds",
                                          "fg_made", "pat_made", "def_safeties")])
    ts = ts.with_columns(pl.col("team").replace(FRANCHISE)).select("season", "week", "team",
                   (pl.col("passing_tds") + pl.col("rushing_tds") + pl.col("special_teams_tds")
                    + pl.col("def_tds")).alias("td"), pl.col("fg_made").alias("fg"),
                   pl.col("pat_made").alias("pat"), pl.col("def_safeties").alias("saf"))
    reg = sched.filter(pl.col("game_type") == "REG", pl.col("home_score").is_not_null()).with_columns(
        pl.col("home_team").replace(FRANCHISE), pl.col("away_team").replace(FRANCHISE))
    h = reg.select("game_id", "season", "week", "gameday", pl.col("home_team").alias("team"),
                   pl.col("away_team").alias("opp"), pl.lit(1).alias("home"), pl.col("home_score").alias("pts"))
    a = reg.select("game_id", "season", "week", "gameday", pl.col("away_team").alias("team"),
                   pl.col("home_team").alias("opp"), pl.lit(0).alias("home"), pl.col("away_score").alias("pts"))
    g = pl.concat([h, a]).join(ts, on=["season", "week", "team"], how="inner")
    return g.with_columns((pl.col("season") * 25 + pl.col("week")).alias("t"))


def _poisson_ridge(X, y, w, lam, pen_mask, b0=None, iters=25):
    b = np.zeros(X.shape[1]) if b0 is None else b0.copy()
    if b0 is None:
        b[0] = np.log(max(np.average(y, weights=w), 1e-3))
    P = lam * np.diag(pen_mask.astype(float))
    for _ in range(iters):
        mu = np.exp(np.clip(X @ b, -10, 5))
        grad = X.T @ (w * (y - mu)) - P @ b
        H = X.T @ (X * (w * mu)[:, None]) + P
        step = np.linalg.solve(H, grad)
        b += step
        if np.max(np.abs(step)) < 1e-8:
            break
    return b


@dataclass
class Ratings:
    teams: list
    td: np.ndarray
    fg: np.ndarray
    p_xp: float
    p_2: float

    def _lam(self, b, team, opp, home):
        i, j, n = self.teams.index(team), self.teams.index(opp), len(self.teams)
        return float(np.exp(b[0] + b[1] * home + b[2 + i] - b[2 + n + j]))

    def rates(self, home_team, away_team):
        return {"home_td": self._lam(self.td, home_team, away_team, 1), "home_fg": self._lam(self.fg, home_team, away_team, 1),
                "away_td": self._lam(self.td, away_team, home_team, 0), "away_fg": self._lam(self.fg, away_team, home_team, 0)}


def fit(games: pl.DataFrame, t_now: int, season_now: int, half_life: float, lam: float) -> Ratings:
    g = games.filter(pl.col("t") < t_now)
    w = (0.5 ** ((t_now - g["t"].to_numpy()) / half_life)) * (0.5 ** (season_now - g["season"].to_numpy()))
    keep = w > 1e-3
    g, w = g.filter(pl.Series(keep)), w[keep]
    teams = sorted(set(g["team"].to_list()) | set(g["opp"].to_list()))
    n = len(teams)
    idx = {t: k for k, t in enumerate(teams)}
    X = np.zeros((g.height, 2 + 2 * n))
    X[:, 0] = 1
    X[:, 1] = g["home"].to_numpy()
    r = np.arange(g.height)
    X[r, 2 + np.array([idx[t] for t in g["team"].to_list()])] = 1
    X[r, 2 + n + np.array([idx[t] for t in g["opp"].to_list()])] = -1
    pen = np.r_[False, False, np.ones(2 * n, bool)]
    btd = _poisson_ridge(X, g["td"].to_numpy().astype(float), w, lam, pen)
    bfg = _poisson_ridge(X, g["fg"].to_numpy().astype(float), w, lam, pen)
    td_sum = float(np.sum(w * g["td"].to_numpy()))
    p_xp = float(np.sum(w * g["pat"].to_numpy()) / max(td_sum, 1e-9))
    extra = g["pts"].to_numpy() - 6 * g["td"].to_numpy() - g["pat"].to_numpy() - 3 * g["fg"].to_numpy() - 2 * g["saf"].to_numpy()
    p_2 = float(np.clip(np.sum(w * np.clip(extra, 0, 2)) / 2 / max(td_sum, 1e-9), 0, 0.15))
    p_xp = min(p_xp, 1 - p_2)
    return Ratings(teams, btd, bfg, p_xp, p_2)


def points_pmf(lam_td: float, lam_fg: float, p_xp: float, p_2: float) -> np.ndarray:
    """Exact pmf of a team's points on 0..MAXP."""
    kmax, fmax = 12, 10
    per_td = np.array([1 - p_xp - p_2, p_xp, p_2])     # extra points after one TD: 0,1,2
    out = np.zeros(MAXP + 1)
    extra = np.array([1.0])
    ptd, pfg = _poisson_pmf(np.arange(kmax + 1), lam_td), _poisson_pmf(np.arange(fmax + 1), lam_fg)
    for k in range(kmax + 1):
        if k > 0:
            extra = np.convolve(extra, per_td)
        for f in range(fmax + 1):
            base = 6 * k + 3 * f
            for e, pe in enumerate(extra):
                if base + e <= MAXP:
                    out[base + e] += ptd[k] * pfg[f] * pe
    return out / out.sum()


class PmfProjection:
    """Read-outs shared by the projections. Subclasses provide margin_pmf (index i -> margin i - MAXP)
    and home_pts / away_pts point pmfs (0..MAXP), or override mean_scores."""

    def mean_scores(self):
        x = np.arange(MAXP + 1)
        return float(self.home_pts @ x), float(self.away_pts @ x)

    def model_line(self):
        h, a = self.mean_scores()
        return -(h - a)                                # canonical home spread

    def p_home_cover(self, league_line: float) -> float:
        s = validate_league_line(league_line)
        mg = np.arange(-MAXP, MAXP + 1)
        return float(self.margin_pmf[mg > -s].sum())

    def median_margin(self):
        mg = np.arange(-MAXP, MAXP + 1)
        c = np.cumsum(self.margin_pmf)
        return float(mg[np.searchsorted(c, 0.5)])


@dataclass
class Projection(PmfProjection):
    home_pts: np.ndarray
    away_pts: np.ndarray

    @property
    def margin_pmf(self):
        m = np.convolve(self.home_pts, self.away_pts[::-1])   # index i -> margin i - MAXP
        return m / m.sum()


def project(r: Ratings, home_team: str, away_team: str) -> Projection:
    home_team, away_team = FRANCHISE.get(home_team, home_team), FRANCHISE.get(away_team, away_team)
    q = r.rates(home_team, away_team)
    return Projection(points_pmf(q["home_td"], q["home_fg"], r.p_xp, r.p_2),
                      points_pmf(q["away_td"], q["away_fg"], r.p_xp, r.p_2))
