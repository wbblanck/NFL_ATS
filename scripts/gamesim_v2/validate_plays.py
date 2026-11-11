"""Gamesim v2: run the preregistered play-level validation (docs/gamesim_v2/PREREGISTRATION.md, tests V1-V8) on 2021.

Frozen settings come from data/gamesim_v2/manifests/g2_frozen_config.json. Seasons 2022+ are never loaded.
Writes data/gamesim_v2/manifests/validation_2021.json, and (not committed) walk-forward predictions and the per-week player effects under
data/gamesim_v2/features/. Usage: python scripts/gamesim_v2/validate_plays.py"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import polars as pl

from engine.gamesim_v2.players import abilities as A
from engine.gamesim_v2.validation import play_validation as V

ROOT = Path(__file__).resolve().parents[2]
FEAT, MAN = ROOT / "data/gamesim_v2/features", ROOT / "data/gamesim_v2/manifests"
CFG = json.loads((MAN / "g2_frozen_config.json").read_text())
SEASONS, VALID = [2018, 2019, 2020, 2021], 2021
GROUPS = {"pressure": ["OL", "DL", "LB", "QB"], "completion": ["R", "DB", "LB", "QB"]}
SEED = 7


def lam_for(kind, cfg):
    g = GROUPS[kind]
    return {**{k: cfg.get("lam_player", 1.0) for k in g}, "OT": cfg.get("lam_team", 1.0), "DT": cfg.get("lam_team", 1.0)}


def population(kind):
    d = pl.read_parquet(FEAT / "dropbacks.parquet").filter(pl.col("has_part"), pl.col("season") <= 2021)
    pos = {(s, g): p for s, g, p in pl.read_parquet(FEAT / "position_lookup.parquet").iter_rows()}
    if kind == "pressure":
        d = d.filter(pl.col("season") >= CFG["train_from"]["pressure"])
        y = (d["was_pressure"].fill_null(False) | d["sack"]).to_numpy().astype(float)
    else:
        d = d.filter(pl.col("attempt"), ~pl.col("sack"), ~pl.col("scramble"))
        y = d["complete"].to_numpy().astype(float)
    return d, pos, y


def recal(y, p):
    """Logistic recalibration y ~ a + b logit(p) by IRLS."""
    z = np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
    X = np.column_stack([np.ones_like(z), z])
    b = np.array([0.0, 1.0])
    for _ in range(30):
        mu = 1 / (1 + np.exp(-X @ b))
        W = mu * (1 - mu)
        b = b + np.linalg.solve(X.T @ (X * W[:, None]) + 1e-9 * np.eye(2), X.T @ (y - mu))
    mu = 1 / (1 + np.exp(-X @ b))
    cov = np.linalg.inv(X.T @ (X * (mu * (1 - mu))[:, None]))
    return {"a": float(b[0]), "b": float(b[1]), "se_a": float(math.sqrt(cov[0, 0])), "se_b": float(math.sqrt(cov[1, 1]))}


def fisher_ci(r, n):
    if n < 5:
        return [float("nan")] * 2
    z, se = np.arctanh(r), 1 / math.sqrt(n - 3)
    return [float(np.tanh(z - 1.96 * se)), float(np.tanh(z + 1.96 * se))]


def spearman(a, b):
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


def boot_corr(a, b, g, n=2000, seed=SEED):
    """Spearman with a bootstrap over game clusters."""
    rng = np.random.default_rng(seed)
    ug = np.unique(g)
    idx = {u: np.where(g == u)[0] for u in ug}
    vals = []
    for _ in range(n):
        pick = rng.choice(ug, len(ug))
        ii = np.concatenate([idx[u] for u in pick])
        vals.append(spearman(a[ii], b[ii]))
    return spearman(a, b), [float(x) for x in np.percentile(vals, [2.5, 97.5])]


def run_models(kind, reuse=False):
    d, pos, y = population(kind)
    designs = V.make_designs(d, pos, kind)
    if reuse and (FEAT / f"pred_{kind}.parquet").exists() and (FEAT / f"abilities_{kind}.parquet").exists():
        return d, pos, y, designs, pl.read_parquet(FEAT / f"pred_{kind}.parquet"), pl.read_parquet(FEAT / f"abilities_{kind}.parquet")
    preds, ab = {}, None
    for v in ("ctx", "team", "player", "both"):
        c = CFG["variants"][v][kind]
        p, a = V.walk_forward(d, pos, kind, y, lam_for(kind, c), float(c["half_life_days"]), SEASONS, CFG["train_from"][kind],
                              variants=(v,), record_abilities=("player" if v == "player" else None), designs={v: designs[v]})
        preds[v] = p.select("game_id", "play_id", v)
        if v == "player":
            ab = a
            base = p.select("game_id", "play_id", "season", "week", "posteam", "defteam", "y")
    pred = base
    for v, p in preds.items():
        pred = pred.join(p, on=["game_id", "play_id"], how="left")
    pred = pred.filter(pl.all_horizontal(pl.col(v).is_not_nan() & pl.col(v).is_not_null() for v in preds))
    pred.write_parquet(FEAT / f"pred_{kind}.parquet")
    ab.write_parquet(FEAT / f"abilities_{kind}.parquet")
    return d, pos, y, designs, pred, ab


def split_half(kind, d, pos, y, designs):
    """V7: effects fit on 2018-2019 and on 2020-2021, no decay; correlation per group."""
    D = designs["player"]
    lam = np.array([1e-3 if g == "ctx" else CFG["variants"]["player"][kind]["lam_player"] for g in D.group])
    s = d["season"].to_numpy()
    halves = [np.where(np.isin(s, h))[0] for h in ([2018, 2019], [2020, 2021])]
    fits = []
    for ix in halves:
        b0, beta = A.fit_logit(D.X[ix], y[ix], np.ones(len(ix)), lam)
        fits.append((beta, np.asarray(D.X[ix].sum(0)).ravel()))
    minn = 400 if kind == "pressure" else 150
    out = {}
    names = np.array(D.names)
    groups = ["OL", "RUSH", "QB"] if kind == "pressure" else ["R", "DB", "QB"]
    for g in groups:
        sel = np.isin(D.group, ["DL", "LB"]) if g == "RUSH" else (D.group == g)
        ok = sel & (fits[0][1] >= minn) & (fits[1][1] >= minn)
        n = int(ok.sum())
        r = float(np.corrcoef(fits[0][0][ok], fits[1][0][ok])[0, 1]) if n > 3 else float("nan")
        out[g] = {"players": n, "r": r, "ci95": fisher_ci(r, n) if n > 3 else None}
    return out


def effect_maps(ab):
    m = {}
    for s, w, k, b in zip(ab["season"], ab["week"], ab["key"], ab["beta"]):
        if ":" in k:
            m.setdefault((s, w), {})[k] = b
    return m


def main(reuse=False):
    res = {"config": CFG, "validation_season": VALID}
    store = {}
    for kind in ("pressure", "completion"):
        d, pos, y, designs, pred, ab = run_models(kind, reuse)
        store[kind] = (d, pos, y, designs, pred, ab)
        v = pred.filter(pl.col("season") == VALID)
        yy = v["y"].to_numpy()
        r = {"n_plays": v.height, "base_rate": float(yy.mean()),
             "logloss": {x: float(V.logloss(yy, v[x].to_numpy()).mean()) for x in ("ctx", "team", "player", "both")},
             "brier": {x: V.brier(yy, v[x].to_numpy()) for x in ("ctx", "team", "player", "both")}}
        r["V_player_vs_ctx"] = V.compare(v, "ctx", "player")
        r["V_player_vs_team"] = V.compare(v, "team", "player")
        r["V_team_vs_ctx"] = V.compare(v, "ctx", "team")
        r["V_both_vs_player"] = V.compare(v, "player", "both")
        r["V5_recalibration_player"] = recal(yy, v["player"].to_numpy())
        r["V5_recalibration_team"] = recal(yy, v["team"].to_numpy())
        r["V7_split_half"] = split_half(kind, d, pos, y, designs)
        res[kind] = r
    # V6: line gradient (pressure). Per play, sum of the OL effects as estimated before that play's week.
    d, pos, y, designs, pred, ab = store["pressure"]
    em = effect_maps(ab)
    v = pred.filter(pl.col("season") == VALID).join(d.select("game_id", "play_id", "offense_players", "defense_players"),
                                                   on=["game_id", "play_id"], how="left")
    S, R = [], []
    for s, w, op, dp in zip(v["season"], v["week"], v["offense_players"], v["defense_players"]):
        m = em.get((s, w), {})
        S.append(sum(m.get("OL:" + p, 0.0) for p in (op or "").split(";") if pos.get((s, p)) == "OL"))
        R.append(sum(m.get("DL:" + p, 0.0) + m.get("LB:" + p, 0.0) for p in (dp or "").split(";") if pos.get((s, p)) in ("DL", "LB")))
    S, R = np.array(S), np.array(R)
    yy, gid = v["y"].to_numpy(), v["game_id"].to_numpy()
    q = np.digitize(S, np.quantile(S, [0.2, 0.4, 0.6, 0.8]))     # 0 = best protection (lowest summed pressure effect)
    rates = [float(yy[q == i].mean()) for i in range(5)]
    rng = np.random.default_rng(SEED)
    ug = np.unique(gid)
    idx = {u: np.where(gid == u)[0] for u in ug}
    diffs = []
    for _ in range(2000):
        ii = np.concatenate([idx[u] for u in rng.choice(ug, len(ug))])
        qq, y2 = q[ii], yy[ii]
        diffs.append(y2[qq == 4].mean() - y2[qq == 0].mean())
    res["V6_line_gradient"] = {"rate_by_quintile_best_to_worst_protection": rates, "worst_minus_best": rates[4] - rates[0],
                               "ci95": [float(x) for x in np.percentile(diffs, [2.5, 97.5])],
                               "monotone_increasing": bool(all(rates[i] < rates[i + 1] for i in range(4)))}
    # V8: pregame expected lineup at the team-game level
    snap = pl.read_parquet(ROOT / f"data/gamesim_v2/snapshots/pregame_players_{VALID}.parquet").filter(pl.col("p_active") >= 0.5)
    resid = v.group_by("game_id", "posteam", "defteam", "season", "week").agg(
        pl.col("y").mean().alias("obs"), pl.col("ctx").mean().alias("ctx"), pl.col("player").mean().alias("player_act"),
        pl.col("team").mean().alias("team_act")).with_columns((pl.col("obs") - pl.col("ctx")).alias("res"),
                                                              (pl.col("player_act") - pl.col("ctx")).alias("act_shift"),
                                                              (pl.col("team_act") - pl.col("ctx")).alias("team_shift"))
    rows = []
    for r_ in resid.iter_rows(named=True):
        m = em.get((r_["season"], r_["week"]), {})
        o = snap.filter((pl.col("game_id") == r_["game_id"]) & (pl.col("team") == r_["posteam"]) & (pl.col("pos_grp") == "OL")).sort("off_share_active", descending=True).head(5)["uid"].to_list()
        dl = snap.filter((pl.col("game_id") == r_["game_id"]) & (pl.col("team") == r_["defteam"]) & (pl.col("pos_grp") == "DL")).sort("def_share_active", descending=True).head(4)["uid"].to_list()
        lb = snap.filter((pl.col("game_id") == r_["game_id"]) & (pl.col("team") == r_["defteam"]) & (pl.col("pos_grp") == "LB")).sort("def_share_active", descending=True).head(3)["uid"].to_list()
        rows.append((sum(m.get("OL:" + u, 0.0) for u in o), sum(m.get("DL:" + u, 0.0) for u in dl) + sum(m.get("LB:" + u, 0.0) for u in lb)))
    ol_s, rush_s = np.array([a for a, _ in rows]), np.array([b for _, b in rows])
    rr, gg = resid["res"].to_numpy(), resid["game_id"].to_numpy()
    out8 = {"team_games": resid.height}
    for name, sc in (("expected_OL_sum", ol_s), ("expected_rush_sum", rush_s), ("expected_OL_plus_rush", ol_s + rush_s),
                     ("actual_lineup_player_shift", resid["act_shift"].to_numpy()), ("team_effect_shift", resid["team_shift"].to_numpy())):
        r, ci = boot_corr(sc, rr, gg)
        out8[name] = {"spearman": r, "ci95": ci}
    res["V8_pregame_signal"] = out8
    (MAN / "validation_2021.json").write_text(json.dumps(res, indent=1, default=float))
    for kind in ("pressure", "completion"):
        r = res[kind]
        print(kind, r["n_plays"], r["logloss"], r["V_player_vs_ctx"], r["V_player_vs_team"], r["V5_recalibration_player"], r["V7_split_half"], sep="\n  ")
    print(res["V6_line_gradient"], res["V8_pregame_signal"], sep="\n")


if __name__ == "__main__":
    import sys

    main("--reuse" in sys.argv)
