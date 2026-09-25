"""Phase 3 runner. Frozen line = SBRO open; market at lock = SBRO close (proxies).
Everything reported here follows docs/phase3_preregistration.md."""
from __future__ import annotations

import datetime as dt
import math

import polars as pl

from engine import config
from engine.data import nflverse, sbro
from engine.models import drift as D

BAR, BAR_SE = 0.5137, 0.0082   # Phase 2 always-away on SBRO open (docs/phase2_report.md)


def load(market_col: str = "close_home_spread") -> tuple[pl.DataFrame, dict]:
    sched, _ = nflverse.pull("schedules", save=False)
    m = sbro.match_schedule(sbro.load_all(config.ROOT / "data" / "raw" / "sbro"), sched)
    reg = m.filter(pl.col("game_type").is_in(list(config.league().game_types)))
    counts = {"reg_games": reg.height,
              "excluded_bad_open_or_close": reg.filter(pl.col("open_home_spread").is_null()
                                                       | pl.col(market_col).is_null()).height}
    df = reg.filter(pl.col("open_home_spread").is_not_null(), pl.col(market_col).is_not_null()) \
        .select("game_id", "season", "week",
                pl.col("open_home_spread").alias("home_spread"),
                pl.col(market_col).alias("market_spread"),
                (pl.col("home_score") - pl.col("away_score")).alias("margin"))
    return D.add_outcomes(df), counts


def _row(label, s):
    return {"label": label, **s}


def run(out_md=None) -> dict:
    df, counts = load()
    res = {"counts": counts}
    o = lambda expr: df.select(D.outcome(expr).alias("o"))["o"]  # noqa: E731

    d0 = D.summarize(o(D.strategy_picks(df)))
    full = D.summarize(o(D.strategy_picks(df, k=0.0, fallback_home=False)))
    z_bar = (d0["win_rate"] - BAR) / math.sqrt(d0["se"] ** 2 + BAR_SE ** 2)
    passed = d0["z_vs_50"] >= 1.96 and z_bar >= 1.96
    res.update(d0=d0, d0_full=full, z_vs_bar=z_bar, passed=passed)

    # per season
    seasons = sorted(df["season"].unique().to_list())
    per = []
    for s in seasons:
        x = df.filter(pl.col("season") == s)
        a = D.summarize(x.select(D.outcome(D.strategy_picks(x)).alias("o"))["o"])
        b = D.summarize(x.select(D.outcome(D.strategy_picks(x, 0.0, False)).alias("o"))["o"])
        per.append({"season": s, **{f"d0_{k}": v for k, v in a.items()}, "full_win_rate": b["win_rate"]})
    res["per_season"] = pl.DataFrame(per)

    # monotonicity buckets
    bk = []
    for name, lo, hi in D.BUCKETS:
        x = df.filter(pl.col("abs_drift").is_between(lo, hi))
        bk.append({"bucket": name, **D.summarize(x.select(D.outcome(D.strategy_picks(x)).alias("o"))["o"])})
    res["buckets"] = pl.DataFrame(bk)
    dec = df.filter(pl.col("drift") != 0, pl.col("result") != "push").with_columns(
        D.outcome(pl.col("drift_pick_home")).alias("o"))
    beta, se = D.logistic(dec["abs_drift"].to_numpy(), (dec["o"] == "W").to_numpy().astype(float))
    res["logit"] = {"intercept": beta[0], "slope": beta[1], "slope_se": se[1], "n": dec.height}

    # key numbers crossed (3 or 7) between open and close
    def crossed(k):
        a, b = pl.col("home_spread").abs(), pl.col("market_spread").abs()
        return ((a < k) & (b > k)) | ((a > k) & (b < k)) | ((a == k) != (b == k))
    kn = []
    for lab, cond in [("crossed 3 or 7", crossed(3) | crossed(7)), ("did not", ~(crossed(3) | crossed(7)))]:
        x = df.filter(cond & (pl.col("drift") != 0))
        kn.append({"group": lab, **D.summarize(x.select(D.outcome(D.strategy_picks(x)).alias("o"))["o"])})
    res["key_numbers"] = pl.DataFrame(kn)

    # walk-forward D-k
    wf = []
    for s in seasons:
        train = df.filter(pl.col("season") < s)
        if train["season"].n_unique() < 3:
            continue
        k = D.choose_k(train)
        x = df.filter(pl.col("season") == s)
        wf.append({"season": s, "k": k, **D.summarize(x.select(D.outcome(D.strategy_picks(x, k, False)).alias("o"))["o"])})
    wfd = pl.DataFrame(wf)
    w, l = int(wfd["W"].sum()), int(wfd["L"].sum())
    p = w / (w + l)
    res["walk_forward"] = wfd
    res["walk_forward_pooled"] = {"W": w, "L": l, "N": w + l, "win_rate": p,
                                  "se": math.sqrt(p * (1 - p) / (w + l)),
                                  "seasons": f"{wfd['season'].min()}-{wfd['season'].max()}"}
    # robustness (diagnostic): outliers and an independent close source
    rob = []
    for lab, x in [("all games (primary)", df),
                   ("abs(drift) < 4.5 (drops possible SBRO open errors)", df.filter(pl.col("abs_drift") < 4.5))]:
        rob.append({"check": lab, **D.summarize(x.select(D.outcome(D.strategy_picks(x)).alias("o"))["o"])})
    alt, _ = load("nflverse_close_home_spread")
    rob.append({"check": "market = nflverse close instead of SBRO close",
                **D.summarize(alt.select(D.outcome(D.strategy_picks(alt)).alias("o"))["o"])})
    res["robustness"] = pl.DataFrame(rob)
    # drift distribution
    res["drift_dist"] = df.group_by("drift").len().sort("drift")

    bt = config.path("backtests")
    res["per_season"].write_csv(bt / "phase3_d0_by_season.csv")
    res["buckets"].write_csv(bt / "phase3_buckets.csv")
    wfd.write_csv(bt / "phase3_walk_forward.csv")
    if out_md:
        out_md.write_text(_markdown(res))
    return res


