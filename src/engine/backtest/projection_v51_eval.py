"""Evaluation of proj-sim-v51 (docs/projection_v51_preregistration.md), including its stop rule."""
from __future__ import annotations

import itertools
import json

import numpy as np
import polars as pl

from engine.backtest import calibration as C
from engine.backtest import players_v3_eval as E
from engine.backtest import projection_v4_eval as E4
from engine.backtest import projection_v5_eval as E5
from engine.backtest.holdout2025 import cbs_opens_2025
from engine.models import projection as P
from engine.models import projection_v51 as S
from engine.models.margin_dist import TotalDist

TRAIN, TEST_A, TEST_B = E.TRAIN, E.TEST_A, E.TEST_B
HOLDOUT_FIT, HOLDOUT_CHECK = (2013, 2018), (2019, 2021)
GRID_A = tuple(round(x, 1) for x in np.arange(0, 0.51, 0.1))
GRID_B = tuple(round(-x, 1) for x in np.arange(0, 0.51, 0.1))
SMM_SIMS, SEED, SEED2 = 500, 1, 2


def fit_drive_model(drives, mu, seasons):
    T = S.drive_training_table(drives.filter(pl.col("season").is_between(*seasons)), mu.select("game_id", "team", "mu_td", "mu_fg"))
    M = S.DriveModel.fit(np.log(T["mu_td"].to_numpy()), np.log(T["mu_fg"].to_numpy()), T["cell"].to_numpy(), T["outcome"].to_numpy())
    ok = T.filter("dur_ok")
    return M, S.DurationPool.fit(ok["outcome"].to_list(), ok["cell"].to_numpy(), ok["dur"].to_numpy(), ok["hs0"].to_numpy(), ok["h"].to_numpy()), T


def sim_games(sched, mu, M, pool, env, sims, seed, keep=0):
    rows = {(r["game_id"], r["team"]): r for r in mu.iter_rows(named=True)}
    out = {}
    for g in sched.select("game_id", pl.col("home_team").replace(P.FRANCHISE).alias("h"),
                          pl.col("away_team").replace(P.FRANCHISE).alias("a")).iter_rows(named=True):
        rh, ra = rows.get((g["game_id"], g["h"])), rows.get((g["game_id"], g["a"]))
        if rh is None or ra is None:
            continue
        r = S.simulate({"td": rh["mu_td"], "fg": rh["mu_fg"]}, {"td": ra["mu_td"], "fg": ra["mu_fg"]},
                       rh["p_xp"], rh["p_2"], M, pool, env=env, sims=sims, seed=seed)
        out[g["game_id"]] = {"pmf": S.margin_pmf(r), "pts": (float(r.home_pts.mean()), float(r.away_pts.mean())),
                             "drives_half": r.drives_by_half.mean(0), "counts": r.counts[:keep] if keep else None,
                             "mu": (rh["mu_td"], rh["mu_fg"], ra["mu_td"], ra["mu_fg"]),
                             "obs": (rh["td"], rh["fg"], ra["td"], ra["fg"])}
    return out


def _corr_from(sims: dict, observed=False):
    ids = list(sims)
    mu = np.array([sims[i]["mu"] for i in ids], float)
    x = np.array([sims[i]["obs"] for i in ids], float) if observed else np.stack([sims[i]["counts"] for i in ids], 1).astype(float)
    return E5.E4_moments(mu, x)


CROSS = [(0, 2), (0, 3), (1, 2), (1, 3)]


def smm(sched, mu, M, pool, log=None) -> dict:
    """(a, b) minimising squared gaps in cross-team residual correlations (training seasons given)."""
    obs = _corr_from(sim_games(sched, mu, M, pool, (0, 0), 1, SEED, keep=1), observed=True)["corr"]
    rows = []
    for a, b in itertools.product(GRID_A, GRID_B):
        sim = _corr_from(sim_games(sched, mu, M, pool, (a, b), SMM_SIMS, SEED, keep=SMM_SIMS))["corr"]
        loss = float(sum((sim[i][j] - obs[i][j]) ** 2 for i, j in CROSS))
        rows.append({"a": a, "b": b, "loss": loss, "sim_cross": [sim[i][j] for i, j in CROSS]})
        if log:
            log(f"smm a={a} b={b} loss={loss:.5f}")
    best = min(rows, key=lambda r: r["loss"])
    return {"a": best["a"], "b": best["b"], "grid": rows, "observed_cross": [obs[i][j] for i, j in CROSS]}


