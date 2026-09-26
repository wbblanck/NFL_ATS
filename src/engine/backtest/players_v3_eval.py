"""Evaluation of proj-players-v3 (docs/players_v3_preregistration.md).

Order is fixed by the pre-registration: estimate train-only constants, tune (D, k) on train,
run the validation checks, then Test A (2022-2024) and Test B (2025).
"""
from __future__ import annotations

import itertools
import math
from pathlib import Path

import numpy as np
import polars as pl

from engine.backtest import calibration as C
from engine.backtest.holdout2025 import cbs_opens_2025
from engine.backtest.players_eval import fit_offset_poisson, v1_rates
from engine.data import nflverse
from engine.features import players_v3 as V
from engine.models import projection as P
from engine.models.margin_dist import MarginDist, TotalDist

TRAIN = (2013, 2021)
TEST_A = (2022, 2024)
TEST_B = 2025
GRID_D = (180, 365, 730)
GRID_K = (100, 250, 500)
MG = np.arange(-P.MAXP, P.MAXP + 1)
PIT_TOL = 1e-12        # floating-point summation order only; any leak would move a feature by far more


# ---------------------------------------------------------------- data

def load(cache: str | None = None) -> dict:
    """Raw tables. With `cache`, reads/writes parquet there so repeated runs use identical data."""
    import nflreadpy as nfl
    cache_p = Path(cache) if cache else None

    def get(name, fn):
        if cache_p and (cache_p / f"{name}.parquet").exists():
            return pl.read_parquet(cache_p / f"{name}.parquet")
        df = fn()
        if cache_p:
            cache_p.mkdir(parents=True, exist_ok=True)
            df.write_parquet(cache_p / f"{name}.parquet")
        return df

    def dropbacks():
        cols = ["game_id", "season", "season_type", "week", "game_date", "posteam", "qb_dropback", "qb_epa",
                "passer_player_id", "rusher_player_id", "passer_player_name", "rusher_player_name"]
        parts = []
        for s in range(2006, TEST_B + 1):
            d = nfl.load_pbp(seasons=[s])
            parts.append(d.filter(pl.col("qb_dropback") == 1).select(cols))
        return pl.concat(parts, how="diagonal_relaxed")

    seasons = list(range(TRAIN[0], TEST_B + 1))
    return {
        "sched": get("sched", nfl.load_schedules),
        "team_stats": get("team_stats", lambda: nfl.load_team_stats(seasons=list(range(1999, TEST_B + 1)))),
        "dropbacks": get("dropbacks", dropbacks),
        "injuries": get("injuries", lambda: nfl.load_injuries(seasons=seasons)),
        "snaps": get("snap_counts", lambda: nfl.load_snap_counts(seasons=seasons)),
        "players": get("players", nfl.load_players),
        "depth25": get("depth25", lambda: nfl.load_depth_charts(seasons=[TEST_B])),
        "depth_old": get("depth_old", lambda: nfl.load_depth_charts(seasons=list(range(TRAIN[0], TEST_B)))),
    }


def _season(gid: pl.Expr) -> pl.Expr:
    return gid.str.slice(0, 4).cast(pl.Int32)


def constants(data: dict, sched: pl.DataFrame) -> dict:
    """Train-only constants: replacement prior and play probabilities."""
    prior = V.replacement_prior(data["dropbacks"], TRAIN)
    tg = V.team_game_frame(sched)
    reps = V.injury_reports(data["injuries"], tg).filter(pl.col("season").is_between(*TRAIN))
    snaps = V.snap_table(data["snaps"], data["players"]).filter(_season(pl.col("game_id")).is_between(*TRAIN))
    return {"prior": prior, "p_play": V.play_probabilities(reps, snaps)}


def features(data, sched, D, k, const, targets=None, weekly_depth=False):
    return V.build(sched, data["dropbacks"], data["injuries"], data["snaps"], data["players"], data["depth25"],
                   D, k, const["prior"]["prior"], const["p_play"], targets,
                   depth_old=data["depth_old"] if weekly_depth else None)


# ---------------------------------------------------------------- model

def design(feat: pl.DataFrame, rates: pl.DataFrame, games: pl.DataFrame) -> pl.DataFrame:
    """Team-game rows with v1 walk-forward rates, v3 features and the actual TD/FG counts."""
    return rates.join(feat.select("game_id", "team", "season", "week", *V.FEATURES), on=["game_id", "team"]) \
        .join(games.select("game_id", "team", "td", "fg"), on=["game_id", "team"], how="left")