def _tbl(df: pl.DataFrame) -> str:
    cols = df.columns
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in df.to_dicts():
        out.append("| " + " | ".join(f"{v:.4f}" if isinstance(v, float) else str(v) for v in r.values()) + " |")
    return "\n".join(out)


def _markdown(r: dict) -> str:
    d0, full = r["d0"], r["d0_full"]
    L = [f"# Phase 3 — Drift results\n",
         f"Generated {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} by "
         "`python -m engine drift`. Pre-registration: `docs/phase3_preregistration.md`. "
         "Frozen line = SBRO open (proxy); market at lock = SBRO close (proxy). Regular season 2007–2021.\n",
         f"Games: {r['counts']['reg_games']} regular season; {r['counts']['excluded_bad_open_or_close']} "
         "excluded (unusable SBRO open or close).\n",
         "## Primary test (D0: sign of drift)\n",
         _tbl(pl.DataFrame([{"strategy": "D0 sign of drift", **d0},
                            {"strategy": "D0-full (drift=0 -> away)", **full}])),
         f"\nz vs 50% = {d0['z_vs_50']:.2f}; z vs Phase 2 bar (0.5137, SE 0.0082) = {r['z_vs_bar']:.2f}.\n",
         f"**Gate: {'PASS' if r['passed'] else 'FAIL'}** (needs both z ≥ 1.96).\n",
         "## Monotonicity (|drift| buckets, D0)\n", _tbl(r["buckets"]),
         f"\nLogistic regression P(picked side covers) on |drift|: slope {r['logit']['slope']:.4f} "
         f"(SE {r['logit']['slope_se']:.4f}), intercept {r['logit']['intercept']:.4f}, n = {r['logit']['n']}.\n",
         "## Key numbers (D0, drift ≠ 0)\n", _tbl(r["key_numbers"]),
         "\n## Walk-forward D-k (k chosen on prior seasons only; else away)\n", _tbl(r["walk_forward"]),
         "\nPooled: " + ", ".join(f"{k}={v:.4f}" if isinstance(v, float) else f"{k}={v}"
                                  for k, v in r["walk_forward_pooled"].items()) + "\n",
         "## Robustness (diagnostic)\n", _tbl(r["robustness"]),
         "\n## Per season (D0 and D0-full)\n", _tbl(r["per_season"]),
         "\n## Drift distribution (close − open, home spread)\n", _tbl(r["drift_dist"])]
    return "\n".join(L)
