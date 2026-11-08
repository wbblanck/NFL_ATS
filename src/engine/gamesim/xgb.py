"""XGBoost margin model (nfl-betting-model docs/batch4_preregistration.md): pregame features and the fixed training setup."""
from __future__ import annotations

import numpy as np
import polars as pl
import xgboost as xgb

from .elo import FRANCHISE

PARAMS = {"objective": "reg:squarederror", "max_depth": 3, "eta": 0.03, "subsample": 0.8,
          "colsample_bytree": 0.8, "min_child_weight": 20, "lambda": 1.0, "seed": 0, "nthread": 1}
TREES = list(range(100, 1001, 100))
FEATURES = ["elo_d", "elo_fair", "qb_h", "qb_a", "kalman", "kalman_var", "off8_h", "def8_h", "off8_a", "def8_a",
            "level", "home_rest", "away_rest", "neutral", "div_game", "dome", "week"]
WINDOW = 8


def rolling_epa(pbp: pl.DataFrame) -> pl.DataFrame:
    """Per (game_id, team): offensive and defensive EPA per play over the team's previous WINDOW regular-season games
    (across seasons), from plays before this game only."""
    p = pbp.filter(pl.col("season_type") == "REG", pl.col("epa").is_not_null(), pl.col("play_type").is_in(["pass", "run"])) \
        .with_columns(pl.col("posteam").replace(FRANCHISE), pl.col("defteam").replace(FRANCHISE))
    off = p.group_by("game_id", "game_date", "posteam").agg(pl.col("epa").sum().alias("s"), pl.len().alias("n")) \
        .rename({"posteam": "team"})
    de = p.group_by("game_id", "game_date", "defteam").agg(pl.col("epa").sum().alias("s"), pl.len().alias("n")) \
        .rename({"defteam": "team"})
    out = None
    for name, g in (("off8", off), ("def8", de)):
        g = g.sort("team", "game_date", "game_id")
        g = g.with_columns(
            (pl.col("s").shift(1).rolling_sum(WINDOW, min_samples=1).over("team")
             / pl.col("n").shift(1).rolling_sum(WINDOW, min_samples=1).over("team")).alias(name))
        g = g.select("game_id", "team", name)
        out = g if out is None else out.join(g, on=["game_id", "team"], how="full", coalesce=True)
    return out


class model:
    """Thin wrapper over xgboost's native API (no scikit-learn needed): model(n).fit(X, y).predict(X)."""

    def __init__(self, n_trees: int):
        self.n = n_trees
        self.booster = None

    def fit(self, X, y):
        self.booster = xgb.train(PARAMS, xgb.DMatrix(np.asarray(X, float), label=np.asarray(y, float)), self.n)
        return self

    def predict(self, X):
        return self.booster.predict(xgb.DMatrix(np.asarray(X, float)))


def choose_trees(X: np.ndarray, y: np.ndarray, season: np.ndarray) -> tuple[int, dict]:
    """Leave-one-season-out MAE for each tree count in TREES; returns the best count and the table."""
    tab = {}
    for n in TREES:
        errs = []
        for s in np.unique(season):
            tr, te = season != s, season == s
            errs.append(np.abs(model(n).fit(X[tr], y[tr]).predict(X[te]) - y[te]))
        tab[n] = float(np.concatenate(errs).mean())
    return min(tab, key=tab.get), tab