def fit_beta(d: pl.DataFrame) -> dict:
    X = d.select(V.FEATURES).to_numpy().astype(float)
    out = {}
    for k in ("td", "fg"):
        b, se = fit_offset_poisson(X, d[k].to_numpy().astype(float), np.log(d[f"lam_{k}"].to_numpy()))
        out[k] = {"b": b, "se": se}
    return out


def _adj(r: dict, beta: dict | None, k: str) -> float:
    lam = r[f"lam_{k}"]
    if beta is None:
        return lam
    b = beta[k]["b"]
    return lam * math.exp(b[0] + sum(b[i + 1] * r[f] for i, f in enumerate(V.FEATURES)))


def game_pmfs(d: pl.DataFrame, sched: pl.DataFrame, beta: dict | None) -> dict:
    """game_id -> margin pmf (home - away) for every game with both team rows."""
    rows = {(r["game_id"], r["team"]): r for r in d.iter_rows(named=True)}
    out = {}
    for g in sched.select("game_id", pl.col("home_team").replace(P.FRANCHISE).alias("h"),
                          pl.col("away_team").replace(P.FRANCHISE).alias("a")).iter_rows(named=True):
        rh, ra = rows.get((g["game_id"], g["h"])), rows.get((g["game_id"], g["a"]))
        if rh is None or ra is None:
            continue
        pr = P.Projection(P.points_pmf(_adj(rh, beta, "td"), _adj(rh, beta, "fg"), rh["p_xp"], rh["p_2"]),
                          P.points_pmf(_adj(ra, beta, "td"), _adj(ra, beta, "fg"), ra["p_xp"], ra["p_2"]))
        out[g["game_id"]] = pr.margin_pmf
    return out


def margin_ll(pmfs: dict, res: dict) -> np.ndarray:
    return np.array([math.log(max(float(pmfs[g][int(res[g]) + P.MAXP]), 1e-12)) for g in pmfs if g in res])


# ---------------------------------------------------------------- metrics

def _mean_se(x: np.ndarray) -> dict:
    return {"mean": float(np.mean(x)), "se": float(np.std(x, ddof=1) / math.sqrt(len(x))), "n": int(len(x))}


def _ats(p: np.ndarray, y: np.ndarray) -> dict:
    w = int(((p > 0.5) == (y == 1)).sum()); n = len(y); r = w / n
    return {"W": w, "L": n - w, "N": n, "win_rate": r, "se": math.sqrt(r * (1 - r) / n)}


def _paired(pa: np.ndarray, pb: np.ndarray, y: np.ndarray) -> dict:
    """ATS difference a - b on the same games: only disagreements matter (sign test)."""
    ca, cb = (pa > 0.5) == (y == 1), (pb > 0.5) == (y == 1)
    a_only, b_only = int((ca & ~cb).sum()), int((cb & ~ca).sum())
    n = a_only + b_only
    return {"a_only": a_only, "b_only": b_only, "z": (a_only - b_only) / math.sqrt(n) if n else 0.0}


def _cover(pmf: np.ndarray, line: float) -> float:
    """P(home covers | no push) for home spread `line`."""
    up, dn = float(pmf[MG > -line].sum()), float(pmf[MG < -line].sum())
    return up / (up + dn)


