"""Phase 6 ablation (docs/phase6_preregistration.md)."""
from __future__ import annotations

import datetime as dt
import math

import numpy as np
import polars as pl

from engine import config
from engine.backtest import calibration as C
from engine.backtest.phase5 import oos_predictions
from engine.data import nflverse
from engine.features.efficiency import efficiency_feature, game_epa, ratings
from engine.features.qb import qb_change
from engine.features.rest import rest_features

GROUPS = {
    "qb": ["qb_change_home", "qb_change_away"],
    "rest": ["rest_diff", "home_short", "away_short", "home_bye", "away_bye"],
    "efficiency": ["net_eff_diff"],
}


def build() -> pl.DataFrame:
    import nflreadpy as nfl
    sched, _ = nflverse.pull("schedules", save=False)
    ts = nfl.load_team_stats(seasons=list(range(1999, 2022)))
    feats = qb_change(sched).join(rest_features(sched), on="game_id", how="left") \
        .join(efficiency_feature(sched, ratings(game_epa(ts))), on="game_id", how="left")
    return oos_predictions().join(feats, on="game_id", how="left").fill_null(0)


def _summ(p, y, raw):
    w = int(((p > 0.5) == (y == 1)).sum()); n = len(y); r = w / n
    return {"n": n, "log_loss": C.log_loss(p, y), "brier": C.brier(p, y), "ece": C.ece(p, y),
            "ats_W": w, "ats_win_rate": r, "ats_se": math.sqrt(r * (1 - r) / n),
            "picks_changed_vs_raw": int(((p > 0.5) != (raw > 0.5)).sum())}


def evaluate(d: pl.DataFrame, cols: list[str] | None):
    ps, ys, raws, coefs = [], [], [], []
    for s in range(2010, 2022):
        tr, te = d.filter(pl.col("season") < s), d.filter(pl.col("season") == s)
        f = C.platt(tr["p"].to_numpy(), tr["y"].to_numpy(),
                    tr.select(cols).to_numpy().astype(float) if cols else None)
        ps.append(f(te["p"].to_numpy(), te.select(cols).to_numpy().astype(float) if cols else None))
        ys.append(te["y"].to_numpy()); raws.append(te["p"].to_numpy())
        coefs.append({"season": s, **{f"g_{c}": float(v) for c, v in zip(cols or [], f.coef[2:])}})
    return np.concatenate(ps), np.concatenate(ys), np.concatenate(raws), pl.DataFrame(coefs)


def run(out_md=None) -> dict:
    d = build()
    test = d.filter(pl.col("season") >= 2010)
    raw_p, y = test["p"].to_numpy(), test["y"].to_numpy()
    rows = [{"model": "raw", **_summ(raw_p, y, raw_p)}]
    pp, py, pr, _ = evaluate(d, None)
    rows.append({"model": "platt (no features)", **_summ(pp, py, pr)})
    base_raw, base_platt = rows[0], rows[1]
    kept, coefs = [], {}
    for g, cols in GROUPS.items():
        p, yy, r, cf = evaluate(d, cols)
        s = _summ(p, yy, r)
        keep = s["log_loss"] < base_raw["log_loss"] and s["log_loss"] < base_platt["log_loss"] \
            and s["ats_win_rate"] >= base_raw["ats_win_rate"]
        rows.append({"model": f"+ {g}", **s, "kept": keep})
        coefs[g] = cf
        if keep:
            kept.append(g)
    if len(kept) > 1:
        cols = [c for g in kept for c in GROUPS[g]]
        p, yy, r, cf = evaluate(d, cols)
        rows.append({"model": "+ " + " + ".join(kept), **_summ(p, yy, r)})
        coefs["combined"] = cf
    T = pl.DataFrame(rows, infer_schema_length=None)
    desc = d.select([pl.col(c).mean().alias(f"mean_{c}") for g in GROUPS.values() for c in g])
    res = {"table": T, "kept": kept, "coefs": coefs, "feature_means": desc}
    T.write_csv(config.path("backtests") / "phase6_ablation.csv")
    if out_md:
        out_md.write_text(_md(res))
    return res


def _tbl(df):
    cols = df.columns
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in df.to_dicts():
        out.append("| " + " | ".join(f"{v:.4f}" if isinstance(v, float) else str(v) for v in r.values()) + " |")
    return "\n".join(out)


def _md(r):
    L = ["# Phase 6 — Residual feature ablation\n",
         f"Generated {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} by `python -m engine features`. "
         "Pre-registration: `docs/phase6_preregistration.md`. Test seasons 2010–2021 walk-forward; frozen line = SBRO "
         "open, market = nflverse close. Weather and OL/pass-rush not tested (see pre-registration).\n",
         "## Ablation (out of sample)\n", _tbl(r["table"]),
         f"\n**Kept groups: {', '.join(r['kept']) if r['kept'] else 'none'}.**\n",
         "## Feature means (all games 2007–2021)\n", _tbl(r["feature_means"])]
    for g, cf in r["coefs"].items():
        L += [f"\n## Fitted γ per test season — {g}\n", _tbl(cf)]
    return "\n".join(L)
