"""Gamesim v2: the preregistered game-level lineup test (docs/gamesim_v2/PREREGISTRATION_game_level.md). 2021 only, one run.
Writes data/gamesim_v2/manifests/game_level_2021.json. Usage: python scripts/gamesim_v2/game_level_test.py"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from engine.gamesim_v2.plays import passing as PS

ROOT = Path(__file__).resolve().parents[2]
FEAT, MAN = ROOT / "data/gamesim_v2/features", ROOT / "data/gamesim_v2/manifests"
TEST, SEED, HL, K = 2021, 7, 6.0, 4.0


def team_games():
    d = pl.read_parquet(FEAT / "dropbacks.parquet").filter(pl.col("has_part"), pl.col("season").is_between(2018, TEST))
    d = d.with_columns((pl.col("was_pressure").fill_null(False) | pl.col("sack")).cast(pl.Float64).alias("press"))
    att = d.filter(pl.col("attempt"), ~pl.col("sack"), ~pl.col("scramble"))
    g = d.group_by("game_id", "game_date", "season", "week", "posteam", "defteam").agg(
        pl.col("epa").mean().alias("epa"), pl.col("press").mean().alias("press"), pl.len().alias("n_db"))
    a = att.group_by("game_id", "posteam").agg(pl.col("complete").cast(pl.Float64).mean().alias("comp"), pl.len().alias("n_att"))
    return d, g.join(a, on=["game_id", "posteam"], how="left").sort("game_date", "game_id")


def form(g: pl.DataFrame, o: str) -> tuple[np.ndarray, np.ndarray]:
    """Shrunk, decayed prior mean of the offense's outcome and of the outcome its opponent defense has allowed."""
    rows = g.select("game_date", "game_id", "posteam", "defteam", o).to_dicts()
    off, dfn, allv = {}, {}, []
    fo, fd = np.zeros(len(rows)), np.zeros(len(rows))
    i = 0
    dates = sorted({r["game_date"] for r in rows})
    for dt in dates:
        today = [(j, r) for j, r in enumerate(rows) if r["game_date"] == dt]
        mu = float(np.mean(allv)) if allv else 0.0
        def est(hist):
            n = len(hist)
            w = np.array([0.5 ** ((n - 1 - t) / HL) for t in range(n)])
            return float((w @ np.array(hist) + K * mu) / (w.sum() + K)) if n else mu
        for j, r in today:
            fo[j] = est(off.get(r["posteam"], [])) - mu
            fd[j] = est(dfn.get(r["defteam"], [])) - mu
        for j, r in today:
            v = r[o]
            if v is None or v != v:
                continue
            off.setdefault(r["posteam"], []).append(v)
            dfn.setdefault(r["defteam"], []).append(v)
            allv.append(v)
    return fo, fd


def lineup_scores(g, d):
    snap = pl.read_parquet(ROOT / f"data/gamesim_v2/snapshots/pregame_players_{TEST}.parquet").filter(pl.col("p_active") >= 0.5)
    parts = snap.partition_by("game_id", "team", as_dict=True)
    ab = {}
    for k in ("pressure", "completion"):
        t = pl.read_parquet(FEAT / f"abilities_{k}.parquet").filter((pl.col("season") == TEST) & pl.col("key").str.contains(":"))
        ab[k] = {}
        for w, key, b in zip(t["week"], t["key"], t["beta"]):
            ab[k].setdefault(w, {})[key] = b
    out = []
    for r in g.filter(pl.col("season") == TEST).iter_rows(named=True):
        w = r["week"]
        so = parts.get((r["game_id"], r["posteam"]))
        sd = parts.get((r["game_id"], r["defteam"]))
        if so is None or sd is None:
            out.append((r["game_id"], r["posteam"], None, None))
            continue
        top = lambda s, grp, col, n: s.filter(pl.col("pos_grp") == grp).sort(col, descending=True).head(n)["uid"].to_list()
        P_, Cm = ab["pressure"].get(w, {}), ab["completion"].get(w, {})
        ol, qb = top(so, "OL", "off_share_active", 5), top(so, "QB", "off_share_active", 1)
        dl, lb, db = top(sd, "DL", "def_share_active", 4), top(sd, "LB", "def_share_active", 3), top(sd, "DB", "def_share_active", 4)
        P = sum(P_.get("OL:" + u, 0) for u in ol) + sum(P_.get("DL:" + u, 0) for u in dl) + sum(P_.get("LB:" + u, 0) for u in lb)
        ts = PS.target_shares(d.filter(pl.col("season") <= TEST), r["posteam"], r["game_date"], 8)
        act = set(so.filter(pl.col("pos_grp").is_in(["WR", "TE", "RB"]))["uid"].to_list())
        sh = {u: s for u, s in ts.items() if u in act}
        tot = sum(sh.values())
        recv = sum(Cm.get("R:" + u, 0) * s / tot for u, s in sh.items()) if tot else 0.0
        C = sum(Cm.get("QB:" + u, 0) for u in qb) + recv + sum(Cm.get("DB:" + u, 0) for u in db) + sum(Cm.get("LB:" + u, 0) for u in lb)
        out.append((r["game_id"], r["posteam"], P, C))
    return pl.DataFrame(out, schema=["game_id", "posteam", "P", "C"], orient="row")


