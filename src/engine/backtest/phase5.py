"""Phase 5 runner (docs/phase5_preregistration.md)."""
from __future__ import annotations

import datetime as dt
import math

import polars as pl

from engine import config
from engine.backtest import calibration as C
from engine.backtest.common import md_table as _tbl
from engine.backtest.phase4 import load
from engine.models.margin_dist import MarginDist

METHODS = ("raw", "platt", "isotonic", "platt_key")


def oos_predictions() -> pl.DataFrame:
    """Phase 4 default estimator, walk-forward 2007-2021, pushes excluded."""
    df, _ = load()
    out = []
    for s in range(2007, 2022):
        tr = df.filter(pl.col("season") < s)
        te = df.filter(pl.col("season") == s, pl.col("open").is_not_null(),
                       pl.col("margin") != -pl.col("open"))
        md = MarginDist("shifted").fit(tr["close"].to_numpy(), tr["margin"].to_numpy())
        p = md.sf(-te["open"].to_numpy(), te["close"].to_numpy())
        out.append(te.with_columns(pl.Series("p", p),
                                   (pl.col("margin") > -pl.col("open")).cast(pl.Float64).alias("y")))
    d = pl.concat(out)
    return d.with_columns(pl.Series("key", C.key_feature(d["open"].to_numpy(), d["close"].to_numpy())))


def run(out_md=None) -> dict:
    d = oos_predictions()
    rows = []
    coefs = []
    for s in range(2010, 2022):
        tr, te = d.filter(pl.col("season") < s), d.filter(pl.col("season") == s)
        ptr, ytr, ktr = tr["p"].to_numpy(), tr["y"].to_numpy(), tr["key"].to_numpy()
        pte, kte = te["p"].to_numpy(), te["key"].to_numpy()
        pl_ = C.platt(ptr, ytr)
        pk = C.platt(ptr, ytr, ktr)
        iso = C.isotonic(ptr, ytr)
        coefs.append({"season": s, "platt_a": pl_.coef[0], "platt_b": pl_.coef[1],
                      "pk_a": pk.coef[0], "pk_b": pk.coef[1], "pk_g": pk.coef[2]})
        preds = {"raw": pte, "platt": pl_(pte), "isotonic": iso(pte), "platt_key": pk(pte, kte)}
        for m, p in preds.items():
            rows.extend({"season": s, "method": m, "p": float(pi), "y": float(yi), "p_raw": float(ri)}
                        for pi, yi, ri in zip(p, te["y"].to_numpy(), pte))
    R = pl.DataFrame(rows)
    pooled, per, rel = [], [], {}
    for m in METHODS:
        x = R.filter(pl.col("method") == m)
        p, y, pr = x["p"].to_numpy(), x["y"].to_numpy(), x["p_raw"].to_numpy()
        w = int(((p > 0.5) == (y == 1)).sum()); n = len(y); r = w / n
        pooled.append({"method": m, "n": n, "log_loss": C.log_loss(p, y), "brier": C.brier(p, y),
                       "ece": C.ece(p, y), "ats_W": w, "ats_win_rate": r, "ats_se": math.sqrt(r * (1 - r) / n),
                       "picks_changed_vs_raw": int(((p > 0.5) != (pr > 0.5)).sum())})
        rel[m] = pl.DataFrame(C.reliability(p, y))
        for s in range(2010, 2022):
            xs = x.filter(pl.col("season") == s)
            per.append({"season": s, "method": m, "log_loss": C.log_loss(xs["p"].to_numpy(), xs["y"].to_numpy())})
    P = pl.DataFrame(pooled)
    raw = P.filter(pl.col("method") == "raw").row(0, named=True)
    qual = P.filter((pl.col("method") != "raw") & (pl.col("log_loss") < raw["log_loss"]) & (pl.col("ece") <= raw["ece"])) \
        .sort("log_loss")
    chosen = qual["method"][0] if qual.height else "raw"
    ch = P.filter(pl.col("method") == chosen).row(0, named=True)
    use_cal_pick = chosen != "raw" and ch["ats_win_rate"] >= raw["ats_win_rate"]
    res = {"pooled": P, "per_season": pl.DataFrame(per).pivot(on="method", index="season", values="log_loss"),
           "reliability": rel, "coefs": pl.DataFrame(coefs), "chosen": chosen, "use_calibrated_pick": use_cal_pick}
    bt = config.path("backtests")
    P.write_csv(bt / "phase5_pooled.csv")
    res["per_season"].write_csv(bt / "phase5_by_season.csv")
    res["coefs"].write_csv(bt / "phase5_coefs.csv")
    for m, t in rel.items():
        t.write_csv(bt / f"phase5_reliability_{m}.csv")
    if out_md:
        out_md.write_text(_md(res))
    return res


def _md(r):
    L = ["# Phase 5 — Calibration results\n",
         f"Generated {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} by `python -m engine calibrate`. "
         "Pre-registration: `docs/phase5_preregistration.md`. Test seasons 2010–2021; each calibrator fit only on "
         "earlier seasons' out-of-sample Phase 4 predictions.\n",
         "## Pooled (2010–2021)\n", _tbl(r["pooled"]),
         f"\n**Chosen: `{r['chosen']}`.** Calibrated pick replaces raw argmax: "
         f"**{'YES' if r['use_calibrated_pick'] else 'NO'}**.\n",
         "## Reliability tables (buckets fixed in pre-registration)\n"]
    for m, t in r["reliability"].items():
        L += [f"### {m}\n", _tbl(t), ""]
    L += ["## Log loss per season\n", _tbl(r["per_season"]),
          "\n## Fitted coefficients per test season\n", _tbl(r["coefs"])]
    return "\n".join(L)
