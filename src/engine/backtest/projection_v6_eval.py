"""Evaluation of proj-epa-v6 (docs/projection_v6_preregistration.md).

Order is fixed by the pre-registration: tune (h, s) on training seasons only (fit 2006-2016, score 2017-2021),
run the validation checks, then fit beta on 2006-2021 and score Test A (2022-2024) and Test B (2025) for v6,
v3 and v1 on the same games.
"""
from __future__ import annotations

import itertools
import json
import math
from pathlib import Path

import numpy as np
import polars as pl

from engine.backtest import calibration as C
from engine.backtest import players_v3_eval as E3
from engine.backtest.holdout2025 import cbs_opens_2025
from engine.backtest.players_eval import fit_offset_poisson, v1_rates
from engine.data import nflverse
from engine.features import efficiency_v6 as F
from engine.features import players_v3 as V3
from engine.models import projection as P
from engine.models.margin_dist import MarginDist, TotalDist

TRAIN = (2006, 2021)
INNER_FIT, INNER_SCORE = (2006, 2016), (2017, 2021)
TEST_A = (2022, 2024)
TEST_B = 2025
GRID_H = (4, 8, 16)
GRID_S = (0.3, 0.6)
V3_D, V3_K, V3_TRAIN = 365, 500, (2013, 2021)     # v3 as frozen (data/processed/players_v3_model.json)
MG = np.arange(-P.MAXP, P.MAXP + 1)
PIT_TOL = 1e-12
NET_CORR_MIN = 0.6
COVERAGE_MIN = 0.99


# ---------------------------------------------------------------- data

