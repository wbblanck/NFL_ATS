"""FTN shadow model: primary test (docs/ftn_shadow_preregistration.md, with Amendment 1). Run once.

Walk-forward by season over 2023-2025. Each test season is fit on every earlier season from 2022. The shadow model is
an L2 logistic regression (engine.models.adaptive.fit_logit, lam = 1.0) on four prior-only, shrunk team features
(home minus away) plus the closing home spread. The baseline is the intercept-only model. The primary statistic is
the paired log-loss difference, bootstrapped by week. The shadow passes only if the 95% upper bound is below 0.

Usage (from the repo root): PYTHONPATH=src python3 scripts/ftn/primary_test.py
"""
import json
from pathlib import Path

import numpy as np
import nflreadpy as nfl
import polars as pl

from engine.models.adaptive import fit_logit

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "evidence" / "ftn" / "primary_test.json"
K = 8                      # shrinkage, team-games (registered)
LAM = 1.0                  # L2 penalty (registered)
SEED = 20261010            # bootstrap seed, fixed before the run
DRAWS = 10_000             # bootstrap draws (registered)
SEASONS = [2022, 2023, 2024, 2025]
TEST = [2023, 2024, 2025]
FEATS = ["blitz", "pa", "screen", "motion"]
BREAK_EVEN = 110 / 210


def as_pl(x):
    return x if isinstance(x, pl.DataFrame) else pl.from_pandas(x)


def wilson(w, n, z=1.96):
    p = w / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


# ---- data (regular season only) ----
sched = (as_pl(nfl.load_schedules(SEASONS))
         .filter((pl.col("game_type") == "REG") & pl.col("result").is_not_null() & pl.col("spread_line").is_not_null())
         .select("game_id", "season", "week", "home_team", "away_team", "result", "spread_line"))
ftn = as_pl(nfl.load_ftn_charting(SEASONS)).select(
    pl.col("nflverse_game_id").alias("game_id"), pl.col("nflverse_play_id").cast(pl.Int64).alias("play_id"),
    "n_pass_rushers", "is_play_action", "is_screen_pass", "is_motion")
pbp = as_pl(nfl.load_pbp(SEASONS)).select(
    "game_id", pl.col("play_id").cast(pl.Int64), "posteam", "defteam", "play_type", "qb_dropback")
plays = ftn.join(pbp, on=["game_id", "play_id"], how="inner")

# ---- team-game rates, per Amendment 1 ----
dropbacks = plays.filter(pl.col("qb_dropback") == 1)
off_db = (dropbacks.filter(pl.col("posteam").is_not_null())
          .group_by("game_id", "posteam")
          .agg(pl.col("is_play_action").mean().alias("pa"), pl.col("is_screen_pass").mean().alias("screen"))
          .rename({"posteam": "team"}))
off_motion = (plays.filter(pl.col("posteam").is_not_null() & pl.col("play_type").is_in(["run", "pass"]))
              .group_by("game_id", "posteam").agg(pl.col("is_motion").mean().alias("motion"))
              .rename({"posteam": "team"}))
def_blitz = (dropbacks.filter(pl.col("defteam").is_not_null() & pl.col("n_pass_rushers").is_between(1, 11))
             .group_by("game_id", "defteam").agg((pl.col("n_pass_rushers") >= 5).mean().alias("blitz"))
             .rename({"defteam": "team"}))
tg = (off_db.join(off_motion, on=["game_id", "team"], how="full", coalesce=True)
      .join(def_blitz, on=["game_id", "team"], how="full", coalesce=True)
      .join(sched.select("game_id", "season", "week"), on="game_id", how="inner"))
print("team-games:", tg.height, "| with a missing feature:", tg.filter(pl.any_horizontal([pl.col(f).is_null() for f in FEATS])).height)

# ---- prior-only shrinkage toward the 2022 league mean (fixed) ----
base22 = tg.filter(pl.col("season") == SEASONS[0])
L = {f: float(base22[f].drop_nulls().mean()) for f in FEATS}
hist, shr = {}, {}
for r in tg.sort(["team", "season", "week"]).iter_rows(named=True):
    prior = hist.setdefault(r["team"], [])
    out = {}
    for f in FEATS:
        vals = [p[f] for p in prior if p[f] is not None]
        n = len(vals)
        out[f] = (n * (sum(vals) / n) + K * L[f]) / (n + K) if n else L[f]
    shr[(r["game_id"], r["team"])] = out
    prior.append(r)

