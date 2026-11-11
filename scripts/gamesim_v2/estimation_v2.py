"""Gamesim v2: development run for docs/gamesim_v2/PREREGISTRATION_estimation_v2.md (M1-M3). Seasons through 2020 only.
Writes features/abilities_v2_<kind>.parquet (not committed) and manifests/estimation_v2.json. Usage: python scripts/gamesim_v2/estimation_v2.py"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import polars as pl

from engine.gamesim_v2.players import abilities as A, abilities_v2 as B
from engine.gamesim_v2.validation import play_validation as V, play_validation_v2 as V2

ROOT = Path(__file__).resolve().parents[2]
FEAT, MAN = ROOT / "data/gamesim_v2/features", ROOT / "data/gamesim_v2/manifests"
LAST, EVAL = 2020, [2019, 2020]
START = {"pressure": 2018, "completion": 2016, "epa": 2016}
LAM = {"OL": 100.0, "DL": 100.0, "LB": 100.0, "QB": 100.0, "R": 100.0, "DB": 100.0, "OT": 100.0, "DT": 100.0}
HALVES = {"pressure": ([2018, 2019], [2020]), "completion": ([2016, 2017, 2018], [2019, 2020]), "epa": ([2016, 2017, 2018], [2019, 2020])}
MINN = {"pressure": 400, "completion": 150, "epa": 150}


def population(kind):
    d = pl.read_parquet(FEAT / "dropbacks.parquet").filter(pl.col("has_part"), pl.col("season") <= LAST)
    pos = {(s, g): p for s, g, p in pl.read_parquet(FEAT / "position_lookup.parquet").filter(pl.col("season") <= LAST).iter_rows()}
    if kind == "pressure":
        d = d.filter(pl.col("season") >= START[kind])
        y = (d["was_pressure"].fill_null(False) | d["sack"]).to_numpy().astype(float)
    elif kind == "completion":
        # a null target (2,018 plays, never completed) is only known after the play: keeping them lets "has a target" leak into the prior columns
        d = d.filter(pl.col("attempt"), ~pl.col("sack"), ~pl.col("scramble"), pl.col("target").is_not_null())
        y = d["complete"].to_numpy().astype(float)
    else:
        d = d.filter(pl.col("attempt"), ~pl.col("sack"), ~pl.col("scramble"), pl.col("epa").is_not_null(), pl.col("target").is_not_null())
        y = d["epa"].to_numpy().astype(float)
    return d, pos, y


def fisher(r, n):
    if n < 5:
        return None
    z, se = np.arctanh(r), 1 / math.sqrt(n - 3)
    return [float(np.tanh(z - 1.96 * se)), float(np.tanh(z + 1.96 * se))]


def split_half(kind, d, pos, y, meta, designs_noprior, design_prior, family):
    s = d["season"].to_numpy()
    h1, h2 = (np.where(np.isin(s, h))[0] for h in HALVES[kind])
    out = {}
    for tag, D in (("no_prior", designs_noprior), ("prior", design_prior)):
        lam = B.lam_vector(D, LAM)
        fits = []
        for ix, last in ((h1, max(HALVES[kind][0])), (h2, max(HALVES[kind][1]))):
            if family == "logit":
                b0, beta = A.fit_logit(D.X[ix], y[ix], np.ones(len(ix)), lam)
            else:
                b0, beta, *_ = B.fit_gauss(D.X[ix], y[ix], np.ones(len(ix)), lam)
            cov = {n: beta[j] for j, n in enumerate(D.names) if n.startswith("cov|")}
            tot = beta.copy()
            for j, nm in enumerate(D.names):
                if ":" in nm and not nm.startswith("cov|"):
                    g, u = nm.split(":", 1)
                    tot[j] = beta[j] + sum(cov.get(f"cov|{g}|{b}", 0.0) for b in B.buckets(meta, u, last))
            fits.append((tot, beta, np.asarray(D.X[ix].sum(0)).ravel()))
        grp = ["OL", "RUSH", "QB"] if kind == "pressure" else ["R", "DB", "QB"]
        for g in grp:
            sel = np.isin(D.group, ["DL", "LB"]) if g == "RUSH" else (D.group == g)
            ok = sel & (fits[0][2] >= MINN[kind]) & (fits[1][2] >= MINN[kind])
            n = int(ok.sum())
            r_tot = float(np.corrcoef(fits[0][0][ok], fits[1][0][ok])[0, 1]) if n > 3 else float("nan")
            r_dev = float(np.corrcoef(fits[0][1][ok], fits[1][1][ok])[0, 1]) if n > 3 else float("nan")
            out.setdefault(g, {})[tag] = {"players": n, "r_total_effect": r_tot, "ci95": fisher(r_tot, n), "r_deviation_only": r_dev}
    return out


def main():
    ident = pl.read_parquet(ROOT / "data/gamesim_v2/processed/player_identity.parquet")
    meta = B.player_meta(ident)
    out = MAN / "estimation_v2.json"
    res = json.loads(out.read_text()) if out.exists() else {}
    res.update({"model_version": B.MODEL_VERSION, "eval_seasons": EVAL})
    kinds = sys.argv[1:] or ["pressure", "completion", "epa"]
    for kind in kinds:
        d, pos, y = population(kind)
        family = "gauss" if kind == "epa" else "logit"
        d_prior = B.build_design_v2(d, pos, kind, meta, prior=True)
        d_noprior = B.build_design_v2(d, pos, kind, meta, prior=False)
        r = {"n_plays": d.height}
        if kind == "epa":
            designs = {"ctx": B.build_design_v2(d, pos, kind, meta, prior=False, player_effects=False),
                       "team": B.build_design_v2(d, pos, kind, meta, prior=False, player_effects=False, team_effects=True),
                       "player0": d_noprior, "player_prior": d_prior}
        else:
            designs = {"v2_noprior": d_noprior, "v2_prior": d_prior}
        lams = {k: B.lam_vector(D, LAM) for k, D in designs.items()}
        rec = "player_prior" if kind == "epa" else "v2_prior"
        pred, ab = V2.walk_forward_v2(d, kind, y, designs, lams, family, 730.0, EVAL, START[kind], meta, record=rec)
        ab.write_parquet(FEAT / f"abilities_v2_{kind}.parquet")
        pred.write_parquet(FEAT / f"pred_v2_{kind}.parquet")
        if family == "logit":
            # control = the same pipeline without prior columns (reproduces the frozen v1 player model to 1e-6 log loss on the 2016-2020 completion population)
            pr = pred
            r["M1_v2_prior_vs_v2_noprior_logloss"] = V.compare(pr, "v2_noprior", "v2_prior")
            for s in EVAL:
                r[f"M1_{s}"] = V.compare(pr.filter(pl.col("season") == s), "v2_noprior", "v2_prior")
            r["logloss"] = {k: float(V.logloss(pr["y"].to_numpy(), pr[k].to_numpy()).mean()) for k in ("v2_noprior", "v2_prior")}
        else:
            r["mse"] = {k: float(((pred["y"].to_numpy() - pred[k].to_numpy()) ** 2).mean()) for k in designs}
            r["M2_player_prior_vs_ctx"] = V2.compare_sq(pred, "ctx", "player_prior")
            r["M2_player_prior_vs_team"] = V2.compare_sq(pred, "team", "player_prior")
            r["M2_player_prior_vs_player0"] = V2.compare_sq(pred, "player0", "player_prior")
            r["M2_player0_vs_ctx"] = V2.compare_sq(pred, "ctx", "player0")
        r["M3_split_half"] = split_half(kind, d, pos, y, meta, d_noprior, d_prior, family)
        cov = {}
        res[kind] = r
        print(kind, json.dumps({k: v for k, v in r.items() if k != "M3_split_half"}, default=float)[:900], flush=True)
        print(" M3", json.dumps(r["M3_split_half"], default=float)[:1200], flush=True)
        out.write_text(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