def load_metrics(cache: str, log=print) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Per-game metrics 1999-2025 and per-season filter statistics, cached as parquet in `cache`."""
    import nflreadpy as nfl
    c = Path(cache)
    fm, fs = c / "v6_metrics.parquet", c / "v6_filter_stats.parquet"
    if fm.exists() and fs.exists():
        return pl.read_parquet(fm), pl.read_parquet(fs)
    parts, stats = [], []
    for s in range(1999, TEST_B + 1):
        d = nfl.load_pbp(seasons=[s]).select(F.PBP_COLS)
        cp = F.counted_plays(d)
        m = F.game_metrics(d)
        reg_ids = d.filter(pl.col("season_type") == "REG")["game_id"].unique().implode()
        mr = m.filter(pl.col("game_id").is_in(reg_ids))
        stats.append({"season": s, "counted_plays": cp.height, "garbage_share": float(cp["garbage"].mean()),
                      "rz_drives_per_team_game": float(mr["n_rz"].fill_null(0).mean()),
                      "team_games_without_rz_drive": int(mr["n_rz"].is_null().sum()),
                      "team_games": mr.height})
        parts.append(m)
        log(f"pbp {s}: {cp.height} plays, garbage {stats[-1]['garbage_share']:.3f}")
    metrics, st = pl.concat(parts), pl.DataFrame(stats)
    c.mkdir(parents=True, exist_ok=True)
    metrics.write_parquet(fm); st.write_parquet(fs)
    return metrics, st


def prepare(cache: str, log=print) -> dict:
    data = E3.load(cache)                        # sched, team_stats and the v3 inputs (cached parquet)
    sched = nflverse.with_kickoff(data["sched"]).filter(pl.col("season").is_between(1999, TEST_B))
    metrics, fstats = load_metrics(cache, log)
    games = P.team_games(data["team_stats"], data["sched"])
    rp = Path(cache) / "v6_v1_rates_2006_2025.parquet"
    if rp.exists():
        rates = pl.read_parquet(rp)
    else:
        rates = v1_rates(games, games.filter(pl.col("season").is_between(TRAIN[0], TEST_B)))
        rates.write_parquet(rp)
    log(f"v1 walk-forward rates: {rates.height} team-games")
    reg = sched.filter(pl.col("game_type") == "REG", pl.col("season").is_between(TRAIN[0], TEST_B))
    done = reg.filter(pl.col("result").is_not_null())
    return {"data": data, "sched": sched, "metrics": metrics, "filter_stats": fstats, "games": games,
            "rates": rates, "reg": reg, "res": dict(zip(done["game_id"].to_list(), done["result"].to_list()))}


# ---------------------------------------------------------------- model

def features(ctx: dict, h: float, s: float) -> pl.DataFrame:
    return F.build(ctx["sched"], ctx["metrics"], h, s)


def design(feat: pl.DataFrame, rates: pl.DataFrame, games: pl.DataFrame) -> pl.DataFrame:
    return rates.join(feat.filter(pl.col("game_type") == "REG").select("game_id", "team", "season", *F.FEATURES),
                      on=["game_id", "team"]) \
        .join(games.select("game_id", "team", "td", "fg"), on=["game_id", "team"], how="left")


def split(df: pl.DataFrame, lo: int, hi: int) -> pl.DataFrame:
    return df.filter(pl.col("season").is_between(lo, hi))


def fit_beta(d: pl.DataFrame, feats=F.FEATURES) -> dict:
    X = d.select(feats).to_numpy().astype(float)
    return {k: dict(zip(("b", "se"), fit_offset_poisson(X, d[k].to_numpy().astype(float),
                                                       np.log(d[f"lam_{k}"].to_numpy())))) for k in ("td", "fg")}


def _adj(r: dict, beta: dict | None, k: str, feats) -> float:
    lam = r[f"lam_{k}"]
    if beta is None:
        return lam
    b = beta[k]["b"]
    return lam * math.exp(b[0] + sum(b[i + 1] * r[f] for i, f in enumerate(feats)))


def game_pmfs(d: pl.DataFrame, sched: pl.DataFrame, beta: dict | None, feats=F.FEATURES) -> dict:
    rows = {(r["game_id"], r["team"]): r for r in d.iter_rows(named=True)}
    out = {}
    for g in sched.select("game_id", pl.col("home_team").replace(P.FRANCHISE).alias("h"),
                          pl.col("away_team").replace(P.FRANCHISE).alias("a")).iter_rows(named=True):
        rh, ra = rows.get((g["game_id"], g["h"])), rows.get((g["game_id"], g["a"]))
        if rh is None or ra is None:
            continue
        pr = P.Projection(P.points_pmf(_adj(rh, beta, "td", feats), _adj(rh, beta, "fg", feats), rh["p_xp"], rh["p_2"]),
                          P.points_pmf(_adj(ra, beta, "td", feats), _adj(ra, beta, "fg", feats), ra["p_xp"], ra["p_2"]))
        out[g["game_id"]] = pr.margin_pmf
    return out


def margin_ll(pmfs: dict, res: dict) -> np.ndarray:
    return np.array([math.log(max(float(pmfs[g][int(res[g]) + P.MAXP]), 1e-12)) for g in pmfs if g in res])


# ---------------------------------------------------------------- stage 1: tuning (training seasons only)

def tune(ctx: dict, log=print) -> dict:
    rows = []
    for h, s in itertools.product(GRID_H, GRID_S):
        d = design(features(ctx, h, s), ctx["rates"], ctx["games"])
        beta = fit_beta(split(d, *INNER_FIT))
        ll = margin_ll(game_pmfs(split(d, *INNER_SCORE), split(ctx["reg"], *INNER_SCORE), beta), ctx["res"])
        rows.append({"h": h, "s": s, "inner_margin_ll": float(ll.mean()), "n": int(ll.size)})
        log(f"h={h} s={s} inner margin ll {ll.mean():.5f} (n={ll.size})")
    # v1 on the same inner block, for reference
    d = design(features(ctx, GRID_H[0], GRID_S[0]), ctx["rates"], ctx["games"])
    ll1 = margin_ll(game_pmfs(split(d, *INNER_SCORE), split(ctx["reg"], *INNER_SCORE), None), ctx["res"])
    best = max(rows, key=lambda r: r["inner_margin_ll"])
    return {"grid": rows, "v1_inner_margin_ll": float(ll1.mean()), "h": best["h"], "s": best["s"]}


# ---------------------------------------------------------------- stage 2: validation checks

def point_in_time_check(ctx: dict, h: float, s: float, game_ids: list[str]) -> list[dict]:
    full = features(ctx, h, s)
    sched, metrics = F.with_order_time(ctx["sched"]), ctx["metrics"]
    kick = sched.select("game_id", "kickoff_utc")
    out = []
    for gid in game_ids:
        ko = sched.filter(pl.col("game_id") == gid)["kickoff_utc"][0]
        early = kick.filter(pl.col("kickoff_utc") < ko)["game_id"].implode()
        cut_s = sched.filter(pl.col("kickoff_utc") <= ko)
        cut_m = metrics.filter(pl.col("game_id").is_in(early))
        a = F.build(cut_s, cut_m, h, s).filter(pl.col("game_id") == gid).sort("team")
        b = full.filter(pl.col("game_id") == gid).sort("team")
        diff = max(abs(x - y) for c in F.FEATURES for x, y in zip(a[c].to_list(), b[c].to_list()))
        out.append({"game_id": gid, "max_abs_diff": float(diff), "rows": a.height})
    return out


def validate(ctx: dict, h: float, s: float, n_pit: int = 2) -> dict:
    out = {}
    feat = features(ctx, h, s)
    reg = feat.filter(pl.col("game_type") == "REG", pl.col("season").is_between(TRAIN[0], TEST_B))
    # 1. point in time: seeded sample, 2 games per season 2006-2025
    rng = np.random.default_rng(20260928)
    sample = []
    for yr in range(TRAIN[0], TEST_B + 1):
        ids = sorted(set(reg.filter(pl.col("season") == yr)["game_id"].to_list()))
        sample += [ids[i] for i in rng.choice(len(ids), n_pit, replace=False)]
    pit = point_in_time_check(ctx, h, s, sample)
    out["point_in_time"] = {"games": len(pit), "max_abs_diff": max(r["max_abs_diff"] for r in pit),
                            "all_two_rows": all(r["rows"] == 2 for r in pit), "rows": pit}
    # 2. beta = 0 reproduces v1: checked by the unit test tests/test_projection_v6.py, and here on real data
    d = design(feat, ctx["rates"], ctx["games"])
    blk = split(d, 2023, 2023)
    zero = {k: {"b": np.zeros(len(F.FEATURES) + 1)} for k in ("td", "fg")}
    p0, p1 = game_pmfs(blk, split(ctx["reg"], 2023, 2023), zero), game_pmfs(blk, split(ctx["reg"], 2023, 2023), None)
    out["beta0_equals_v1"] = {"games": len(p0), "max_abs_diff": max(float(np.abs(p0[g] - p1[g]).max()) for g in p0)}
    # 3. ratings: end-of-2023 lists, and net rating vs season point differential 2006-2021
    tg = F.team_games(ctx["sched"], ctx["metrics"])
    snaps: dict = {}
    F.ratings(tg, h, s, end_of_regular_season=snaps)
    s23 = snaps[2023]
    teams23 = set(tg.filter(pl.col("season") == 2023)["team"].to_list())
    rows = [{"team": t, "off_db": s23[t][0]["db"], "def_db": s23[t][1]["db"]} for t in sorted(teams23)]
    out["end_2023"] = {"top5_offense_db": sorted(rows, key=lambda r: -r["off_db"])[:5],
                       "bottom5_offense_db": sorted(rows, key=lambda r: r["off_db"])[:5],
                       "top5_defense_db": sorted(rows, key=lambda r: r["def_db"])[:5],
                       "bottom5_defense_db": sorted(rows, key=lambda r: -r["def_db"])[:5]}
    g = ctx["games"].filter(pl.col("season").is_between(*TRAIN))
    opp_pts = g.select("game_id", pl.col("team").alias("opp"), pl.col("pts").alias("opp_pts"))
    pd_ = g.join(opp_pts, on=["game_id", "opp"]).group_by("season", "team").agg(
        (pl.col("pts") - pl.col("opp_pts")).sum().alias("pd"))
    net, pdv = [], []
    for r in pd_.iter_rows(named=True):
        st = snaps.get(r["season"], {}).get(r["team"])
        if st:
            net.append(st[0]["db"] + st[0]["rush"] - st[1]["db"] - st[1]["rush"]); pdv.append(r["pd"])
    corr = float(np.corrcoef(net, pdv)[0, 1])
    out["net_rating_vs_point_diff"] = {"team_seasons": len(net), "corr": corr, "pass": corr > NET_CORR_MIN}
    # 4. coverage: REG team-games 2006-2025 whose own and opponent play data exist (db, rush, sr)
    tgr = tg.filter(pl.col("game_type") == "REG", pl.col("season").is_between(TRAIN[0], TEST_B))
    have = tgr.select(pl.all_horizontal([pl.col(f"{p}_{m}").is_not_null() for p in ("o", "a")
                                         for m in ("db", "rush", "sr")]).alias("ok"))["ok"]
    feats_ok = reg.select(pl.all_horizontal([pl.col(c).is_not_null() for c in F.FEATURES]).alias("ok"))["ok"]
    out["coverage"] = {"team_games": tgr.height, "share_with_play_data": float(have.mean()),
                       "missing": tgr.filter(~have).select("game_id", "team").to_dicts()[:20],
                       "share_with_all_8_features": float(feats_ok.mean()),
                       "pass": float(have.mean()) >= COVERAGE_MIN}
    # 5. filter statistics (reported)
    out["filter_stats"] = ctx["filter_stats"].to_dicts()
    out["pass"] = (out["point_in_time"]["max_abs_diff"] < PIT_TOL and out["point_in_time"]["all_two_rows"]
                   and out["beta0_equals_v1"]["max_abs_diff"] == 0.0
                   and out["net_rating_vs_point_diff"]["pass"] and out["coverage"]["pass"])
    return out


# ---------------------------------------------------------------- stage 3: test (only after validation passes)

def _mean_se(x):
    return {"mean": float(np.mean(x)), "se": float(np.std(x, ddof=1) / math.sqrt(len(x))), "n": int(len(x))}


def _ats(p, y):
    w = int(((p > 0.5) == (y == 1)).sum()); n = len(y); r = w / n
    return {"W": w, "L": n - w, "N": n, "win_rate": r, "se": math.sqrt(r * (1 - r) / n)}


def _paired(pa, pb, y):
    ca, cb = (pa > 0.5) == (y == 1), (pb > 0.5) == (y == 1)
    a_only, b_only = int((ca & ~cb).sum()), int((cb & ~ca).sum())
    n = a_only + b_only
    return {"a_only": a_only, "b_only": b_only, "z": (a_only - b_only) / math.sqrt(n) if n else 0.0}


def _cover(pmf, line):
    up, dn = float(pmf[MG > -line].sum()), float(pmf[MG < -line].sum())
    return up / (up + dn)


def evaluate(g: pl.DataFrame, pms: dict, market_win: np.ndarray) -> dict:
    """g: game_id, margin, close (canonical home spread) for games present in every model's pmfs."""
    ids, m, c = g["game_id"].to_list(), g["margin"].to_numpy(), g["close"].to_numpy()
    out = {"n_games": len(ids)}
    ll = {k: np.array([math.log(max(pm[i][int(x) + P.MAXP], 1e-12)) for i, x in zip(ids, m)]) for k, pm in pms.items()}
    out["margin_ll"] = {k: _mean_se(v) for k, v in ll.items()}
    out["margin_ll"]["v6_minus_v1"] = _mean_se(ll["v6"] - ll["v1"])
    out["margin_ll"]["v6_minus_v3"] = _mean_se(ll["v6"] - ll["v3"])
    pred = {k: np.array([float(pm[i] @ MG) for i in ids]) for k, pm in pms.items()}
    ae = {k: np.abs(m - v) for k, v in pred.items()}
    ae["market_close"] = np.abs(m + c)
    out["mae"] = {k: _mean_se(v) for k, v in ae.items()}
    out["mae"]["v6_minus_v1"] = _mean_se(ae["v6"] - ae["v1"])
    out["mae"]["v6_minus_v3"] = _mean_se(ae["v6"] - ae["v3"])
    out["mae"]["v6_minus_market"] = _mean_se(ae["v6"] - ae["market_close"])
    nt = m != 0
    yw = (m[nt] > 0).astype(float)
    pw = {k: np.array([float(pm[i][MG > 0].sum() / (1 - pm[i][MG == 0].sum())) for i in np.array(ids)[nt]])
          for k, pm in pms.items()}
    pw["market_close"] = market_win[nt]
    out["win_log_loss"] = {**{k: C.log_loss(v, yw) for k, v in pw.items()}, "n": int(nt.sum())}
    npu = m != -c
    yc = (m[npu] > -c[npu]).astype(float)
    pc = {k: np.array([_cover(pm[i], cc) for i, cc in zip(np.array(ids)[npu], c[npu])]) for k, pm in pms.items()}
    out["ats_close"] = {k: {**_ats(v, yc), "log_loss": C.log_loss(v, yc)} for k, v in pc.items()}
    out["ats_close"]["paired_v6_vs_v1"] = _paired(pc["v6"], pc["v1"], yc)
    out["ats_close"]["paired_v6_vs_v3"] = _paired(pc["v6"], pc["v3"], yc)
    # diagnostics: does v6's disagreement with the close predict the close's error?
    dis, err = pred["v6"] + c, m + c
    out["diag"] = {"corr_v6_minus_close_vs_margin_minus_close": float(np.corrcoef(dis, err)[0, 1])}
    big = np.abs(dis) >= 3
    sel = big & npu
    if sel.sum():
        right = np.sign(dis[sel]) == np.sign(err[sel])
        r = float(right.mean())
        out["diag"]["disagree_3plus"] = {"games": int(sel.sum()), "v6_side_covers": int(right.sum()), "rate": r,
                                         "se": math.sqrt(r * (1 - r) / sel.sum())}
    return out


