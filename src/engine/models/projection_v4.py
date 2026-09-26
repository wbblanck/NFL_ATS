"""Projection v4 (docs/projection_v4_preregistration.md).

Fixes to v1/v3:
  1. TDs counted from play-by-play (touchdown == 1 credited to td_team), not nflverse team_stats.
  2. Neutral sites: home indicator 0 for both teams.
  3. Score distribution from a drive model: the game's drive counts (N_h, N_a) follow their empirical joint
     distribution (training seasons); each drive ends TD (p_td), FG (p_fg) or nothing, with
     p = expected count / E[N]. Expected TDs/FGs are unchanged; the shape changes (binomial TDs,
     TD/FG trade-off within a team, positive cross-team dependence through shared drive counts).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from engine.models.projection import FRANCHISE, MAXP
from engine.picks.grading import validate_league_line

VERSION = "proj-drives-v4"


def team_games(team_stats: pl.DataFrame, sched: pl.DataFrame, td_pbp: pl.DataFrame,
               neutral_fix: bool = True) -> pl.DataFrame:
    """As projection.team_games, with TDs from play-by-play and (optionally) home = 0 at neutral sites."""
    ts = team_stats.filter(pl.col("season_type") == "REG").with_columns(
        [pl.col(c).fill_null(0) for c in ("fg_made", "pat_made", "def_safeties")]) \
        .with_columns(pl.col("team").replace(FRANCHISE)) \
        .select("season", "week", "team", pl.col("fg_made").alias("fg"), pl.col("pat_made").alias("pat"),
                pl.col("def_safeties").alias("saf"))
    reg = sched.filter(pl.col("game_type") == "REG", pl.col("home_score").is_not_null()).with_columns(
        pl.col("home_team").replace(FRANCHISE), pl.col("away_team").replace(FRANCHISE))
    neutral = (pl.col("location") == "Neutral") if neutral_fix else pl.lit(False)
    h = reg.select("game_id", "season", "week", "gameday", pl.col("home_team").alias("team"),
                   pl.col("away_team").alias("opp"), pl.when(neutral).then(0).otherwise(1).alias("home"),
                   pl.col("home_score").alias("pts"))
    a = reg.select("game_id", "season", "week", "gameday", pl.col("away_team").alias("team"),
                   pl.col("home_team").alias("opp"), pl.lit(0).alias("home"), pl.col("away_score").alias("pts"))
    td = td_pbp.select("game_id", pl.col("td_team").replace(FRANCHISE).alias("team"), pl.col("td_pbp").cast(pl.Int64)) \
        .group_by("game_id", "team").agg(pl.col("td_pbp").sum().alias("td"))
    g = pl.concat([h, a]).join(ts, on=["season", "week", "team"], how="inner") \
        .join(td, on=["game_id", "team"], how="left").with_columns(pl.col("td").fill_null(0))
    return g.with_columns((pl.col("season") * 25 + pl.col("week")).alias("t"))


def drive_table(drives: pl.DataFrame, sched: pl.DataFrame) -> pl.DataFrame:
    """Per REG game: home and away drive counts (distinct fixed_drive per possession team)."""
    s = sched.filter(pl.col("game_type") == "REG").select(
        "game_id", "season", pl.col("home_team").replace(FRANCHISE).alias("h"), pl.col("away_team").replace(FRANCHISE).alias("a"))
    d = drives.with_columns(pl.col("posteam").replace(FRANCHISE))
    return s.join(d.select("game_id", pl.col("posteam").alias("h"), pl.col("drives").alias("n_h")), on=["game_id", "h"]) \
        .join(d.select("game_id", pl.col("posteam").alias("a"), pl.col("drives").alias("n_a")), on=["game_id", "a"]) \
        .select("game_id", "season", "n_h", "n_a")


@dataclass
class DriveDist:
    """Empirical joint distribution of (home drives, away drives)."""
    pairs: np.ndarray        # shape (K, 2) int
    probs: np.ndarray        # shape (K,)

    @classmethod
    def fit(cls, table: pl.DataFrame) -> "DriveDist":
        c = table.group_by("n_h", "n_a").len().sort("n_h", "n_a")
        p = c["len"].to_numpy().astype(float)
        return cls(np.column_stack([c["n_h"].to_numpy(), c["n_a"].to_numpy()]).astype(int), p / p.sum())

    @property
    def mean(self) -> tuple[float, float]:
        return float(self.probs @ self.pairs[:, 0]), float(self.probs @ self.pairs[:, 1])

    def to_json(self) -> dict:
        return {"pairs": self.pairs.tolist(), "probs": self.probs.tolist()}

    @classmethod
    def from_json(cls, j: dict) -> "DriveDist":
        return cls(np.array(j["pairs"], int), np.array(j["probs"], float))


def _drive_pmf(p_td: float, p_fg: float, p_xp: float, p_2: float) -> np.ndarray:
    """Points from one drive: 0, 3, 6, 7, 8."""
    p_td, p_fg = max(p_td, 0.0), max(p_fg, 0.0)
    s = p_td + p_fg
    if s > 0.999:                               # keep a valid distribution (never binding in practice)
        p_td, p_fg = p_td * 0.999 / s, p_fg * 0.999 / s
    out = np.zeros(9)
    out[0] = 1 - p_td - p_fg
    out[3] = p_fg
    out[6], out[7], out[8] = p_td * (1 - p_xp - p_2), p_td * p_xp, p_td * p_2
    return out


def _powers(pmf: np.ndarray, nmax: int) -> list[np.ndarray]:
    """pmf convolved with itself n times, n = 0..nmax, truncated at MAXP points (mass beyond is renormalised)."""
    out = [np.r_[1.0, np.zeros(MAXP)]]
    cur = out[0]
    for _ in range(nmax):
        cur = np.convolve(cur, pmf)[:MAXP + 1]
        out.append(cur / cur.sum())
    return out


@dataclass
class DriveProjection:
    home_pts: np.ndarray
    away_pts: np.ndarray
    margin: np.ndarray       # index i -> margin i - MAXP

    @property
    def margin_pmf(self):
        return self.margin

    def mean_scores(self):
        x = np.arange(MAXP + 1)
        return float(self.home_pts @ x), float(self.away_pts @ x)

    def model_line(self):
        h, a = self.mean_scores()
        return -(h - a)

    def p_home_cover(self, league_line: float) -> float:
        s = validate_league_line(league_line)
        mg = np.arange(-MAXP, MAXP + 1)
        return float(self.margin[mg > -s].sum())

    def median_margin(self):
        mg = np.arange(-MAXP, MAXP + 1)
        return float(mg[np.searchsorted(np.cumsum(self.margin), 0.5)])


def project(mu_h: dict, mu_a: dict, p_xp: float, p_2: float, dd: DriveDist) -> DriveProjection:
    """mu_*: {"td": expected TDs, "fg": expected FGs} for home and away."""
    eh, ea = dd.mean
    nmax = int(dd.pairs.max())
    ph = _powers(_drive_pmf(mu_h["td"] / eh, mu_h["fg"] / eh, p_xp, p_2), nmax)
    pa = _powers(_drive_pmf(mu_a["td"] / ea, mu_a["fg"] / ea, p_xp, p_2), nmax)
    margin = np.zeros(2 * MAXP + 1)
    home = np.zeros(MAXP + 1)
    away = np.zeros(MAXP + 1)
    for (nh, na), w in zip(dd.pairs, dd.probs):
        margin += w * np.convolve(ph[nh], pa[na][::-1])
        home += w * ph[nh]
        away += w * pa[na]
    return DriveProjection(home / home.sum(), away / away.sum(), margin / margin.sum())
