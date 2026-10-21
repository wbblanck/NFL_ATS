"""Phase 4 walk-forward evaluation (docs/phase4_preregistration.md)."""
from __future__ import annotations

import datetime as dt
import math

import numpy as np
import polars as pl

from engine import config
from engine.backtest.common import md_table as _tbl
from engine.data import nflverse, sbro
from engine.models.margin_dist import MarginDist, brier, choose_h, log_loss

KINDS = ("normal", "shifted", "kernel", "kernel_sym")


def load():
    sched, sid = nflverse.pull("schedules", save=False)
    reg = sched.filter(pl.col("game_type").is_in(list(config.league().game_types)),
                       pl.col("result").is_not_null(), pl.col("spread_line").is_not_null())
    base = reg.select("game_id", "season", pl.col("result").alias("margin"),
                      (-pl.col("spread_line")).alias("close"))
    sb = sbro.match_schedule(sbro.load_all(config.ROOT / "data" / "raw" / "sbro"), sched) \
        .select("game_id", pl.col("open_home_spread").alias("open"))
    return base.join(sb, on="game_id", how="left"), sid


def run(out_md=None) -> dict:
    df, sid = load()
    rows, per = [], []
    counts = {"push_on_open": 0, "missing_open": 0}
    for s in range(2007, 2022):
        tr = df.filter(pl.col("season") < s)
        te = df.filter(pl.col("season") == s)
        counts["missing_open"] += te.filter(pl.col("open").is_null()).height
        te = te.filter(pl.col("open").is_not_null())
        push = te.filter(pl.col("margin") == -pl.col("open"))
        counts["push_on_open"] += push.height
        te = te.filter(pl.col("margin") != -pl.col("open"))
        tc, tm, ts = (tr[x].to_numpy().astype(float) for x in ("close", "margin", "season"))
        y = (te["margin"].to_numpy() > -te["open"].to_numpy()).astype(float)
        rec = {"season": s, "n": te.height}
        for kind in KINDS:
            h = choose_h(tc, tm, ts, kind) if kind.startswith("kernel") else float("nan")
            md = MarginDist(kind=kind, h=h if not math.isnan(h) else 1.0).fit(tc, tm)
            p = md.sf(-te["open"].to_numpy(), te["close"].to_numpy())
            rec[f"ll_{kind}"] = log_loss(p, y)
            rec[f"h_{kind}"] = h
            for gi, (pi, yi) in enumerate(zip(p, y)):
                rows.append({"season": s, "kind": kind, "p": pi, "y": yi,
                             "drift": te["close"][gi] - te["open"][gi]})
        per.append(rec)
    R = pl.DataFrame(rows)
    pooled = []
    for kind in KINDS:
        x = R.filter(pl.col("kind") == kind)
        p, y = x["p"].to_numpy(), x["y"].to_numpy()
        pick_home = p > 0.5
        w = int(((pick_home) == (y == 1)).sum())
        n = len(y)
        rate = w / n
        pooled.append({"estimator": kind, "n": n, "log_loss": log_loss(p, y), "brier": brier(p, y),
                       "argmax_W": w, "argmax_L": n - w, "argmax_win_rate": rate,
                       "argmax_se": math.sqrt(rate * (1 - rate) / n),
                       "p_min": float(p.min()), "p_max": float(p.max())})
    P = pl.DataFrame(pooled).sort("log_loss")
    # D0-full on the same games (drift<0 -> home; else away)
    x = R.filter(pl.col("kind") == KINDS[0])
    d_home = x["drift"].to_numpy() < 0
    y = x["y"].to_numpy()
    w = int((d_home == (y == 1)).sum()); n = len(y); r = w / n
    d0 = {"W": w, "L": n - w, "N": n, "win_rate": r, "se": math.sqrt(r * (1 - r) / n)}
    # coin-flip reference log loss
    ref = log_loss(np.full(n, 0.5), y)
    best = P.row(0, named=True)
    switch = best["argmax_win_rate"] >= d0["win_rate"]
    res = {"pooled": P, "per_season": pl.DataFrame(per), "d0_full_same_games": d0, "counts": counts,
           "coinflip_ll": ref, "best": best["estimator"], "switch_pick_rule": switch, "snapshot": sid}
    bt = config.path("backtests")
    P.write_csv(bt / "phase4_pooled.csv")
    res["per_season"].write_csv(bt / "phase4_by_season.csv")
    if out_md:
        out_md.write_text(_md(res))
    return res


def _md(r):
    d0 = r["d0_full_same_games"]
    return "\n".join([
        "# Phase 4 — Cover-probability results\n",
        f"Generated {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} by `python -m engine coverprob` "
        f"(nflverse snapshot {r['snapshot']}). Pre-registration: `docs/phase4_preregistration.md`. "
        "Walk-forward 2007–2021; target = home covers the SBRO open (frozen-line proxy); c = nflverse close "
        "(market-at-lock proxy). Kernel bandwidth chosen per test season on the last 3 training seasons "
        "(validation thresholds = close ± 0.5).\n",
        f"Excluded: {r['counts']['push_on_open']} pushes on a whole-number open, "
        f"{r['counts']['missing_open']} games with no usable open. Coin-flip log loss = {r['coinflip_ll']:.4f}.\n",
        "## Pooled out-of-sample\n", _tbl(r["pooled"]),
        f"\nD0-full drift rule on the same games: W {d0['W']} L {d0['L']} → {d0['win_rate']:.4f} (SE {d0['se']:.4f}).\n",
        f"**Default estimator (lowest log loss): `{r['best']}`.** Pick-rule switch to argmax "
        f"(pre-registered: only if argmax ATS ≥ D0-full): **{'YES' if r['switch_pick_rule'] else 'NO'}**.\n",
        "## Per season\n", _tbl(r["per_season"]),
    ])
