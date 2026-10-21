"""Evaluation of proj-drives-v4 (docs/projection_v4_preregistration.md).

Stages, in the pre-registered order: validation checks (training seasons only) -> tuning -> informed test on
2022-2025 with the ablation. Test seasons are scored only if every validation check passes.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np
import polars as pl

from engine.backtest import calibration as C
from engine.backtest import players_v3_eval as E
from engine.backtest.holdout2025 import cbs_opens_2025
from engine.backtest.players_eval import v1_rates
from engine.features import players_v3 as V
from engine.models import projection as P
from engine.models import projection_v4 as V4
from engine.models.margin_dist import TotalDist

TRAIN, TEST_A, TEST_B = E.TRAIN, E.TEST_A, E.TEST_B
MG = E.MG


# ---------------------------------------------------------------- data

def load_extra(cache: str | None) -> dict:
    """Play-by-play TD counts and drive counts per team-game, 1999-2025 (REG)."""
    import nflreadpy as nfl
    cp = Path(cache) if cache else None
    if cp and (cp / "td_pbp.parquet").exists() and (cp / "drives.parquet").exists():
        return {"td_pbp": pl.read_parquet(cp / "td_pbp.parquet"), "drives": pl.read_parquet(cp / "drives.parquet")}
    tds, drv = [], []
    for s in range(1999, TEST_B + 1):
        d = nfl.load_pbp(seasons=[s]).filter(pl.col("season_type") == "REG")
        tds.append(d.filter(pl.col("touchdown") == 1, pl.col("td_team").is_not_null())
                   .group_by("game_id", "season", "week", "td_team").agg(pl.len().alias("td_pbp")))
        drv.append(d.filter(pl.col("posteam").is_not_null(), pl.col("fixed_drive").is_not_null())
                   .group_by("game_id", "season", "posteam").agg(pl.col("fixed_drive").n_unique().alias("drives")))
    out = {"td_pbp": pl.concat(tds), "drives": pl.concat(drv)}
    if cp:
        out["td_pbp"].write_parquet(cp / "td_pbp.parquet"); out["drives"].write_parquet(cp / "drives.parquet")
    return out


def prepare(cache: str | None = None, log=print) -> dict:
    base = E.prepare(cache, log)                         # v3 context: data, sched, reg, res, const, games, rates
    extra = load_extra(cache)
    sched_all = base["data"]["sched"]
    g1 = V4.team_games(base["data"]["team_stats"], sched_all, extra["td_pbp"], neutral_fix=False)
    g12 = V4.team_games(base["data"]["team_stats"], sched_all, extra["td_pbp"], neutral_fix=True)
    tgt = lambda g: g.filter(pl.col("season").is_between(TRAIN[0], TEST_B))  # noqa: E731
    r1, r12 = v1_rates(g1, tgt(g1)), v1_rates(g12, tgt(g12))
    log(f"v1 rates recomputed: fix1 {r1.height}, fix1+2 {r12.height}")
    dt = V4.drive_table(extra["drives"], sched_all)
    return {**base, **extra, "games_fix1": g1, "games_fix12": g12, "rates_fix1": r1, "rates_fix12": r12,
            "drive_table": dt, "drive_dist": V4.DriveDist.fit(dt.filter(pl.col("season").is_between(*TRAIN)))}


# ---------------------------------------------------------------- projections

def _mu(r: dict, beta: dict, k: str) -> float:
    return E._adj(r, beta, k)


def pmfs_v4(d: pl.DataFrame, sched: pl.DataFrame, beta: dict, dd: V4.DriveDist) -> dict:
    rows = {(r["game_id"], r["team"]): r for r in d.iter_rows(named=True)}
    out = {}
    for g in sched.select("game_id", pl.col("home_team").replace(P.FRANCHISE).alias("h"),
                          pl.col("away_team").replace(P.FRANCHISE).alias("a")).iter_rows(named=True):
        rh, ra = rows.get((g["game_id"], g["h"])), rows.get((g["game_id"], g["a"]))
        if rh is None or ra is None:
            continue
        pr = V4.project({"td": _mu(rh, beta, "td"), "fg": _mu(rh, beta, "fg")},
                        {"td": _mu(ra, beta, "td"), "fg": _mu(ra, beta, "fg")}, rh["p_xp"], rh["p_2"], dd)
        out[g["game_id"]] = pr.margin_pmf
    return out


def _pit(pm: dict, res: dict) -> np.ndarray:
    out = []
    for g, p in pm.items():
        if g not in res:
            continue
        i = int(res[g]) + P.MAXP
        out.append(float(p[:i].sum() + 0.5 * p[i]))
    return np.array(out)


def _residual_stats(d: pl.DataFrame, beta: dict, games: pl.DataFrame) -> dict:
    """Pearson dispersion of TD/FG and cross-team TD residual correlation under the fitted means."""
    x = d.join(games.select("game_id", "team", "home"), on=["game_id", "team"], how="left")
    mu = {k: np.array([_mu(r, beta, k) for r in x.iter_rows(named=True)]) for k in ("td", "fg")}
    x = x.with_columns(pl.Series("mu_td", mu["td"]), pl.Series("mu_fg", mu["fg"]))
    disp = {k: float((((x[k] - x[f"mu_{k}"]) ** 2) / x[f"mu_{k}"]).mean()) for k in ("td", "fg")}
    r = x.with_columns((pl.col("td") - pl.col("mu_td")).alias("r")).select("game_id", "team", "r", "mu_td", "mu_fg")
    pairs = r.join(r, on="game_id", suffix="_o").filter(pl.col("team") < pl.col("team_o"))
    return {"dispersion_td": disp["td"], "dispersion_fg": disp["fg"],
            "cross_team_td_corr": float(np.corrcoef(pairs["r"], pairs["r_o"])[0, 1]), "n_games": pairs.height, "x": x}


def _drive_implied(x: pl.DataFrame, dd: V4.DriveDist) -> dict:
    """Implied TD/FG dispersion and cross-team TD correlation under the drive model, averaged over games."""
    eh, ea = dd.mean
    en = (eh + ea) / 2
    n = np.r_[dd.pairs[:, 0], dd.pairs[:, 1]]
    w = np.r_[dd.probs, dd.probs] / 2
    vn = float(w @ (n - en) ** 2)
    cov_n = float(dd.probs @ ((dd.pairs[:, 0] - eh) * (dd.pairs[:, 1] - ea)))
    out = {}
    for k in ("td", "fg"):
        p = x[f"mu_{k}"].to_numpy() / en
        var = en * p * (1 - p) + p ** 2 * vn
        out[f"dispersion_{k}"] = float(np.mean(var / x[f"mu_{k}"].to_numpy()))
    x2 = x.select("game_id", "team", "mu_td")
    pr = x2.join(x2, on="game_id", suffix="_o").filter(pl.col("team") < pl.col("team_o"))
    ph, pa = pr["mu_td"].to_numpy() / en, pr["mu_td_o"].to_numpy() / en
    var_h = en * ph * (1 - ph) + ph ** 2 * vn
    var_a = en * pa * (1 - pa) + pa ** 2 * vn
    out["cross_team_td_corr"] = float(np.mean(ph * pa * cov_n / np.sqrt(var_h * var_a)))
    return out


# ---------------------------------------------------------------- stages

def validate(ctx: dict, log=print) -> dict:
    """Stage 1: the pre-registered checks, using training seasons only (plus data-integrity checks)."""
    out = {}
    g = ctx["games_fix12"].with_columns((pl.col("pts") - 6 * pl.col("td") - pl.col("pat") - 3 * pl.col("fg")
                                         - 2 * pl.col("saf")).alias("rem"))
    ok = (pl.col("rem") >= 0) & (pl.col("rem") % 2 == 0) & (pl.col("rem") <= 2 * pl.col("td"))
    bad = g.filter(~ok)
    out["td_reconciliation"] = {"team_games": g.height, "reconciled": float(g.select(ok.mean()).item()),
                                "exceptions": bad.select("game_id", "team", "pts", "td", "pat", "fg", "saf", "rem").to_dicts()[:25],
                                "n_exceptions": bad.height}
    old = ctx["games"].with_columns((pl.col("pts") - 6 * pl.col("td") - pl.col("pat") - 3 * pl.col("fg")
                                     - 2 * pl.col("saf")).alias("rem"))
    out["td_reconciliation"]["team_stats_reconciled"] = float(old.select(ok.mean()).item())
    s = ctx["data"]["sched"].filter(pl.col("game_type") == "REG", pl.col("location") == "Neutral",
                                    pl.col("home_score").is_not_null())
    neutral_ids = s["game_id"].to_list()
    out["neutral"] = {"per_season": dict(zip(*s.group_by("season").len().sort("season").to_dict(as_series=False).values())),
                      "any_home_flag": int(ctx["games_fix12"].filter(pl.col("game_id").is_in(neutral_ids))["home"].sum())}
    # problems exist in training: Poisson (v3-style) with fixes 1-2, D/k as v3's frozen choice
    m3 = json.loads(Path(E.__file__).resolve().parents[3].joinpath("data/processed/players_v3_model.json").read_text())
    f = E.features(ctx["data"], ctx["sched"], m3["D"], m3["k"], ctx["const"])
    d = E.design(f, ctx["rates_fix12"], ctx["games_fix12"])
    tr = E._split(d, *TRAIN)
    beta = E.fit_beta(tr)
    st = _residual_stats(tr, beta, ctx["games_fix12"])
    treg = E._split(ctx["reg"], *TRAIN)
    pit_p = _pit(E.game_pmfs(tr, treg, beta), ctx["res"])
    cov_p = float(((pit_p > 0.25) & (pit_p < 0.75)).mean())
    out["problems_in_training"] = {"dispersion_td": st["dispersion_td"], "dispersion_fg": st["dispersion_fg"],
                                   "cross_team_td_corr": st["cross_team_td_corr"], "coverage_50": cov_p,
                                   "exists": st["dispersion_td"] < 0.95 or st["cross_team_td_corr"] > 0.05 or cov_p > 0.55}
    dd = ctx["drive_dist"]
    imp = _drive_implied(st["x"], dd)
    pit_4 = _pit(pmfs_v4(tr, treg, beta, dd), ctx["res"])
    cov_4 = float(((pit_4 > 0.25) & (pit_4 < 0.75)).mean())
    out["drive_model_fit"] = {**{f"implied_{k}": v for k, v in imp.items()},
                              **{f"observed_{k}": st[k] for k in ("dispersion_td", "dispersion_fg", "cross_team_td_corr")},
                              "coverage_50": cov_4, "pit_deciles": (np.histogram(pit_4, bins=10, range=(0, 1))[0] / len(pit_4)).tolist(),
                              "poisson_pit_deciles": (np.histogram(pit_p, bins=10, range=(0, 1))[0] / len(pit_p)).tolist(),
                              "drive_mean": dd.mean, "drive_games": int(E._split(ctx["drive_table"], *TRAIN).height),
                              "pass": 0.46 <= cov_4 <= 0.54 and abs(imp["cross_team_td_corr"] - st["cross_team_td_corr"]) <= 0.07}
    drv = ctx["drive_table"]
    out["drives_by_season"] = drv.group_by("season").agg(((pl.col("n_h") + pl.col("n_a")) / 2).mean().alias("drives")) \
        .sort("season").to_dicts()
    pit = E.point_in_time_check(ctx["data"], ctx["sched"], m3["D"], m3["k"], ctx["const"],
                                _pit_sample(f))
    out["point_in_time"] = {"games": len(pit), "max_abs_diff": max(r["max_abs_diff"] for r in pit),
                            "all_same_starter": all(r["same_starter"] for r in pit)}
    out["pass"] = (out["td_reconciliation"]["reconciled"] >= 0.995 and out["neutral"]["any_home_flag"] == 0
                   and out["drive_model_fit"]["pass"] and out["point_in_time"]["max_abs_diff"] < E.PIT_TOL
                   and out["point_in_time"]["all_same_starter"])
    out["fix3_kept"] = out["problems_in_training"]["exists"]
    return out


def _pit_sample(f: pl.DataFrame) -> list[str]:
    rng = np.random.default_rng(20260927)
    ids = []
    for s in range(TRAIN[0], TEST_B + 1):
        g = sorted(set(f.filter(pl.col("season") == s)["game_id"].to_list()))
        ids.append(g[int(rng.integers(len(g)))])
    return ids


def tune(ctx: dict, log=print) -> dict:
    """Stage 2: D, k by training margin log-likelihood under v4 (fixes 1-3)."""
    rows = []
    for D, k in itertools.product(E.GRID_D, E.GRID_K):
        d = E.design(E.features(ctx["data"], ctx["sched"], D, k, ctx["const"]), ctx["rates_fix12"], ctx["games_fix12"])
        tr = E._split(d, *TRAIN)
        ll = E.margin_ll(pmfs_v4(tr, E._split(ctx["reg"], *TRAIN), E.fit_beta(tr), ctx["drive_dist"]), ctx["res"])
        rows.append({"D": D, "k": k, "train_margin_ll": float(ll.mean()), "n": int(ll.size)})
        log(f"v4 D={D} k={k} train ll {ll.mean():.5f}")
    best = max(rows, key=lambda r: r["train_margin_ll"])
    return {"tuning": rows, "D": best["D"], "k": best["k"]}


def _relabel(e: dict, a: str, b: str) -> dict:
    """E.evaluate labels its two models v3/v1; rename them."""
    s = json.dumps(e).replace('"v3"', f'"{a}"').replace('"v1"', f'"{b}"').replace("v3_minus_v1", f"{a}_minus_{b}") \
        .replace("paired_v3_vs_v1", f"paired_{a}_vs_{b}").replace("v3_minus_market", f"{a}_minus_market")
    return json.loads(s)


def test(ctx: dict, D: float, k: float) -> dict:
    """Stage 3 (informed test): v4 vs v3 (as specified) vs v1, plus the ablation."""
    reg = ctx["reg"]
    m3 = json.loads(Path(E.__file__).resolve().parents[3].joinpath("data/processed/players_v3_model.json").read_text())
    # v3 exactly as specified and frozen (team_stats TDs, neutral as home, Poisson)
    d3 = E.design(E.features(ctx["data"], ctx["sched"], m3["D"], m3["k"], ctx["const"]), ctx["rates"], ctx["games"])
    b3 = E.fit_beta(E._split(d3, *TRAIN))
    # ablation: fix 1; fixes 1+2 (both Poisson, v3's D/k); v4 = fixes 1-3 at its own tuned D/k
    f3 = E.features(ctx["data"], ctx["sched"], m3["D"], m3["k"], ctx["const"])
    d1 = E.design(f3, ctx["rates_fix1"], ctx["games_fix1"]); b1 = E.fit_beta(E._split(d1, *TRAIN))
    d12 = E.design(f3, ctx["rates_fix12"], ctx["games_fix12"]); b12 = E.fit_beta(E._split(d12, *TRAIN))
    d4 = E.design(E.features(ctx["data"], ctx["sched"], D, k, ctx["const"]), ctx["rates_fix12"], ctx["games_fix12"])
    b4 = E.fit_beta(E._split(d4, *TRAIN))
    out = {"beta_v4": [{"feature": f, "td_b": float(b4["td"]["b"][i + 1]), "td_se": float(b4["td"]["se"][i + 1]),
                        "fg_b": float(b4["fg"]["b"][i + 1]), "fg_se": float(b4["fg"]["se"][i + 1])}
                       for i, f in enumerate(V.FEATURES)]}
    dd = ctx["drive_dist"]

    def block(lo, hi):
        s = E._split(reg, lo, hi)
        pm = {"v4": pmfs_v4(E._split(d4, lo, hi), s, b4, dd),
              "v3": E.game_pmfs(E._split(d3, lo, hi), s, b3),
              "v1": E.game_pmfs(E._split(d3, lo, hi), s, None),
              "fix1": E.game_pmfs(E._split(d1, lo, hi), s, b1),
              "fix12": E.game_pmfs(E._split(d12, lo, hi), s, b12)}
        common = set.intersection(*(set(v) for v in pm.values()))
        pm = {k_: {g: v[g] for g in common} for k_, v in pm.items()}
        g = s.filter(pl.col("result").is_not_null(), pl.col("spread_line").is_not_null(),
                     pl.col("game_id").is_in(list(common))).select(
            "game_id", pl.col("result").alias("margin"), (-pl.col("spread_line")).alias("close"), "total_line")
        pm = {k_: {i: v[i] for i in g["game_id"].to_list()} for k_, v in pm.items()}
        res = {"v4_vs_v3": _relabel(E.evaluate(g, pm["v4"], pm["v3"]), "v4", "v3"),
               "v4_vs_v1": _relabel(E.evaluate(g, pm["v4"], pm["v1"]), "v4", "v1"),
               "ablation_margin_ll": {k_: E._mean_se(E.margin_ll(v, ctx["res"])) for k_, v in pm.items()}}
        pit = _pit(pm["v4"], ctx["res"]); pit3 = _pit(pm["v3"], ctx["res"])
        res["coverage_50"] = {"v4": float(((pit > 0.25) & (pit < 0.75)).mean()),
                              "v3": float(((pit3 > 0.25) & (pit3 < 0.75)).mean())}
        return g, pm, res

    _, _, out["test_a"] = block(*TEST_A)
    gB, pmB, out["test_b"] = block(TEST_B, TEST_B)
    b = gB.join(cbs_opens_2025(ctx["data"]["sched"]), on="game_id", how="inner") \
        .with_columns((pl.col("cbs_open").abs() % 1 == 0.5).alias("half")).filter(pl.col("margin") != -pl.col("cbs_open"))
    hist = reg.filter(pl.col("season").is_between(1999, TEST_B - 1), pl.col("result").is_not_null(),
                      pl.col("spread_line").is_not_null(), pl.col("total_line").is_not_null())
    live = TotalDist("shifted_total").fit(-hist["spread_line"].to_numpy(), hist["result"].to_numpy(), hist["total_line"].to_numpy())
    ids, o = b["game_id"].to_list(), b["cbs_open"].to_numpy()
    y = (b["margin"].to_numpy() > -o).astype(float)
    p = {"v4": np.array([E._cover(pmB["v4"][i], x) for i, x in zip(ids, o)]),
         "v3": np.array([E._cover(pmB["v3"][i], x) for i, x in zip(ids, o)]),
         "live": live.sf(-o, b["close"].to_numpy(), b["total_line"].to_numpy())}
    half = b["half"].to_numpy()
    out["test_b_cbs_open"] = {}
    for lab, msk in (("half_point_opens", half), ("all_opens", np.ones_like(half, bool))):
        out["test_b_cbs_open"][lab] = {
            **{m: {**E._ats(v[msk], y[msk]), "log_loss": C.log_loss(v[msk], y[msk])} for m, v in p.items()},
            "paired_v4_vs_live": E._paired(p["v4"][msk], p["live"][msk], y[msk]),
            "paired_v4_vs_v3": E._paired(p["v4"][msk], p["v3"][msk], y[msk])}
    return out


def run(cache: str | None = None, log=print) -> dict:
    ctx = prepare(cache, log)
    va = validate(ctx, log)
    log(json.dumps({k: v for k, v in va.items() if k not in ("drives_by_season",)}, default=str)[:3000])
    if not va["pass"]:
        return {"validation": va, "scored": False}
    if not va["fix3_kept"]:
        raise SystemExit("fix 3 not supported by training seasons: per pre-registration v4 = fixes 1-2; "
                         "that variant is not implemented in this run")
    tu = tune(ctx, log)
    te = test(ctx, tu["D"], tu["k"])
    return {"validation": va, "tuning": tu, "test": te, "scored": True, "ctx": ctx}