def wls(X, y, w):
    W = np.sqrt(w)
    b, *_ = np.linalg.lstsq(X * W[:, None], y * W, rcond=None)
    return b


def analyse(df, o, wcol, pred, seed=SEED, nb=2000):
    y = df[o].to_numpy()
    w = df[wcol].to_numpy().astype(float)
    fo, fd = form(df_full, o)  # placeholder replaced below
    return None


def run():
    global df_full
    d, g = team_games()
    df_full = g
    sc = lineup_scores(g, d)
    res = {"test_season": TEST}
    forms = {o: form(g, o) for o in ("epa", "press", "comp")}
    gt = g.with_row_index("i").filter(pl.col("season") == TEST).join(sc, on=["game_id", "posteam"], how="left")
    ok = gt["P"].is_not_null() & gt["epa"].is_not_null() & gt["comp"].is_not_null()
    gt = gt.filter(ok)
    idx = gt["i"].to_numpy()
    P, C = gt["P"].to_numpy(), gt["C"].to_numpy()
    z = lambda x: (x - x.mean()) / x.std()
    S = z(C) + z(-P)
    res["team_games_used"] = int(gt.height)
    res["corr_P_C"] = float(np.corrcoef(P, C)[0, 1])
    gid, week = gt["game_id"].to_numpy(), gt["week"].to_numpy()
    ug = np.unique(gid)
    cl = {u: np.where(gid == u)[0] for u in ug}
    rng = np.random.default_rng(SEED)
    boots = [np.concatenate([cl[u] for u in rng.choice(ug, len(ug))]) for _ in range(2000)]
    tests = {"epa": ("n_db", S, "S"), "press": ("n_db", -P, "-P"), "comp": ("n_att", C, "C")}
    for o, (wc, x, name) in tests.items():
        y, w = gt[o].to_numpy(), gt[wc].to_numpy().astype(float)
        fo, fd = forms[o][0][idx], forms[o][1][idx]
        X0 = np.column_stack([np.ones(len(y)), fo, fd])
        X1 = np.column_stack([X0, x])
        b0, b1 = wls(X0, y, w), wls(X1, y, w)
        coef = lambda ii: wls(X1[ii], y[ii], w[ii])[-1]
        bs = np.array([coef(ii) for ii in boots])
        sdx = x.std()
        # leave-one-week-out squared errors
        e0, e1 = np.zeros(len(y)), np.zeros(len(y))
        for wk in np.unique(week):
            te, tr = week == wk, week != wk
            p0 = X0[te] @ wls(X0[tr], y[tr], w[tr])
            p1 = X1[te] @ wls(X1[tr], y[tr], w[tr])
            e0[te], e1[te] = (y[te] - p0) ** 2, (y[te] - p1) ** 2
        d_ = w * (e1 - e0)
        dm = d_.sum() / w.sum()
        dbs = np.array([d_[ii].sum() / w[ii].sum() for ii in boots])
        resid = y - X0 @ b0
        res[o] = {"predictor": name, "coef": float(b1[-1]), "ci95": [float(v) for v in np.percentile(bs, [2.5, 97.5])],
                  "per_sd_of_predictor": float(b1[-1] * sdx), "form_coefs": [float(b1[1]), float(b1[2])],
                  "outcome_sd": float(np.sqrt(np.average((y - np.average(y, weights=w)) ** 2, weights=w))),
                  "cv_wmse_form_only": float((w * e0).sum() / w.sum()), "cv_wmse_form_plus": float((w * e1).sum() / w.sum()),
                  "cv_mse_diff": float(dm), "cv_mse_diff_ci95": [float(v) for v in np.percentile(dbs, [2.5, 97.5])],
                  "corr_predictor_with_form_residual": float(np.corrcoef(x, resid)[0, 1]),
                  "corr_form_off_with_outcome": float(np.corrcoef(fo, y)[0, 1])}
    e = res["epa"]
    res["G1_pass"] = bool(e["ci95"][0] > 0 and e["cv_mse_diff_ci95"][1] < 0)
    (MAN / "game_level_2021.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    run()