def evaluate(games: pl.DataFrame, pm3: dict, pm1: dict, extra: dict | None = None) -> dict:
    """games: game_id, margin, close (canonical home spread), total_line, and optional league columns."""
    g = games.filter(pl.col("game_id").is_in(list(pm3.keys())), pl.col("game_id").is_in(list(pm1.keys())))
    ids, m, c = g["game_id"].to_list(), g["margin"].to_numpy(), g["close"].to_numpy()
    out = {"n_games": len(ids)}
    ll3 = np.array([math.log(max(pm3[i][int(x) + P.MAXP], 1e-12)) for i, x in zip(ids, m)])
    ll1 = np.array([math.log(max(pm1[i][int(x) + P.MAXP], 1e-12)) for i, x in zip(ids, m)])
    out["margin_ll"] = {"v3": _mean_se(ll3), "v1": _mean_se(ll1), "diff_v3_minus_v1": _mean_se(ll3 - ll1)}
    line = {k: np.array([float(-(pm[i] @ MG)) for i in ids]) for k, pm in (("v3", pm3), ("v1", pm1))}
    ae = {"v3": np.abs(m + line["v3"]), "v1": np.abs(m + line["v1"]), "market_close": np.abs(m + c)}
    out["mae"] = {k: _mean_se(v) for k, v in ae.items()}
    out["mae"]["diff_v3_minus_v1"] = _mean_se(ae["v3"] - ae["v1"])
    out["mae"]["diff_v3_minus_market"] = _mean_se(ae["v3"] - ae["market_close"])
    # P(home wins | not a tie)
    nt = m != 0
    yw = (m[nt] > 0).astype(float)
    pw = {k: np.array([float(pm[i][MG > 0].sum() / (1 - pm[i][MG == 0].sum())) for i in np.array(ids)[nt]])
          for k, pm in (("v3", pm3), ("v1", pm1))}
    if extra and "market_win" in extra:
        pw["market_close"] = extra["market_win"][nt]
    out["win_log_loss"] = {k: C.log_loss(v, yw) for k, v in pw.items()}
    out["win_log_loss"]["n"] = int(nt.sum())
    # ATS against the close (pushes excluded)
    np_ = m != -c
    yc = (m[np_] > -c[np_]).astype(float)
    pc = {k: np.array([_cover(pm[i], cc) for i, cc in zip(np.array(ids)[np_], c[np_])]) for k, pm in (("v3", pm3), ("v1", pm1))}
    out["ats_close"] = {k: {**_ats(v, yc), "log_loss": C.log_loss(v, yc)} for k, v in pc.items()}
    out["ats_close"]["paired_v3_vs_v1"] = _paired(pc["v3"], pc["v1"], yc)
    return out


# ---------------------------------------------------------------- point-in-time check

def point_in_time_check(data, sched, D, k, const, game_ids: list[str]) -> list[dict]:
    """Rebuild each game's features after deleting every game, play, snap row, injury report and
    depth-chart snapshot at or after its kickoff (lock, for reports and snapshots). Features must match."""
    full = features(data, sched, D, k, const, targets=game_ids)
    kick = sched.select("game_id", "kickoff_utc")
    out = []
    for gid in game_ids:
        g = sched.filter(pl.col("game_id") == gid).row(0, named=True)
        ko, lock = g["kickoff_utc"], g["lock_utc"]
        s2 = sched.filter(pl.col("kickoff_utc") <= ko)
        early = kick.filter(pl.col("kickoff_utc") < ko)["game_id"].implode()
        inj = data["injuries"].filter(
            (pl.col("season").cast(pl.Int32) < g["season"])
            | ((pl.col("season").cast(pl.Int32) == g["season"]) & (pl.col("week").cast(pl.Int32) <= g["week"])))
        inj = inj.filter(pl.col("date_modified").is_null() | (pl.col("date_modified") < lock))
        cut = {**data,
               "dropbacks": data["dropbacks"].filter(pl.col("game_id").is_in(early)),
               "snaps": data["snaps"].filter(pl.col("game_id").is_in(early)),
               "injuries": inj,
               "depth25": data["depth25"].filter(pl.col("dt") < lock.strftime("%Y-%m-%dT%H:%M:%SZ"))}
        a = features(cut, s2, D, k, const, targets=[gid]).sort("team")
        b = full.filter(pl.col("game_id") == gid).sort("team")
        cols = ["starter", "qb_rating", "qb_baseline", *V.FEATURES]
        diff = max(abs(x - y) for c in cols[1:] for x, y in zip(a[c].to_list(), b[c].to_list()))
        same_qb = a["starter"].to_list() == b["starter"].to_list()
        out.append({"game_id": gid, "max_abs_diff": float(diff), "same_starter": same_qb})
    return out


# ---------------------------------------------------------------- run (three stages, in pre-registered order)

def prepare(cache: str | None = None, log=print) -> dict:
    data = load(cache)
    sched = nflverse.with_kickoff(data["sched"]).filter(pl.col("season").is_between(2006, TEST_B))
    reg = sched.filter(pl.col("game_type") == "REG")
    done = reg.filter(pl.col("result").is_not_null())
    const = constants(data, sched)
    log(f"prior {const['prior']}; p_play {const['p_play']}")
    games = P.team_games(data["team_stats"], data["sched"])
    rates = v1_rates(games, games.filter(pl.col("season").is_between(TRAIN[0], TEST_B)))
    log(f"v1 walk-forward rates: {rates.height} team-games")
    return {"data": data, "sched": sched, "reg": reg, "res": dict(zip(done["game_id"].to_list(), done["result"].to_list())),
            "const": const, "games": games, "rates": rates}


