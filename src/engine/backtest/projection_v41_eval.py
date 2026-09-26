"""Evaluation of proj-latent-v41 (docs/projection_v41_preregistration.md).

Order: data-fix and point-in-time checks -> ML fit of the latent distribution on 2013-2021 -> dependence,
calibration and internal-holdout checks -> (only if all pass) informed test on 2022-2025 with the ablation.
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
from engine.features import players_v3 as V
from engine.models import projection as P
from engine.models import projection_v41 as L
from engine.models.margin_dist import TotalDist

TRAIN, TEST_A, TEST_B = E.TRAIN, E.TEST_A, E.TEST_B
HOLDOUT_FIT, HOLDOUT_CHECK = (2013, 2018), (2019, 2021)
N_TD_GRID = ("max+1", 12, 15, 20, 30, None)
N_FG_GRID = ("max+1", 12, 20, None)


def _v3_model() -> dict:
    return json.loads(Path(E.__file__).resolve().parents[3].joinpath("data/processed/players_v3_model.json").read_text())


def game_matrix(d: pl.DataFrame, beta: dict, sched: pl.DataFrame) -> pl.DataFrame:
    """One row per game (listed home/away from the schedule): expected and observed TD/FG for both teams."""
    rows = {(r["game_id"], r["team"]): r for r in d.iter_rows(named=True)}
    out = []
    for g in sched.select("game_id", "season", pl.col("home_team").replace(P.FRANCHISE).alias("h"),
                          pl.col("away_team").replace(P.FRANCHISE).alias("a")).iter_rows(named=True):
        rh, ra = rows.get((g["game_id"], g["h"])), rows.get((g["game_id"], g["a"]))
        if rh is None or ra is None or rh.get("td") is None or ra.get("td") is None:
            continue
        out.append({"game_id": g["game_id"], "season": g["season"], "p_xp": rh["p_xp"], "p_2": rh["p_2"],
                    "mu_td_h": E._adj(rh, beta, "td"), "mu_fg_h": E._adj(rh, beta, "fg"),
                    "mu_td_a": E._adj(ra, beta, "td"), "mu_fg_a": E._adj(ra, beta, "fg"),
                    "td_h": rh["td"], "fg_h": rh["fg"], "td_a": ra["td"], "fg_a": ra["fg"]})
    return pl.DataFrame(out)


def _mu_y(gm: pl.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    return (gm.select("mu_td_h", "mu_fg_h", "mu_td_a", "mu_fg_a").to_numpy().astype(float),
            gm.select("td_h", "fg_h", "td_a", "fg_a").to_numpy().astype(float))


def _grid(values, observed_max):
    return [observed_max + 1 if v == "max+1" else v for v in values if v is None or v == "max+1" or v > observed_max]


def fit_latent(gm: pl.DataFrame, log=print) -> dict:
    mu, y = _mu_y(gm)
    mt, mf = int(max(y[:, 0].max(), y[:, 2].max())), int(max(y[:, 1].max(), y[:, 3].max()))
    return L.fit(mu, y, _grid(N_TD_GRID, mt), _grid(N_FG_GRID, mf), log)


def pmfs(gm: pl.DataFrame, p: L.Params) -> dict:
    return {r["game_id"]: L.project((r["mu_td_h"], r["mu_fg_h"], r["mu_td_a"], r["mu_fg_a"]), r["p_xp"], r["p_2"], p).margin_pmf
            for r in gm.iter_rows(named=True)}


def _coverage(pm: dict, res: dict) -> tuple[float, list]:
    pit = E4._pit(pm, res)
    return float(((pit > 0.25) & (pit < 0.75)).mean()), (np.histogram(pit, bins=10, range=(0, 1))[0] / len(pit)).tolist()


def _moments(mu: np.ndarray, counts: np.ndarray) -> dict:
    """Residual correlation matrix and dispersions. counts: (G, 4) or (draws, G, 4)."""
    r = (counts - mu).reshape(-1, 4)
    m = np.broadcast_to(mu, counts.shape).reshape(-1, 4)
    disp = ((r ** 2) / m).mean(0)
    return {"corr": np.corrcoef(r.T).round(4).tolist(),
            "dispersion_td": float((disp[0] + disp[2]) / 2), "dispersion_fg": float((disp[1] + disp[3]) / 2)}


def validate(ctx: dict, log=print) -> dict:
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
    reg = ctx["reg"]
    gm = game_matrix(E._split(d, *TRAIN), beta, E._split(reg, *TRAIN))
    fit = fit_latent(gm, log)
    p = fit["params"]
    mu, y = _mu_y(gm)
    obs, imp = _moments(mu, y), _moments(mu, L.simulate(p, mu, 200, 20260927))
    diff = float(np.max(np.abs(np.array(obs["corr"]) - np.array(imp["corr"]))))
    out["latent_fit"] = {"params": p.to_json(), "se": fit["se"], "cap_share": fit["cap_share"], "table": fit["table"],
                         "n_games": gm.height}
    out["dependence"] = {"observed": obs, "implied": imp, "max_corr_diff": diff,
                         "pass": diff <= 0.05 and abs(obs["dispersion_td"] - imp["dispersion_td"]) <= 0.05
                         and abs(obs["dispersion_fg"] - imp["dispersion_fg"]) <= 0.05}
    cov, dec = _coverage(pmfs(gm, p), ctx["res"])
    out["calibration_train"] = {"coverage_50": cov, "pit_deciles": dec,
                                "pass": 0.47 <= cov <= 0.53 and all(0.08 <= x <= 0.12 for x in dec)}
    gfit = gm.filter(pl.col("season").is_between(*HOLDOUT_FIT))
    gchk = gm.filter(pl.col("season").is_between(*HOLDOUT_CHECK))
    hp = fit_latent(gfit, None)["params"]
    hcov, hdec = _coverage(pmfs(gchk, hp), ctx["res"])
    out["internal_holdout"] = {"params": hp.to_json(), "coverage_50": hcov, "pit_deciles": hdec, "pass": 0.46 <= hcov <= 0.54}
    out["pass"] = (out["td_reconciliation"] >= 0.995 and out["neutral_home_flags"] == 0
                   and out["point_in_time"]["max_abs_diff"] < E.PIT_TOL and out["point_in_time"]["all_same_starter"]
                   and out["dependence"]["pass"] and out["calibration_train"]["pass"] and out["internal_holdout"]["pass"])
    ctx["_v41"] = {"params": p, "d12": d, "beta12": beta}
    return out


def test(ctx: dict) -> dict:
    """Informed test on 2022-2025: v4.1 vs v3 (as specified) and v1, with the ablation."""
    reg = ctx["reg"]
    m3 = _v3_model()
    p, d12, b12 = ctx["_v41"]["params"], ctx["_v41"]["d12"], ctx["_v41"]["beta12"]
    f3 = E.features(ctx["data"], ctx["sched"], m3["D"], m3["k"], ctx["const"])
    d3 = E.design(f3, ctx["rates"], ctx["games"]); b3 = E.fit_beta(E._split(d3, *TRAIN))
    d1 = E.design(f3, ctx["rates_fix1"], ctx["games_fix1"]); b1 = E.fit_beta(E._split(d1, *TRAIN))

    def block(lo, hi):
        s = E._split(reg, lo, hi)
        pm = {"v41": pmfs(game_matrix(E._split(d12, lo, hi), b12, s), p),
              "v3": E.game_pmfs(E._split(d3, lo, hi), s, b3),
              "v1": E.game_pmfs(E._split(d3, lo, hi), s, None),
              "fix1": E.game_pmfs(E._split(d1, lo, hi), s, b1),
              "fix12": E.game_pmfs(E._split(d12, lo, hi), s, b12)}
        common = set.intersection(*(set(v) for v in pm.values()))
        g = s.filter(pl.col("result").is_not_null(), pl.col("spread_line").is_not_null(),
                     pl.col("game_id").is_in(list(common))).select(
            "game_id", pl.col("result").alias("margin"), (-pl.col("spread_line")).alias("close"), "total_line")
        ids = g["game_id"].to_list()
        pm = {k: {i: v[i] for i in ids} for k, v in pm.items()}
        res = {"v41_vs_v3": E4._relabel(E.evaluate(g, pm["v41"], pm["v3"]), "v41", "v3"),
               "v41_vs_v1": E4._relabel(E.evaluate(g, pm["v41"], pm["v1"]), "v41", "v1"),
               "ablation_margin_ll": {k: E._mean_se(E.margin_ll(v, ctx["res"])) for k, v in pm.items()},
               "calibration": {k: dict(zip(("coverage_50", "pit_deciles"), _coverage(v, ctx["res"]))) for k, v in pm.items()}}
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
    pr = {"v41": np.array([E._cover(pmB["v41"][i], x) for i, x in zip(ids, o)]),
          "v3": np.array([E._cover(pmB["v3"][i], x) for i, x in zip(ids, o)]),
          "live": live.sf(-o, b["close"].to_numpy(), b["total_line"].to_numpy())}
    half = b["half"].to_numpy()
    out["test_b_cbs_open"] = {}
    for lab, msk in (("half_point_opens", half), ("all_opens", np.ones_like(half, bool))):
        out["test_b_cbs_open"][lab] = {
            **{m: {**E._ats(v[msk], y[msk]), "log_loss": C.log_loss(v[msk], y[msk])} for m, v in pr.items()},
            "paired_v41_vs_live": E._paired(pr["v41"][msk], pr["live"][msk], y[msk]),
            "paired_v41_vs_v3": E._paired(pr["v41"][msk], pr["v3"][msk], y[msk])}
    out["beta"] = [{"feature": f, "td_b": float(b12["td"]["b"][i + 1]), "td_se": float(b12["td"]["se"][i + 1]),
                    "fg_b": float(b12["fg"]["b"][i + 1]), "fg_se": float(b12["fg"]["se"][i + 1])}
                   for i, f in enumerate(V.FEATURES)]
    return out


def run(cache: str | None = None, log=print) -> dict:
    ctx = E4.prepare(cache, log)
    va = validate(ctx, log)
    log("VALIDATION " + json.dumps({k: (v if k not in ("latent_fit",) else {kk: vv for kk, vv in v.items() if kk != "table"})
                                    for k, v in va.items()}, default=str)[:4000])
    if not va["pass"]:
        return {"validation": va, "scored": False}
    return {"validation": va, "test": test(ctx), "scored": True}