def validate(ctx: dict, drives: pl.DataFrame, log=print) -> dict:
    out = {}
    g = ctx["games_fix12"].with_columns((pl.col("pts") - 6 * pl.col("td") - pl.col("pat") - 3 * pl.col("fg")
                                         - 2 * pl.col("saf")).alias("rem"))
    ok = (pl.col("rem") >= 0) & (pl.col("rem") % 2 == 0) & (pl.col("rem") <= 2 * pl.col("td"))
    out["td_reconciliation"] = float(g.select(ok.mean()).item())
    neutral = ctx["data"]["sched"].filter(pl.col("game_type") == "REG", pl.col("location") == "Neutral")["game_id"].to_list()
    out["neutral_home_flags"] = int(ctx["games_fix12"].filter(pl.col("game_id").is_in(neutral))["home"].sum())
    m3 = E5._v3_model()
    f = E.features(ctx["data"], ctx["sched"], m3["D"], m3["k"], ctx["const"])
    pit = E.point_in_time_check(ctx["data"], ctx["sched"], m3["D"], m3["k"], ctx["const"], E4._pit_sample(f))
    out["point_in_time"] = {"games": len(pit), "max_abs_diff": max(r["max_abs_diff"] for r in pit),
                            "all_same_starter": all(r["same_starter"] for r in pit)}
    d = E.design(f, ctx["rates_fix12"], ctx["games_fix12"])
    beta = E.fit_beta(E._split(d, *TRAIN))
    mu = E5.means(d, beta)
    reg = ctx["reg"]
    tr_sched = E._split(reg, *TRAIN)
    M, pool, T = fit_drive_model(drives, mu, TRAIN)
    late_trail = S.BUCKETS.index("-16..-9") * len(S.PERIODS) + S.PERIODS.index("q4_gt5")
    late_lead = S.BUCKETS.index("9..16") * len(S.PERIODS) + S.PERIODS.index("q4_gt5")
    tab = M.cell_table(float(np.log(T["mu_td"].mean())), float(np.log(T["mu_fg"].mean())))
    ob = {k: float((T.filter(pl.col("cell") == c)["outcome"] == "TD").mean()) for k, c in (("trail", late_trail), ("lead", late_lead))}
    out["drive_model"] = {"n_drives": T.height, "coef": M.coef, "se": M.se, "late_td_observed": ob,
                          "late_td_model": {"trail": float(tab[late_trail, 0]), "lead": float(tab[late_lead, 0])},
                          "pass": ob["trail"] > ob["lead"] and tab[late_trail, 0] > tab[late_lead, 0]}
    env = smm(tr_sched, mu, M, pool, log)
    out["environment"] = env
    log(f"environment factor a={env['a']} b={env['b']}")
    sims = sim_games(tr_sched, mu, M, pool, (env["a"], env["b"]), S.SIMS, SEED, keep=2000)
    ids = [i for i in sims if i in ctx["res"]]
    obs_pts = float(ctx["games_fix12"].filter(pl.col("season").is_between(*TRAIN))["pts"].mean())
    sim_pts = float(np.mean([np.mean(sims[i]["pts"]) for i in ids]))
    obs_half = T.group_by("game_id", "h").len().group_by("h").agg(pl.col("len").mean()).sort("h")["len"].to_list()
    sim_half = np.mean([sims[i]["drives_half"] for i in ids], 0).tolist()
    mo, ms = _corr_from({i: sims[i] for i in ids}, observed=True), _corr_from({i: sims[i] for i in ids})
    pm = {i: sims[i]["pmf"] for i in ids}
    pitv = E4._pit(pm, ctx["res"])
    cov = float(((pitv > 0.25) & (pitv < 0.75)).mean())
    dec = (np.histogram(pitv, bins=10, range=(0, 1))[0] / len(pitv)).tolist()
    mg = np.arange(-P.MAXP, P.MAXP + 1)
    real = np.array([ctx["res"][i] for i in ids])
    avg = np.mean([pm[i] for i in ids], 0)
    key = {k: {"observed": float((np.abs(real) == k).mean()), "simulated": float(avg[np.abs(mg) == k].sum())} for k in (3, 7)}
    out["training"] = {
        "points_per_team": {"observed": obs_pts, "simulated": sim_pts},
        "drives_per_half": {"observed": obs_half, "simulated": sim_half},
        "dispersion": {"observed": [mo["dispersion_td"], mo["dispersion_fg"]], "simulated": [ms["dispersion_td"], ms["dispersion_fg"]]},
        "corr_observed": mo["corr"], "corr_simulated": ms["corr"],
        "coverage_50": cov, "pit_deciles": dec, "key_numbers": key,
        "pass": (abs(obs_pts - sim_pts) <= 0.3 and all(abs(a - b) <= 0.3 for a, b in zip(obs_half, sim_half))
                 and abs(mo["dispersion_td"] - ms["dispersion_td"]) <= 0.05 and abs(mo["dispersion_fg"] - ms["dispersion_fg"]) <= 0.05
                 and 0.47 <= cov <= 0.53 and all(0.08 <= x <= 0.12 for x in dec)
                 and all(abs(v["observed"] - v["simulated"]) <= 0.015 for v in key.values()))}
    # out-of-sample dependence and calibration: fit on 2013-2018, check on 2019-2021
    Mh, poolh, _ = fit_drive_model(drives, mu, HOLDOUT_FIT)
    envh = smm(E._split(reg, *HOLDOUT_FIT), mu, Mh, poolh)
    hs = sim_games(E._split(reg, *HOLDOUT_CHECK), mu, Mh, poolh, (envh["a"], envh["b"]), S.SIMS, SEED, keep=2000)
    hid = [i for i in hs if i in ctx["res"]]
    ho, hsm = _corr_from({i: hs[i] for i in hid}, observed=True), _corr_from({i: hs[i] for i in hid})
    gap = float(np.max(np.abs(np.array(ho["corr"]) - np.array(hsm["corr"]))))
    hp = E4._pit({i: hs[i]["pmf"] for i in hid}, ctx["res"])
    hcov = float(((hp > 0.25) & (hp < 0.75)).mean())
    out["holdout"] = {"environment": {"a": envh["a"], "b": envh["b"]}, "corr_observed": ho["corr"], "corr_simulated": hsm["corr"],
                      "max_corr_gap": gap, "coverage_50": hcov,
                      "dependence_pass": gap <= 0.05, "calibration_pass": 0.46 <= hcov <= 0.54}
    out["pass"] = (out["td_reconciliation"] >= 0.995 and out["neutral_home_flags"] == 0
                   and out["point_in_time"]["max_abs_diff"] < E.PIT_TOL and out["point_in_time"]["all_same_starter"]
                   and out["drive_model"]["pass"] and out["training"]["pass"]
                   and out["holdout"]["dependence_pass"] and out["holdout"]["calibration_pass"])
    ctx["_v51"] = {"model": M, "pool": pool, "env": (env["a"], env["b"]), "mu": mu}
    return out