def _split(df, lo, hi):
    return df.filter(pl.col("season").is_between(lo, hi))


def tune(ctx: dict, log=print) -> dict:
    """Stage 1: choose (D, k) by train-season margin log-likelihood. Uses no test-season outcome."""
    tuning = []
    for D, k in itertools.product(GRID_D, GRID_K):
        d = design(features(ctx["data"], ctx["sched"], D, k, ctx["const"]), ctx["rates"], ctx["games"])
        tr = _split(d, *TRAIN)
        ll = margin_ll(game_pmfs(tr, _split(ctx["reg"], *TRAIN), fit_beta(tr)), ctx["res"])
        tuning.append({"D": D, "k": k, "train_margin_ll": float(ll.mean()), "n": int(ll.size)})
        log(f"D={D} k={k} train margin ll {ll.mean():.5f}")
    best = max(tuning, key=lambda r: r["train_margin_ll"])
    return {"tuning": tuning, "D": best["D"], "k": best["k"]}


def test(ctx: dict, D: float, k: float) -> tuple[dict, pl.DataFrame]:
    """Stage 3 (only after the validation checks pass): fit beta on train, score Test A and Test B."""
    reg, d = ctx["reg"], design(features(ctx["data"], ctx["sched"], D, k, ctx["const"]), ctx["rates"], ctx["games"])
    tr = _split(d, *TRAIN)
    beta = fit_beta(tr)
    beta_tab = [{"feature": "intercept", **{f"{kk}_b": float(beta[kk]["b"][0]) for kk in ("td", "fg")},
                 **{f"{kk}_se": float(beta[kk]["se"][0]) for kk in ("td", "fg")}}]
    beta_tab += [{"feature": f, **{f"{kk}_b": float(beta[kk]["b"][i + 1]) for kk in ("td", "fg")},
                  **{f"{kk}_se": float(beta[kk]["se"][i + 1]) for kk in ("td", "fg")}} for i, f in enumerate(V.FEATURES)]
    out = {"beta": beta_tab, "n_train_team_games": tr.height}

    def mkt(block_start):
        h = reg.filter(pl.col("season").is_between(1999, block_start - 1), pl.col("result").is_not_null(),
                       pl.col("spread_line").is_not_null())
        return MarginDist("shifted").fit(-h["spread_line"].to_numpy(), h["result"].to_numpy())

    def block(lo, hi):
        s = _split(reg, lo, hi)
        pm3, pm1 = game_pmfs(_split(d, lo, hi), s, beta), game_pmfs(_split(d, lo, hi), s, None)
        g = s.filter(pl.col("result").is_not_null(), pl.col("spread_line").is_not_null(),
                     pl.col("game_id").is_in(list(pm3))).select(
            "game_id", pl.col("result").alias("margin"), (-pl.col("spread_line")).alias("close"), "total_line")
        mw = mkt(lo).sf(np.zeros(g.height), g["close"].to_numpy())
        return g, pm3, pm1, evaluate(g, pm3, pm1, {"market_win": mw})

    *_, out["test_a"] = block(*TEST_A)
    gB, pm3B, pm1B, out["test_b"] = block(TEST_B, TEST_B)

    # Test B against the CBS open and the live model (total-shifted-empirical, fit on seasons before 2025)
    b = gB.join(cbs_opens_2025(ctx["data"]["sched"]), on="game_id", how="inner") \
        .with_columns((pl.col("cbs_open").abs() % 1 == 0.5).alias("half")) \
        .filter(pl.col("margin") != -pl.col("cbs_open"))
    hist = reg.filter(pl.col("season").is_between(1999, TEST_B - 1), pl.col("result").is_not_null(),
                      pl.col("spread_line").is_not_null(), pl.col("total_line").is_not_null())
    live = TotalDist("shifted_total").fit(-hist["spread_line"].to_numpy(), hist["result"].to_numpy(),
                                          hist["total_line"].to_numpy())
    ids, o = b["game_id"].to_list(), b["cbs_open"].to_numpy()
    y = (b["margin"].to_numpy() > -o).astype(float)
    p = {"v3": np.array([_cover(pm3B[i], x) for i, x in zip(ids, o)]),
         "v1": np.array([_cover(pm1B[i], x) for i, x in zip(ids, o)]),
         "live": live.sf(-o, b["close"].to_numpy(), b["total_line"].to_numpy())}
    half = b["half"].to_numpy()
    out["test_b_cbs_open"] = {}
    for lab, msk in (("half_point_opens", half), ("all_opens", np.ones_like(half, bool))):
        out["test_b_cbs_open"][lab] = {
            **{m: {**_ats(v[msk], y[msk]), "log_loss": C.log_loss(v[msk], y[msk])} for m, v in p.items()},
            "paired_v3_vs_live": _paired(p["v3"][msk], p["live"][msk], y[msk]),
            "paired_v3_vs_v1": _paired(p["v3"][msk], p["v1"][msk], y[msk])}
    return out, d


