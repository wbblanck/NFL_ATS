"""Evaluation of proj-sim-v5 (docs/projection_v5_preregistration.md).

Order: data checks -> drive model fit (2013-2021) -> simulation checks on training -> internal holdout ->
(only if all pass) informed test on 2022-2025.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from engine.backtest import calibration as C
from engine.backtest import players_v3_eval as E
from engine.backtest import projection_v4_eval as E4
from engine.backtest.holdout2025 import cbs_opens_2025
from engine.models import projection as P
from engine.models import projection_v5 as S5
from engine.models.margin_dist import TotalDist

TRAIN, TEST_A, TEST_B = E.TRAIN, E.TEST_A, E.TEST_B
HOLDOUT_FIT, HOLDOUT_CHECK = (2013, 2018), (2019, 2021)
SEED, SEED2 = 1, 2


def _v3_model() -> dict:
    return json.loads(Path(E.__file__).resolve().parents[3].joinpath("data/processed/players_v3_model.json").read_text())


def load_drives(cache: str | None) -> pl.DataFrame:
    import nflreadpy as nfl
    cp = Path(cache) if cache else None
    if cp and (cp / "drive_rows_v2.parquet").exists():
        return pl.read_parquet(cp / "drive_rows_v2.parquet")
    parts = []
    for s in range(TRAIN[0], TEST_B + 1):
        d = nfl.load_pbp(seasons=[s]).filter(pl.col("season_type") == "REG", pl.col("posteam").is_not_null(),
                                             pl.col("fixed_drive").is_not_null())
        # One row per (game, drive). Grouping by possession team would split every defensive-TD drive in two: the
        # extra point after a return TD has the scoring team as posteam (found in validation; see the report).
        parts.append(d.sort("game_id", "play_id").group_by("game_id", "season", "fixed_drive", maintain_order=True).agg(
            pl.col("posteam").first(), pl.col("defteam").first(),
            pl.col("score_differential").drop_nulls().first().alias("diff"),
            pl.col("half_seconds_remaining").first().alias("hs0"), pl.col("half_seconds_remaining").last().alias("hs1"),
            pl.col("game_half").first().alias("half"), pl.col("qtr").first().alias("qtr"),
            pl.col("fixed_drive_result").first().alias("res")))
    out = pl.concat(parts)
    if cp:
        out.write_parquet(cp / "drive_rows_v2.parquet")
    return out


def means(d: pl.DataFrame, beta: dict) -> pl.DataFrame:
    return pl.DataFrame([{"game_id": r["game_id"], "team": r["team"], "mu_td": E._adj(r, beta, "td"),
                          "mu_fg": E._adj(r, beta, "fg"), "p_xp": r["p_xp"], "p_2": r["p_2"], "td": r.get("td"),
                          "fg": r.get("fg")} for r in d.iter_rows(named=True)])


def fit_drive_model(drives: pl.DataFrame, mu: pl.DataFrame, seasons) -> tuple[S5.DriveModel, S5.DurationPool, pl.DataFrame]:
    T = S5.drive_training_table(drives.filter(pl.col("season").is_between(*seasons)), mu.select("game_id", "team", "mu_td", "mu_fg"))
    M = S5.DriveModel.fit(np.log(T["mu_td"].to_numpy()), np.log(T["mu_fg"].to_numpy()), T["cell"].to_numpy(), T["outcome"].to_numpy())
    ok = T.filter("dur_ok")
    pool = S5.DurationPool.fit(ok["outcome"].to_list(), ok["cell"].to_numpy(), ok["dur"].to_numpy())
    return M, pool, T


def simulate_games(sched: pl.DataFrame, mu: pl.DataFrame, M, pool, seed: int, keep_counts=False) -> dict:
    rows = {(r["game_id"], r["team"]): r for r in mu.iter_rows(named=True)}
    out = {}
    for g in sched.select("game_id", pl.col("home_team").replace(P.FRANCHISE).alias("h"),
                          pl.col("away_team").replace(P.FRANCHISE).alias("a")).iter_rows(named=True):
        rh, ra = rows.get((g["game_id"], g["h"])), rows.get((g["game_id"], g["a"]))
        if rh is None or ra is None:
            continue
        r = S5.simulate({"td": rh["mu_td"], "fg": rh["mu_fg"]}, {"td": ra["mu_td"], "fg": ra["mu_fg"]},
                        rh["p_xp"], rh["p_2"], M, pool, seed=seed)
        out[g["game_id"]] = {"pmf": S5.margin_pmf(r), "counts_mean": r.counts.mean(0),
                             "pts": (float(r.home_pts.mean()), float(r.away_pts.mean())),
                             "counts": r.counts[:2000] if keep_counts else None,
                             "mu": (rh["mu_td"], rh["mu_fg"], ra["mu_td"], ra["mu_fg"]),
                             "obs": (rh["td"], rh["fg"], ra["td"], ra["fg"])}
    return out


def validate(ctx: dict, drives: pl.DataFrame, log=print) -> dict:
    out = {}
    g = ctx["games_fix12"].with_columns((pl.col("pts") - 6 * pl.col("td") - pl.col("pat") - 3 * pl.col("fg")
                                         - 2 * pl.col("saf")).alias("rem"))
    ok = (pl.col("rem") >= 0) & (pl.col("rem") % 2 == 0) & (pl.col("rem") <= 2 * pl.col("td"))
    out["td_reconciliation"] = float(g.select(ok.mean()).item())
    neutral = ctx["data"]["sched"].filter(pl.col("game_type") == "REG", pl.col("location") == "Neutral")["game_id"].to_list()
    out["neutral_home_flags"] = int(ctx["games_fix12"].filter(pl.col("game_id").is_in(neutral))["home"].sum())
    m3 = _v3_model()
    f = E.features(ctx["data"], ctx["sched"], m3["D"], m3["k"], ctx["const"])
    pit = E.point_in_time_check(ctx["data"], ctx["sched"], m3["D"], m3["k"], ctx["const"], E4._pit_sample(f))
    out["point_in_time"] = {"games": len(pit), "max_abs_diff": max(r["max_abs_diff"] for r in pit),
                            "all_same_starter": all(r["same_starter"] for r in pit)}
    d = E.design(f, ctx["rates_fix12"], ctx["games_fix12"])
    beta = E.fit_beta(E._split(d, *TRAIN))
    mu = means(d, beta)
    M, pool, T = fit_drive_model(drives, mu, TRAIN)
    log(f"drive model fit on {T.height} drives; durations kept {T['dur_ok'].mean():.4f}")
    # 2. drive-model sanity: trailing late has a higher TD share than leading late, in data and model
    late = [S5.BUCKETS.index(b) * len(S5.PERIODS) + S5.PERIODS.index("late") for b in ("trail9", "lead9")]
    obs_late = {b: float((T.filter(pl.col("cell") == c)["outcome"] == "TD").mean()) for b, c in zip(("trail9", "lead9"), late)}
    tab = M.cell_table(float(np.log(T["mu_td"].mean())), float(np.log(T["mu_fg"].mean())))
    mod_late = {b: float(tab[c, 0]) for b, c in zip(("trail9", "lead9"), late)}
    out["drive_model"] = {"n_drives": T.height, "coef": M.coef, "se": M.se, "late_td_observed": obs_late,
                          "late_td_model": mod_late, "durations_kept": float(T["dur_ok"].mean()),
                          "pass": obs_late["trail9"] > obs_late["lead9"] and mod_late["trail9"] > mod_late["lead9"]}
    # 3-4. simulation vs training
    sims = simulate_games(E._split(ctx["reg"], *TRAIN), mu, M, pool, SEED, keep_counts=True)
    res = ctx["res"]
    ids = [i for i in sims if i in res]
    obs_pts = ctx["games_fix12"].filter(pl.col("season").is_between(*TRAIN))["pts"].mean()
    sim_pts = float(np.mean([np.mean(sims[i]["pts"]) for i in ids]))
    mu_arr = np.array([sims[i]["mu"] for i in ids], float)
    obs_arr = np.array([sims[i]["obs"] for i in ids], float)
    sim_arr = np.stack([sims[i]["counts"] for i in ids], 1).astype(float)       # (draws, G, 4)
    o_m, s_m = E4_moments(mu_arr, obs_arr), E4_moments(mu_arr, sim_arr)
    diff = float(np.max(np.abs(np.array(o_m["corr"]) - np.array(s_m["corr"]))))
    out["simulation_vs_training"] = {
        "points_per_team": {"observed": float(obs_pts), "simulated": sim_pts},
        "observed": o_m, "simulated": s_m, "max_corr_diff": diff,
        "pass": abs(obs_pts - sim_pts) <= 0.3 and diff <= 0.05
        and abs(o_m["dispersion_td"] - s_m["dispersion_td"]) <= 0.05 and abs(o_m["dispersion_fg"] - s_m["dispersion_fg"]) <= 0.05}
    pm = {i: sims[i]["pmf"] for i in ids}
    pitv = E4._pit(pm, res)
    cov = float(((pitv > 0.25) & (pitv < 0.75)).mean())
    dec = (np.histogram(pitv, bins=10, range=(0, 1))[0] / len(pitv)).tolist()
    out["calibration_train"] = {"coverage_50": cov, "pit_deciles": dec,
                                "pass": 0.47 <= cov <= 0.53 and all(0.08 <= x <= 0.12 for x in dec)}
    mg = np.arange(-P.MAXP, P.MAXP + 1)
    real = np.array([res[i] for i in ids])
    avg = np.mean([pm[i] for i in ids], 0)
    key = {k: {"observed": float((np.abs(real) == k).mean()), "simulated": float(avg[np.abs(mg) == k].sum())} for k in (3, 7)}
    out["key_numbers"] = {**{str(k): v for k, v in key.items()},
                          "pass": all(abs(v["observed"] - v["simulated"]) <= 0.015 for v in key.values())}
    # 5. internal holdout
    Mh, poolh, _ = fit_drive_model(drives, mu, HOLDOUT_FIT)
    hs = simulate_games(E._split(ctx["reg"], *HOLDOUT_CHECK), mu, Mh, poolh, SEED)
    hp = E4._pit({i: v["pmf"] for i, v in hs.items()}, res)
    hcov = float(((hp > 0.25) & (hp < 0.75)).mean())
    out["internal_holdout"] = {"coverage_50": hcov, "pass": 0.46 <= hcov <= 0.54}
    out["pass"] = (out["td_reconciliation"] >= 0.995 and out["neutral_home_flags"] == 0
                   and out["point_in_time"]["max_abs_diff"] < E.PIT_TOL and out["point_in_time"]["all_same_starter"]
                   and out["drive_model"]["pass"] and out["simulation_vs_training"]["pass"]
                   and out["calibration_train"]["pass"] and out["key_numbers"]["pass"] and out["internal_holdout"]["pass"])
    ctx["_v5"] = {"model": M, "pool": pool, "d12": d, "beta12": beta, "mu": mu}
    return out


def E4_moments(mu: np.ndarray, counts: np.ndarray) -> dict:
    r = (counts - mu).reshape(-1, 4)
    m = np.broadcast_to(mu, counts.shape).reshape(-1, 4)
    disp = ((r ** 2) / m).mean(0)
    return {"corr": np.corrcoef(r.T).round(4).tolist(), "dispersion_td": float((disp[0] + disp[2]) / 2),
            "dispersion_fg": float((disp[1] + disp[3]) / 2)}


def test(ctx: dict) -> dict:
    reg = ctx["reg"]
    m3 = _v3_model()
    v5 = ctx["_v5"]
    f3 = E.features(ctx["data"], ctx["sched"], m3["D"], m3["k"], ctx["const"])
    d3 = E.design(f3, ctx["rates"], ctx["games"]); b3 = E.fit_beta(E._split(d3, *TRAIN))

    def block(lo, hi):
        s = E._split(reg, lo, hi)
        sim1 = simulate_games(s, v5["mu"], v5["model"], v5["pool"], SEED)
        sim2 = simulate_games(s, v5["mu"], v5["model"], v5["pool"], SEED2)
        pm = {"v5": {i: v["pmf"] for i, v in sim1.items()}, "v5_seed2": {i: v["pmf"] for i, v in sim2.items()},
              "v3": E.game_pmfs(E._split(d3, lo, hi), s, b3), "v1": E.game_pmfs(E._split(d3, lo, hi), s, None)}
        common = set.intersection(*(set(v) for v in pm.values()))
        g = s.filter(pl.col("result").is_not_null(), pl.col("spread_line").is_not_null(),
                     pl.col("game_id").is_in(list(common))).select(
            "game_id", pl.col("result").alias("margin"), (-pl.col("spread_line")).alias("close"), "total_line")
        ids = g["game_id"].to_list()
        pm = {k: {i: v[i] for i in ids} for k, v in pm.items()}
        ll = {k: E.margin_ll(v, ctx["res"]) for k, v in pm.items()}
        res = {"v5_vs_v3": E4._relabel(E.evaluate(g, pm["v5"], pm["v3"]), "v5", "v3"),
               "v5_vs_v1": E4._relabel(E.evaluate(g, pm["v5"], pm["v1"]), "v5", "v1"),
               "margin_ll": {k: E._mean_se(v) for k, v in ll.items()},
               "mc_error": {"seed1_minus_seed2": float(ll["v5"].mean() - ll["v5_seed2"].mean())},
               "calibration": {}}
        for k in ("v5", "v3", "v1"):
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
    pr = {"v5": np.array([E._cover(pmB["v5"][i], x) for i, x in zip(ids, o)]),
          "v3": np.array([E._cover(pmB["v3"][i], x) for i, x in zip(ids, o)]),
          "live": live.sf(-o, b["close"].to_numpy(), b["total_line"].to_numpy())}
    half = b["half"].to_numpy()
    out["test_b_cbs_open"] = {}
    for lab, msk in (("half_point_opens", half), ("all_opens", np.ones_like(half, bool))):
        out["test_b_cbs_open"][lab] = {
            **{m: {**E._ats(v[msk], y[msk]), "log_loss": C.log_loss(v[msk], y[msk])} for m, v in pr.items()},
            "paired_v5_vs_live": E._paired(pr["v5"][msk], pr["live"][msk], y[msk]),
            "paired_v5_vs_v3": E._paired(pr["v5"][msk], pr["v3"][msk], y[msk])}
    return out


def run(cache: str | None = None, log=print) -> dict:
    ctx = E4.prepare(cache, log)
    drives = load_drives(cache)
    va = validate(ctx, drives, log)
    log("VALIDATION " + json.dumps({k: v for k, v in va.items() if k != "drive_model"}, default=str)[:4000])
    if not va["pass"]:
        return {"validation": va, "scored": False}
    return {"validation": va, "test": test(ctx), "scored": True,
            "frozen": {"model": ctx["_v5"]["model"].to_json(), "pool": ctx["_v5"]["pool"].to_json()}}