def v3_design(ctx: dict) -> tuple[pl.DataFrame, dict]:
    """v3 exactly as frozen: D=365, k=500, beta fit on 2013-2021 (its own training block)."""
    data = ctx["data"]
    s3 = nflverse.with_kickoff(data["sched"]).filter(pl.col("season").is_between(2006, TEST_B))
    const = E3.constants(data, s3)
    f3 = E3.features(data, s3, V3_D, V3_K, const)
    d3 = ctx["rates"].join(f3.select("game_id", "team", "season", *V3.FEATURES), on=["game_id", "team"]) \
        .join(ctx["games"].select("game_id", "team", "td", "fg"), on=["game_id", "team"], how="left")
    return d3, fit_beta(split(d3, *V3_TRAIN), V3.FEATURES)


def test(ctx: dict, h: float, s: float, log=print) -> dict:
    reg = ctx["reg"]
    d = design(features(ctx, h, s), ctx["rates"], ctx["games"])
    tr = split(d, *TRAIN)
    beta = fit_beta(tr)
    out = {"n_train_team_games": tr.height,
           "beta": [{"feature": f, **{f"{k}_b": float(beta[k]["b"][i]) for k in ("td", "fg")},
                     **{f"{k}_se": float(beta[k]["se"][i]) for k in ("td", "fg")}}
                    for i, f in enumerate(["intercept", *F.FEATURES])]}
    d3, beta3 = v3_design(ctx)
    log("v3 rebuilt as frozen")

    def mkt(block_start):
        hh = ctx["sched"].filter(pl.col("game_type") == "REG", pl.col("season").is_between(1999, block_start - 1),
                                 pl.col("result").is_not_null(), pl.col("spread_line").is_not_null())
        return MarginDist("shifted").fit(-hh["spread_line"].to_numpy(), hh["result"].to_numpy())

    def block(lo, hi):
        sb = split(reg, lo, hi)
        pms = {"v6": game_pmfs(split(d, lo, hi), sb, beta), "v1": game_pmfs(split(d, lo, hi), sb, None),
               "v3": game_pmfs(split(d3, lo, hi), sb, beta3, V3.FEATURES)}
        common = set(pms["v6"]) & set(pms["v1"]) & set(pms["v3"])
        g = sb.filter(pl.col("result").is_not_null(), pl.col("spread_line").is_not_null(),
                      pl.col("game_id").is_in(list(common))).select(
            "game_id", pl.col("result").alias("margin"), (-pl.col("spread_line")).alias("close"), "total_line")
        mw = mkt(lo).sf(np.zeros(g.height), g["close"].to_numpy())
        return g, pms, {**evaluate(g, pms, mw), "games_in_block": sb.height, "games_scored": g.height}

    _, _, out["test_a"] = block(*TEST_A)
    gB, pmB, out["test_b"] = block(TEST_B, TEST_B)
    # Test B against the CBS open and the live model (fit on seasons before 2025), as in v3's evaluation
    b = gB.join(cbs_opens_2025(ctx["data"]["sched"]), on="game_id", how="inner") \
        .with_columns((pl.col("cbs_open").abs() % 1 == 0.5).alias("half")) \
        .filter(pl.col("margin") != -pl.col("cbs_open"))
    hist = ctx["sched"].filter(pl.col("game_type") == "REG", pl.col("season").is_between(1999, TEST_B - 1),
                               pl.col("result").is_not_null(), pl.col("spread_line").is_not_null(),
                               pl.col("total_line").is_not_null())
    live = TotalDist("shifted_total").fit(-hist["spread_line"].to_numpy(), hist["result"].to_numpy(),
                                          hist["total_line"].to_numpy())
    ids, o = b["game_id"].to_list(), b["cbs_open"].to_numpy()
    y = (b["margin"].to_numpy() > -o).astype(float)
    p = {k: np.array([_cover(pmB[k][i], x) for i, x in zip(ids, o)]) for k in ("v6", "v3", "v1")}
    p["live"] = live.sf(-o, b["close"].to_numpy(), b["total_line"].to_numpy())
    half = b["half"].to_numpy()
    out["test_b_cbs_open"] = {}
    for lab, msk in (("half_point_opens", half), ("all_opens", np.ones_like(half, bool))):
        out["test_b_cbs_open"][lab] = {
            **{k: {**_ats(v[msk], y[msk]), "log_loss": C.log_loss(v[msk], y[msk])} for k, v in p.items()},
            "paired_v6_vs_live": _paired(p["v6"][msk], p["live"][msk], y[msk]),
            "paired_v6_vs_v3": _paired(p["v6"][msk], p["v3"][msk], y[msk])}
    ta = out["test_a"]["margin_ll"]
    out["decision"] = {"replaces_v3_as_tracked": ta["v6"]["mean"] > ta["v1"]["mean"] and ta["v6"]["mean"] > ta["v3"]["mean"]}
    return out


def run(cache: str, log=print) -> dict:
    ctx = prepare(cache, log)
    tu = tune(ctx, log)
    va = validate(ctx, tu["h"], tu["s"])
    log(f"validation pass: {va['pass']}")
    out = {"tuning": tu, "validation": va}
    if va["pass"]:
        out["test"] = test(ctx, tu["h"], tu["s"], log)
    return out