def coverage(data, sched, f) -> dict:
    """f: the feature frame (one row per team-game), which carries the starter's weighted prior dropbacks."""
    tg = f.filter(pl.col("season").is_between(TRAIN[0], TEST_B))
    reps = V.injury_reports(data["injuries"], V.team_game_frame(sched))
    snaps = V.snap_table(data["snaps"], data["players"])
    rows = []
    for s in range(TRAIN[0], TEST_B + 1):
        t = tg.filter(pl.col("season") == s)
        r = reps.filter(pl.col("season") == s)
        sn = snaps.filter(_season(pl.col("game_id")) == s)
        rows.append({"season": s, "team_games": t.height,
                     "starter_with_prior_dropbacks": float((t["qb_wdropbacks"] > 0).mean()),
                     "starter_rated_at_prior_only": int((t["qb_wdropbacks"] == 0).sum()),
                     "team_games_with_injury_rows": r.select("game_id", "team").unique().height / max(t.height, 1),
                     "injury_players_in_snap_data": float(r["gsis_id"].is_in(sn["gsis_id"].drop_nulls().implode()).mean()) if r.height else None,
                     "snap_rows_id_mapped": float(sn["gsis_id"].is_not_null().mean()) if sn.height else None})
    return {"by_season": rows}


def validate(ctx: dict, D: float, k: float, n_pit: int = 2) -> dict:
    """Stage 2: the pre-registered validation checks. No test-season outcome is read here."""
    data, sched, const = ctx["data"], ctx["sched"], ctx["const"]
    f = features(data, sched, D, k, const)
    qbg = V.qb_games(data["dropbacks"])
    names = data["dropbacks"].select(pl.coalesce("passer_player_id", "rusher_player_id").alias("qb"),
                                     pl.coalesce("passer_player_name", "rusher_player_name").alias("name")) \
        .drop_nulls().unique("qb", keep="first")
    nm = dict(zip(names["qb"].to_list(), names["name"].to_list()))
    out = {}
    # 1. point-in-time: fixed sample (seeded), plus the named known cases
    reg = f.filter(pl.col("season").is_between(TRAIN[0], TEST_B))
    rng = np.random.default_rng(20260926)
    sample = []
    for s in range(TRAIN[0], TEST_B + 1):
        ids = sorted(set(reg.filter(pl.col("season") == s)["game_id"].to_list()))
        sample += [ids[i] for i in rng.choice(len(ids), n_pit, replace=False)]
    sample += ["2025_04_JAX_SF", "2025_01_TEN_DEN"]
    sample = [g for g in dict.fromkeys(sample) if g in set(reg["game_id"].to_list())]
    pit = point_in_time_check(data, sched, D, k, const, sample)
    out["point_in_time"] = {"games": len(pit), "max_abs_diff": max(r["max_abs_diff"] for r in pit),
                            "all_same_starter": all(r["same_starter"] for r in pit), "rows": pit}
    # 2. QB ratings at the end of 2023 (day after the 2023 season's last game)
    rater = V.QBRater(qbg, D, k, const["prior"]["prior"])
    end23 = V._day(sched.filter(pl.col("season") == 2023)["gameday"].max()) + 1
    q23 = qbg.filter(pl.col("season") == 2023)["qb"].unique().to_list()
    rows = sorted(({"qb": q, "name": nm.get(q), "rating": rater.rating(q, end23)[0],
                    "w_dropbacks": rater.rating(q, end23)[1]} for q in q23), key=lambda r: -r["rating"])
    out["top10_end_2023"] = rows[:10]
    out["bottom5_end_2023"] = rows[-5:]
    career = qbg.filter(pl.col("day") < end23).group_by("qb").agg(pl.col("n").sum())
    small = [q for q, n in zip(career["qb"].to_list(), career["n"].to_list()) if n < 100 and q in set(q23)]
    dev = [abs(rater.rating(q, end23)[0] - const["prior"]["prior"]) for q in small]
    out["small_sample_qbs"] = {"n": len(small), "mean_abs_dev_from_prior": float(np.mean(dev)) if dev else None,
                               "max_abs_dev_from_prior": float(np.max(dev)) if dev else None}
    # 3. known cases
    def row(gid, team):
        r = f.filter((pl.col("game_id") == gid) & (pl.col("team") == team)).row(0, named=True)
        return {"game_id": gid, "team": team, "starter": nm.get(r["starter"]), "qb_rating": r["qb_rating"],
                "qb_baseline": r["qb_baseline"], "qb_delta": r["qb_delta"], "starter_prior_w_dropbacks": r["qb_wdropbacks"]}
    purdy, ward = row("2025_04_JAX_SF", "SF"), row("2025_01_TEN_DEN", "TEN")
    backup = f.filter(pl.col("season").is_between(TRAIN[0], TEST_A[1])).sort("qb_delta").row(0, named=True)
    out["known_cases"] = {"purdy_2025_w4": {**purdy, "pass": purdy["qb_delta"] > 0},
                          "ward_2025_w1": {**ward, "pass": ward["starter_prior_w_dropbacks"] == 0.0},
                          "most_negative_backup": {**row(backup["game_id"], backup["team"]), "pass": backup["qb_delta"] < 0}}
    # 4. play-probability ordering
    pp = const["p_play"]
    out["p_play"] = {**pp, "ordered": pp["Out"]["p_play"] < pp["Doubtful"]["p_play"] < pp["Questionable"]["p_play"]}
    # 5. coverage, plus the 2025 depth-chart starter vs the recorded starter
    out["coverage"] = coverage(data, sched, f)
    f25 = f.filter(pl.col("season") == TEST_B)
    mism = f25.filter(pl.col("qb_depth") != pl.col("qb_recorded"))
    out["depth_vs_recorded_2025"] = {
        "team_games": f25.height, "agree": float((f25["qb_depth"] == f25["qb_recorded"]).mean()),
        "no_snapshot": int(f25["qb_depth"].is_null().sum()),
        "mismatches": [{"game_id": r["game_id"], "team": r["team"], "depth_qb": nm.get(r["qb_depth"]),
                        "actual": nm.get(r["qb_recorded"]), "qb1_out": r["qb1_out"]} for r in mism.iter_rows(named=True)]}
    inj = data["injuries"]
    out["injury_timestamps"] = {
                                "rows_2025_without_timestamp": int(inj.filter(pl.col("season") == TEST_B)["date_modified"].is_null().sum()),
                                "rows_2025": int(inj.filter(pl.col("season") == TEST_B).height)}
    out["pass"] = (out["point_in_time"]["max_abs_diff"] < PIT_TOL and out["point_in_time"]["all_same_starter"]
                   and out["known_cases"]["purdy_2025_w4"]["pass"] and out["known_cases"]["ward_2025_w1"]["pass"]
                   and out["known_cases"]["most_negative_backup"]["pass"] and out["p_play"]["ordered"])
    return out