# ---- one row per game: home-minus-away features, closing spread, outcome ----
rows, missing = [], 0
for g in sched.iter_rows(named=True):
    h = shr.get((g["game_id"], g["home_team"]))
    a = shr.get((g["game_id"], g["away_team"]))
    if h is None or a is None:
        missing += 1
        continue
    cover = g["result"] - g["spread_line"]          # > 0 home covers, == 0 push (spread_line > 0: home favored)
    if cover == 0:
        continue
    rows.append({"season": g["season"], "week": g["week"], "game_id": g["game_id"],
                 "y": 1.0 if cover > 0 else 0.0,
                 **{f"d_{f}": h[f] - a[f] for f in FEATS}, "spread": float(g["spread_line"])})
data = pl.DataFrame(rows)
print("games used (non-push, both teams charted):", data.height, "| games dropped for missing team features:", missing)

DCOLS = [f"d_{f}" for f in FEATS] + ["spread"]
out_rows, per_season = [], {}
for s in TEST:
    tr = data.filter(pl.col("season") < s)
    te = data.filter(pl.col("season") == s)
    Xtr = tr.select(DCOLS).to_numpy()
    mu, sd = Xtr.mean(0), Xtr.std(0)
    Xtr_s = np.column_stack([np.ones(len(tr)), (Xtr - mu) / sd])
    Xte_s = np.column_stack([np.ones(len(te)), (te.select(DCOLS).to_numpy() - mu) / sd])
    b = fit_logit(Xtr_s, tr["y"].to_numpy(), np.ones(len(tr)), LAM)
    p = 1 / (1 + np.exp(-(Xte_s @ b)))
    p0 = float(tr["y"].mean())
    y = te["y"].to_numpy()
    ll_m = -(y * np.log(p) + (1 - y) * np.log(1 - p))
    ll_b = -(y * np.log(p0) + (1 - y) * np.log(1 - p0))
    out_rows.append(te.select("season", "week", "y").with_columns(
        pl.Series("p_model", p), pl.Series("d", ll_m - ll_b)))
    per_season[s] = {"train_games": tr.height, "test_games": te.height,
                     "mean_d": float((ll_m - ll_b).mean()), "baseline_p": p0,
                     "coef": [round(float(c), 4) for c in b]}

res = pl.concat(out_rows)
d = res["d"].to_numpy()
cl = res.group_by("season", "week").agg(pl.col("d").sum().alias("sd"), pl.len().alias("n")).sort("season", "week")
sd_c, n_c = cl["sd"].to_numpy(), cl["n"].to_numpy().astype(float)
rng = np.random.default_rng(SEED)
idx = rng.integers(0, len(cl), size=(DRAWS, len(cl)))
boot = sd_c[idx].sum(1) / n_c[idx].sum(1)
lo, hi = np.percentile(boot, [2.5, 97.5])
mean_d = float(d.mean())
passed = bool(hi < 0)

# ---- secondary: the shadow side at the closing line, -110, descriptive only ----
side_home = res["p_model"].to_numpy() > 0.5
yy = res["y"].to_numpy()
win = np.where(side_home, yy == 1, yy == 0)
W, Lo = int(win.sum()), int((~win).sum())
rate = W / (W + Lo)
zlo, zhi = wilson(W, W + Lo)
ats = {"W": W, "L": Lo, "win_rate": rate, "ci95": [zlo, zhi],
       "z_vs_break_even": (rate - BREAK_EVEN) / np.sqrt(BREAK_EVEN * (1 - BREAK_EVEN) / (W + Lo)),
       "roi_at_-110": (W * 100 / 110 - Lo) / (W + Lo)}

summary = {"games": int(res.height), "L_2022": L, "lambda": LAM, "K": K, "seed": SEED, "draws": DRAWS,
           "mean_log_loss_diff_shadow_minus_baseline": mean_d,
           "bootstrap_95": [float(lo), float(hi)], "primary_pass": passed,
           "per_season": per_season, "ats_secondary": ats}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