def test(ctx: dict) -> dict:
    reg = ctx["reg"]
    m3 = E5._v3_model()
    v = ctx["_v51"]
    f3 = E.features(ctx["data"], ctx["sched"], m3["D"], m3["k"], ctx["const"])
    d3 = E.design(f3, ctx["rates"], ctx["games"]); b3 = E.fit_beta(E._split(d3, *TRAIN))

    def block(lo, hi):
        s = E._split(reg, lo, hi)
        s1 = sim_games(s, v["mu"], v["model"], v["pool"], v["env"], S.SIMS, SEED)
        s2 = sim_games(s, v["mu"], v["model"], v["pool"], v["env"], S.SIMS, SEED2)
        pm = {"v51": {i: x["pmf"] for i, x in s1.items()}, "v51_seed2": {i: x["pmf"] for i, x in s2.items()},
              "v3": E.game_pmfs(E._split(d3, lo, hi), s, b3), "v1": E.game_pmfs(E._split(d3, lo, hi), s, None)}
        common = set.intersection(*(set(x) for x in pm.values()))
        g = s.filter(pl.col("result").is_not_null(), pl.col("spread_line").is_not_null(), pl.col("game_id").is_in(list(common))) \
            .select("game_id", pl.col("result").alias("margin"), (-pl.col("spread_line")).alias("close"), "total_line")
        ids = g["game_id"].to_list()
        pm = {k: {i: x[i] for i in ids} for k, x in pm.items()}
        ll = {k: E.margin_ll(x, ctx["res"]) for k, x in pm.items()}
        res = {"v51_vs_v3": E4._relabel(E.evaluate(g, pm["v51"], pm["v3"]), "v51", "v3"),
               "v51_vs_v1": E4._relabel(E.evaluate(g, pm["v51"], pm["v1"]), "v51", "v1"),
               "margin_ll": {k: E._mean_se(x) for k, x in ll.items()},
               "mc_error": float(ll["v51"].mean() - ll["v51_seed2"].mean()), "calibration": {}}
        for k in ("v51", "v3", "v1"):
            pit = E4._pit(pm[k], ctx["res"])
            res["calibration"][k] = {"coverage_50": float(((pit > 0.25) & (pit < 0.75)).mean()),
                                     "pit_deciles": (np.histogram(pit, bins=10, range=(0, 1))[0] / len(pit)).tolist()}
        return g, pm, res

    out = {}
    _, _, out["test_a"] = block(*TEST_A)
    gB, pmB, out["test_b"] = block(TEST_B, TEST_B)
    b = gB.join(cbs_opens_2025(ctx["data"]["sched"]), on="game_id", how="inner") \
        .with_columns((pl.col("cbs_open").abs() % 1 == 0.5).alias("half")).filter(pl.col("margin") != -pl.col("cbs_open"))
    hist = reg.filter(pl.col("season").is_between(1999, TEST_B - 1), pl.col("result").is_not_null(),
                      pl.col("spread_line").is_not_null(), pl.col("total_line").is_not_null())
    live = TotalDist("shifted_total").fit(-hist["spread_line"].to_numpy(), hist["result"].to_numpy(), hist["total_line"].to_numpy())
    ids, o = b["game_id"].to_list(), b["cbs_open"].to_numpy()
    y = (b["margin"].to_numpy() > -o).astype(float)
    pr = {"v51": np.array([E._cover(pmB["v51"][i], x) for i, x in zip(ids, o)]),
          "v3": np.array([E._cover(pmB["v3"][i], x) for i, x in zip(ids, o)]),
          "live": live.sf(-o, b["close"].to_numpy(), b["total_line"].to_numpy())}
    half = b["half"].to_numpy()
    out["test_b_cbs_open"] = {}
    for lab, msk in (("half_point_opens", half), ("all_opens", np.ones_like(half, bool))):
        out["test_b_cbs_open"][lab] = {
            **{m: {**E._ats(x[msk], y[msk]), "log_loss": C.log_loss(x[msk], y[msk])} for m, x in pr.items()},
            "paired_v51_vs_live": E._paired(pr["v51"][msk], pr["live"][msk], y[msk]),
            "paired_v51_vs_v3": E._paired(pr["v51"][msk], pr["v3"][msk], y[msk])}
    return out


def run(cache=None, log=print) -> dict:
    ctx = E4.prepare(cache, log)
    drives = E5.load_drives(cache)
    va = validate(ctx, drives, log)
    log("VALIDATION " + json.dumps({k: v for k, v in va.items() if k not in ("drive_model", "environment")}, default=str)[:4000])
    if not va["pass"]:
        return {"validation": va, "scored": False, "stop_rule": "triggered: projection-distribution track stops"}
    return {"validation": va, "test": test(ctx), "scored": True,
            "frozen": {"model": ctx["_v51"]["model"].to_json(), "pool": ctx["_v51"]["pool"].to_json(),
                       "env": ctx["_v51"]["env"]}}
