"""Phase 7: full-system walk-forward (docs/phase7_preregistration.md)."""
from __future__ import annotations

import datetime as dt
import math

import numpy as np
import polars as pl

from engine import config
from engine.backtest import calibration as C
from engine.backtest.common import md_table as _tbl
from engine.data import nflverse, sbro
from engine.models.margin_dist import MarginDist

BAR, BAR_SE = 0.5137, 0.0082


def load() -> pl.DataFrame:
    sched, _ = nflverse.pull("schedules", save=False)
    reg = sched.filter(pl.col("game_type").is_in(list(config.league().game_types)),
                       pl.col("result").is_not_null(), pl.col("spread_line").is_not_null())
    base = reg.select("game_id", "season", "week", pl.col("result").alias("margin"),
                      (-pl.col("spread_line")).alias("close"))
    sb = sbro.match_schedule(sbro.load_all(config.ROOT / "data" / "raw" / "sbro"), sched) \
        .select("game_id", pl.col("open_home_spread").alias("open"))
    return base.join(sb, on="game_id", how="left")


def predict(df: pl.DataFrame, first=2007, last=2021) -> tuple[pl.DataFrame, dict]:
    """Walk-forward predictions for every test game (pushes kept, flagged). Deterministic."""
    out, counts = [], {"missing_open": 0}
    for s in range(first, last + 1):
        tr = df.filter(pl.col("season") < s)
        te = df.filter(pl.col("season") == s)
        counts["missing_open"] += te.filter(pl.col("open").is_null()).height
        te = te.filter(pl.col("open").is_not_null())
        md = MarginDist("shifted").fit(tr["close"].to_numpy(), tr["margin"].to_numpy())
        p = md.sf(-te["open"].to_numpy(), te["close"].to_numpy())
        med = np.array([md.median_margin(c) for c in te["close"].to_numpy()])
        out.append(te.with_columns(pl.Series("p_home", p), pl.Series("median_margin", med)))
    d = pl.concat(out).with_columns(
        (-pl.col("close")).alias("exp_margin"),
        (pl.col("close") - pl.col("open")).alias("drift"),
        pl.when(pl.col("margin") > -pl.col("open")).then(pl.lit("home"))
        .when(pl.col("margin") < -pl.col("open")).then(pl.lit("away")).otherwise(pl.lit("push")).alias("result"),
        pl.when(pl.col("p_home") > 0.5).then(pl.lit("home")).otherwise(pl.lit("away")).alias("pick"),
    ).with_columns(
        pl.when(pl.col("result") == "push").then(pl.lit("P"))
        .when(pl.col("result") == pl.col("pick")).then(pl.lit("W")).otherwise(pl.lit("L")).alias("o"))
    return d, counts


def metrics(x: pl.DataFrame) -> dict:
    w, l, p = (int((x["o"] == k).sum()) for k in ("W", "L", "P"))
    n = w + l
    r = w / n if n else float("nan")
    dec = x.filter(pl.col("o") != "P")
    y = (dec["result"] == "home").cast(pl.Float64).to_numpy()
    ph = dec["p_home"].to_numpy()
    err = x["margin"].to_numpy() - x["exp_margin"].to_numpy()
    errm = x["margin"].to_numpy() - x["median_margin"].to_numpy()
    return {"W": w, "L": l, "P": p, "N": n, "win_rate": r, "se": math.sqrt(r * (1 - r) / n) if n else float("nan"),
            "mae_exp": float(np.mean(np.abs(err))), "rmse_exp": float(np.sqrt(np.mean(err ** 2))),
            "mae_median": float(np.mean(np.abs(errm))),
            "log_loss": C.log_loss(ph, y) if n else float("nan"), "brier": C.brier(ph, y) if n else float("nan"),
            "ece": C.ece(ph, y) if n else float("nan")}


SUBGROUPS = {
    "spread abs(S)<=3": pl.col("open").abs() <= 3,
    "spread abs(S) 3.5-7": pl.col("open").abs().is_between(3.5, 7),
    "spread abs(S)>7": pl.col("open").abs() > 7,
    "pick home": pl.col("pick") == "home",
    "pick away": pl.col("pick") == "away",
    "pick favorite": ((pl.col("pick") == "home") & (pl.col("open") < 0)) | ((pl.col("pick") == "away") & (pl.col("open") > 0)),
    "pick underdog": ((pl.col("pick") == "home") & (pl.col("open") > 0)) | ((pl.col("pick") == "away") & (pl.col("open") < 0)),
    "weeks 1-6": pl.col("week") <= 6,
    "weeks 7-12": pl.col("week").is_between(7, 12),
    "weeks 13+": pl.col("week") >= 13,
    "drift 0": pl.col("drift") == 0,
    "drift 0.5": pl.col("drift").abs() == 0.5,
    "drift >=1": pl.col("drift").abs() >= 1,
}


def run(out_md=None) -> dict:
    d, counts = predict(load())
    pooled = metrics(d)
    z_bar = (pooled["win_rate"] - BAR) / math.sqrt(pooled["se"] ** 2 + BAR_SE ** 2)
    per = pl.DataFrame([{"season": s, **metrics(d.filter(pl.col("season") == s))}
                        for s in sorted(d["season"].unique().to_list())])
    sub = pl.DataFrame([{"subgroup": k, **metrics(d.filter(v))} for k, v in SUBGROUPS.items()])
    res = {"pooled": pooled, "z_vs_bar": z_bar, "passed": z_bar >= 1.96, "per_season": per,
           "subgroups": sub, "counts": counts}
    bt = config.path("backtests")
    d.write_csv(bt / "phase7_predictions.csv")
    per.write_csv(bt / "phase7_by_season.csv")
    sub.write_csv(bt / "phase7_subgroups.csv")
    if out_md:
        out_md.write_text(_md(res))
    return res


def _md(r):
    p = r["pooled"]
    return "\n".join([
        "# Phase 7 — Full-system walk-forward results\n",
        f"Generated {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} by `python -m engine backtest`. "
        "Pre-registration: `docs/phase7_preregistration.md`. System `phase4-shifted-empirical-argmax`; test seasons "
        "2007–2021; frozen line = SBRO open, market = nflverse close (proxies).\n",
        f"Excluded (no usable open): {r['counts']['missing_open']}.\n",
        "## Pooled\n", _tbl(pl.DataFrame([p])),
        f"\nz vs best Phase 2 baseline (0.5137, SE 0.0082) = {r['z_vs_bar']:.2f}. "
        f"**Kill criterion: {'PASS' if r['passed'] else 'FAIL'}.**\n",
        "## Per season (every season reported)\n", _tbl(r["per_season"]),
        "\n## Diagnostic subgroups (diagnostics only — never used to filter picks)\n", _tbl(r["subgroups"]),
    ])