def sensitivity_weekly_depth(ctx: dict, D: float, k: float) -> dict:
    """Sensitivity (reported, not a decision input): train and score Test A with the weekly depth-chart QB1
    instead of the recorded starter, so any hindsight in the recorded starter shows up as a difference."""
    reg = ctx["reg"]
    f = features(ctx["data"], ctx["sched"], D, k, ctx["const"], weekly_depth=True)
    agree = f.filter(pl.col("season").is_between(TRAIN[0], TEST_A[1]), pl.col("qb_weekly").is_not_null())
    d = design(f, ctx["rates"], ctx["games"])
    beta = fit_beta(_split(d, *TRAIN))
    s = _split(reg, *TEST_A)
    pm3, pm1 = game_pmfs(_split(d, *TEST_A), s, beta), game_pmfs(_split(d, *TEST_A), s, None)
    g = s.filter(pl.col("result").is_not_null(), pl.col("spread_line").is_not_null(),
                 pl.col("game_id").is_in(list(pm3))).select(
        "game_id", pl.col("result").alias("margin"), (-pl.col("spread_line")).alias("close"), "total_line")
    return {"weekly_qb1_equals_recorded": float((agree["qb_weekly"] == agree["qb_recorded"]).mean()),
            "team_games_with_weekly_qb1": agree.height,
            "team_games_without_weekly_qb1": int(f.filter(pl.col("season").is_between(TRAIN[0], TEST_A[1]),
                                                          pl.col("qb_weekly").is_null()).height),
            "test_a": evaluate(g, pm3, pm1)}


# ---------------------------------------------------------------- results file

def _f(x, n=4):
    return "—" if x is None else (f"{x:.{n}f}" if isinstance(x, float) else str(x))


def _pct(r):
    return f"{100 * r['win_rate']:.2f}% ± {100 * r['se']:.2f} pp ({r['W']}-{r['L']})"


def _block_md(title: str, e: dict, market: bool = True) -> list[str]:
    L = [f"### {title} ({e['n_games']} games)", "",
         "| Metric | v3 | v1 | Market close | v3 − v1 (± SE) |", "|---|---|---|---|---|"]
    ml = e["margin_ll"]
    L.append(f"| Margin log-likelihood (higher is better) | {_f(ml['v3']['mean'])} | {_f(ml['v1']['mean'])} | n/a "
             f"| {ml['diff_v3_minus_v1']['mean']:+.4f} ± {ml['diff_v3_minus_v1']['se']:.4f} |")
    mae = e["mae"]
    L.append(f"| Margin MAE, points | {_f(mae['v3']['mean'], 2)} | {_f(mae['v1']['mean'], 2)} | "
             f"{_f(mae['market_close']['mean'], 2)} | {mae['diff_v3_minus_v1']['mean']:+.3f} ± {mae['diff_v3_minus_v1']['se']:.3f} |")
    w = e["win_log_loss"]
    L.append(f"| P(home wins) log loss ({w['n']} non-ties) | {_f(w['v3'])} | {_f(w['v1'])} | {_f(w.get('market_close'))} | |")
    a = e["ats_close"]
    L.append(f"| ATS vs the close (pushes out) | {_pct(a['v3'])} | {_pct(a['v1'])} | — | "
             f"disagreements: v3 {a['paired_v3_vs_v1']['a_only']}, v1 {a['paired_v3_vs_v1']['b_only']}, "
             f"z = {a['paired_v3_vs_v1']['z']:+.2f} |")
    L.append(f"| Cover log loss vs the close | {_f(a['v3']['log_loss'])} | {_f(a['v1']['log_loss'])} | — | |")
    return L + [""]


def write_results(tu: dict, va: dict, te: dict, se: dict | None, path: str) -> None:
    L = ["# Player Model v3: Results", "",
         "Generated by `python -m engine players-v3`. Rules: `docs/players_v3_preregistration.md`.", "",
         "## Stage 1: hyperparameters (training seasons 2013–2021 only)", "",
         "| D (days) | k (dropbacks) | Train margin log-likelihood |", "|---|---|---|"]
    for r in tu["tuning"]:
        L.append(f"| {r['D']} | {r['k']} | {r['train_margin_ll']:.5f} |")
    L += ["", f"Chosen: **D = {tu['D']}, k = {tu['k']}**.", "", "## Stage 2: validation checks", ""]
    pit = va["point_in_time"]
    L += [f"1. **Point-in-time:** {pit['games']} games rebuilt after deleting everything at or after kickoff. "
          f"Largest feature difference: {pit['max_abs_diff']:.1e} (tolerance {PIT_TOL:.0e}, floating-point summation "
          f"order); same starter in every game: {pit['all_same_starter']}.",
          "2. **QB ratings at the end of 2023** (EPA per dropback, shrunk):", "",
          "| Rank | QB | Rating | Weighted dropbacks |", "|---|---|---|---|"]
    for i, r in enumerate(va["top10_end_2023"], 1):
        L.append(f"| {i} | {r['name']} | {r['rating']:+.3f} | {r['w_dropbacks']:.0f} |")
    L.append("")
    L.append("   Bottom 5: " + ", ".join(f"{r['name']} ({r['rating']:+.3f})" for r in va["bottom5_end_2023"]) + ".")
    sm = va["small_sample_qbs"]
    L.append(f"   QBs with < 100 career dropbacks who played in 2023: {sm['n']}; mean distance from the prior "
             f"{_f(sm['mean_abs_dev_from_prior'])}, max {_f(sm['max_abs_dev_from_prior'])}.")
    L += ["3. **Known cases:**", "", "| Case | Starter | Rating | Team baseline | qb_delta | Pass |", "|---|---|---|---|---|---|"]
    for lab, r in va["known_cases"].items():
        L.append(f"| {lab} ({r['game_id']} {r['team']}) | {r['starter']} | {r['qb_rating']:+.3f} | "
                 f"{r['qb_baseline']:+.3f} | {r['qb_delta']:+.3f} | {r['pass']} |")
    pp = va["p_play"]
    L += ["", "4. **Probability of playing by status** (training seasons):", "",
          "| Status | Reports | P(played) | SE |", "|---|---|---|---|"]
    for s in STATUSES_ORDER:
        L.append(f"| {s} | {pp[s]['n']} | {pp[s]['p_play']:.4f} | {pp[s]['se']:.4f} |")
    L += ["", f"   Ordered Out < Doubtful < Questionable: {pp['ordered']}.", "", "5. **Coverage:**", "",
          "| Season | Team-games | Starter has earlier dropbacks (debuts rated at the prior) | Team-games with injury rows | Injured players found in snap data | Snap rows id-mapped |",
          "|---|---|---|---|---|---|"]
    for r in va["coverage"]["by_season"]:
        L.append(f"| {r['season']} | {r['team_games']} | {r['starter_with_prior_dropbacks']:.3f} ({r['starter_rated_at_prior_only']}) | "
                 f"{r['team_games_with_injury_rows']:.3f} | {_f(r['injury_players_in_snap_data'], 3)} | {_f(r['snap_rows_id_mapped'], 3)} |")
    dv = va["depth_vs_recorded_2025"]
    L += ["", f"   2025 depth-chart QB (last snapshot before lock) equals the actual starter in "
          f"{100 * dv['agree']:.1f}% of {dv['team_games']} team-games; {len(dv['mismatches'])} mismatches; "
          f"{dv['no_snapshot']} with no snapshot.",
          f"   2025 injury rows without a timestamp: {va['injury_timestamps']['rows_2025_without_timestamp']} "
          f"of {va['injury_timestamps']['rows_2025']}.", "", f"**All checks pass: {va['pass']}.**", ""]
    L += ["## Stage 3: out-of-sample results", "", "### Coefficients (fit on 2013–2021; multiplicative on log scale)", "",
          "| Feature | TD β | TD SE | FG β | FG SE |", "|---|---|---|---|---|"]
    for r in te["beta"]:
        L.append(f"| {r['feature']} | {r['td_b']:+.4f} | {r['td_se']:.4f} | {r['fg_b']:+.4f} | {r['fg_se']:.4f} |")
    L.append("")
    L += _block_md("Test A: 2022–2024", te["test_a"])
    L += _block_md("Test B: 2025", te["test_b"])
    L += ["### Test B against the CBS open", "", "| Opens | Model | ATS | Log loss |", "|---|---|---|---|"]
    for lab, blk in te["test_b_cbs_open"].items():
        for m in ("v3", "v1", "live"):
            L.append(f"| {lab} | {m} | {_pct(blk[m])} | {blk[m]['log_loss']:.4f} |")
        pv = blk["paired_v3_vs_live"]
        L.append(f"| {lab} | v3 vs live, disagreements | v3 right {pv['a_only']}, live right {pv['b_only']}, z = {pv['z']:+.2f} | |")
    if se:
        L += ["", "## Sensitivity: weekly depth-chart QB1 instead of the recorded starter (2013–2024)", "",
              f"Weekly QB1 equals the recorded starter in {100 * se['weekly_qb1_equals_recorded']:.1f}% of "
              f"{se['team_games_with_weekly_qb1']} team-games ({se['team_games_without_weekly_qb1']} without a weekly QB1, "
              "which fall back to the recorded starter).", ""]
        L += _block_md("Test A with weekly depth-chart QB1", se["test_a"])
    Path(path).write_text("\n".join(L) + "\n")


STATUSES_ORDER = ("Out", "Doubtful", "Questionable")
