"""Team-stat factors model with 10,000 simulations per game (docs/factors_v7_preregistration.md).

Nine season-to-date metrics per team (offense, and what the defense allowed), not opponent-adjusted, centered by
the previous season's league mean; two Poisson regressions (TDs, FGs) fit on 2006-2021 weeks 3-18; 10,000 Monte
Carlo games per matchup. Scored on 2022-2024 (Test A), 2025 (Test B) and the 2026 live games.

Run:  python -m engine.backtest.factors_v7 --cache <dir with pbp_<season>.parquet>
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
import polars as pl

from engine import config
from engine.backtest.players_eval import H, LAM, fit_offset_poisson, v1_rates
from engine.data import nflverse
from engine.models import projection as P

METRICS = ("epa", "pass", "rush", "sr", "expl", "sack", "third", "rz", "ppd")
FEATURES = [f"off_{m}" for m in METRICS] + [f"def_{m}" for m in METRICS]
FIRST, TRAIN, TEST_A, TEST_B, LIVE = 2005, (2006, 2021), (2022, 2024), 2025, 2026
MIN_WEEK, MAX_WEEK = 3, 18
N_SIM, SEED = 10_000, 20261102
LL_FLOOR = 1e-4
MG = np.arange(-P.MAXP, P.MAXP + 1)


def _team(c: str) -> pl.Expr:
    return pl.col(c).replace(P.FRANCHISE)


# ---------------------------------------------------------------- metrics

def game_sums(pbp: pl.DataFrame) -> pl.DataFrame:
    """One row per (game_id, team) on offense with numerator/denominator sums for every metric."""
    pbp = pbp.filter(pl.col("season_type") == "REG")
    p = pbp.filter(pl.col("play_type").is_in(["pass", "run"]), pl.col("two_point_attempt").fill_null(0) == 0,
                   pl.col("epa").is_not_null(), pl.col("posteam").is_not_null()) \
        .with_columns(_team("posteam").alias("team"),
                      (pl.col("qb_dropback").fill_null(0) == 1).alias("db"),
                      ((pl.col("play_type") == "run") & (pl.col("qb_scramble").fill_null(0) == 0)).alias("dr"))
    p = p.with_columns((((pl.col("db")) & (pl.col("yards_gained").fill_null(0) >= 20))
                        | ((pl.col("dr")) & (pl.col("yards_gained").fill_null(0) >= 10))).alias("ex"))
    plays = p.group_by("game_id", "team").agg(
        pl.col("epa").sum().alias("epa_n"), pl.len().alias("epa_d"),
        pl.col("epa").filter(pl.col("db")).sum().alias("pass_n"), pl.col("db").sum().alias("pass_d"),
        pl.col("epa").filter(pl.col("dr")).sum().alias("rush_n"), pl.col("dr").sum().alias("rush_d"),
        pl.col("success").fill_null(0).sum().alias("sr_n"), pl.len().alias("sr_d"),
        pl.col("ex").sum().alias("expl_n"), pl.len().alias("expl_d"),
        pl.col("sack").fill_null(0).filter(pl.col("db")).sum().alias("sack_n"), pl.col("db").sum().alias("sack_d"),
        pl.col("third_down_converted").fill_null(0).filter(pl.col("down") == 3).sum().alias("third_n"),
        (pl.col("down") == 3).sum().alias("third_d"))
    # drives: keyed by (game, fixed_drive); the drive team is the posteam of its first scrimmage play
    scrim = pl.col("play_type").is_in(["pass", "run", "qb_kneel", "qb_spike"])
    d = pbp.filter(pl.col("fixed_drive").is_not_null(), pl.col("posteam").is_not_null())
    dt = d.filter(scrim).group_by("game_id", "fixed_drive", maintain_order=True).agg(
        _team("posteam").first().alias("team"),
        pl.col("play_type").is_in(["pass", "run"]).sum().alias("n_real"),
        pl.col("drive_inside20").max().alias("in20"),
        pl.col("fixed_drive_result").first().alias("res"))
    conv = d.with_columns(_team("posteam").alias("pt")).group_by("game_id", "fixed_drive", "pt").agg(
        ((pl.col("extra_point_result") == "good").sum() + 2 * (pl.col("two_point_conv_result") == "success").sum())
        .alias("conv"))
    dt = dt.filter(pl.col("n_real") > 0) \
        .join(conv, left_on=["game_id", "fixed_drive", "team"], right_on=["game_id", "fixed_drive", "pt"], how="left") \
        .with_columns(pl.when(pl.col("res") == "Touchdown").then(6 + pl.col("conv").fill_null(0).clip(0, 2))
                      .when(pl.col("res") == "Field goal").then(3).otherwise(0).alias("pts"))
    drives = dt.group_by("game_id", "team").agg(
        pl.col("pts").sum().alias("ppd_n"), pl.len().alias("ppd_d"),
        ((pl.col("in20") == 1) & (pl.col("res") == "Touchdown")).sum().alias("rz_n"),
        (pl.col("in20") == 1).sum().alias("rz_d"))
    return plays.join(drives, on=["game_id", "team"], how="full", coalesce=True).fill_null(0)


def team_weeks(sums: pl.DataFrame, sched: pl.DataFrame) -> pl.DataFrame:
    """Team-game rows (REG) with own offensive sums (o_*) and sums allowed (a_*)."""
    s = sched.filter(pl.col("game_type") == "REG").select(
        "game_id", "season", "week", _team("home_team").alias("home"), _team("away_team").alias("away"))
    rows = pl.concat([s.select("game_id", "season", "week", pl.col("home").alias("team"), pl.col("away").alias("opp")),
                      s.select("game_id", "season", "week", pl.col("away").alias("team"), pl.col("home").alias("opp"))])
    cols = [c for c in sums.columns if c not in ("game_id", "team")]
    off = sums.select("game_id", "team", *[pl.col(c).alias(f"o_{c}") for c in cols])
    alw = sums.select("game_id", pl.col("team").alias("opp"), *[pl.col(c).alias(f"a_{c}") for c in cols])
    return rows.join(off, on=["game_id", "team"], how="inner").join(alw, on=["game_id", "opp"], how="inner")


def league_means(tw: pl.DataFrame) -> dict:
    out = {}
    for (season,), g in tw.group_by("season"):
        out[int(season)] = {m: float(g[f"o_{m}_n"].sum() / g[f"o_{m}_d"].sum()) for m in METRICS}
    return out


def season_to_date(tw: pl.DataFrame) -> pl.DataFrame:
    """Per (season, team, week): pooled values from the team's games in earlier weeks of that season."""
    sumc = [c for c in tw.columns if c.startswith(("o_", "a_"))]
    t = tw.sort("season", "team", "week")
    t = t.with_columns([(pl.col(c).cum_sum().over("season", "team") - pl.col(c)).alias(c) for c in sumc])
    return t.with_columns(
        *[(pl.col(f"o_{m}_n") / pl.col(f"o_{m}_d")).alias(f"so_{m}") for m in METRICS],
        *[(pl.col(f"a_{m}_n") / pl.col(f"a_{m}_d")).alias(f"sa_{m}") for m in METRICS],
        (pl.col("o_epa_d") > 0).alias("_any")).select("season", "week", "team", *[f"so_{m}" for m in METRICS],
                                                      *[f"sa_{m}" for m in METRICS])


def season_to_date_at(tw: pl.DataFrame, season: int, week: int) -> pl.DataFrame:
    """Values for a week computed from weeks < week only (used by the point-in-time check)."""
    past = tw.filter(pl.col("season") == season, pl.col("week") < week)
    g = past.group_by("team").agg([pl.col(c).sum() for c in past.columns if c.startswith(("o_", "a_"))])
    return g.select("team", *[(pl.col(f"o_{m}_n") / pl.col(f"o_{m}_d")).alias(f"so_{m}") for m in METRICS],
                    *[(pl.col(f"a_{m}_n") / pl.col(f"a_{m}_d")).alias(f"sa_{m}") for m in METRICS])


def features(tw: pl.DataFrame, std: pl.DataFrame, means: dict) -> pl.DataFrame:
    """Per team-game: the team's offensive values and the opponent's values allowed, centered by the previous
    season's league mean. Rows with any missing value are dropped (reported)."""
    base = tw.select("game_id", "season", "week", "team", "opp")
    own = std.select("season", "week", "team", *[pl.col(f"so_{m}").alias(f"off_{m}") for m in METRICS])
    opp = std.select("season", "week", pl.col("team").alias("opp"), *[pl.col(f"sa_{m}").alias(f"def_{m}") for m in METRICS])
    f = base.join(own, on=["season", "week", "team"], how="left").join(opp, on=["season", "week", "opp"], how="left")
    prev = pl.DataFrame([{"season": s + 1, **{f"mu_{m}": v[m] for m in METRICS}} for s, v in means.items()])
    f = f.join(prev, on="season", how="left")
    return f.with_columns(*[(pl.col(f"off_{m}") - pl.col(f"mu_{m}")).alias(f"off_{m}") for m in METRICS],
                          *[(pl.col(f"def_{m}") - pl.col(f"mu_{m}")).alias(f"def_{m}") for m in METRICS]) \
        .drop([f"mu_{m}" for m in METRICS]).with_columns([pl.col(c).fill_nan(None) for c in FEATURES])


# ---------------------------------------------------------------- model

def fit(train: pl.DataFrame) -> dict:
    X = train.select(FEATURES).to_numpy().astype(float)
    mu, sd = X.mean(0), X.std(0)
    Z = np.column_stack([train["home"].to_numpy().astype(float), (X - mu) / sd])
    out = {"mu": mu.tolist(), "sd": sd.tolist()}
    for k in ("td", "fg"):
        b, se = fit_offset_poisson(Z, train[k].to_numpy().astype(float), np.zeros(len(Z)))
        out[k] = {"b": b.tolist(), "se": se.tolist()}
    td = float(train["td"].sum())
    extra = (train["pts"] - 6 * train["td"] - train["pat"] - 3 * train["fg"] - 2 * train["saf"]).to_numpy()
    p_2 = float(np.clip(np.clip(extra, 0, 2).sum() / 2 / td, 0, 0.15))
    out["p_xp"] = min(float(train["pat"].sum()) / td, 1 - p_2)
    out["p_2"] = p_2
    return out


def rates(m: dict, row: dict) -> tuple[float, float]:
    x = (np.array([row[f] for f in FEATURES], float) - np.array(m["mu"])) / np.array(m["sd"])
    z = np.r_[1.0, float(row["home"]), x]
    return float(math.exp(z @ np.array(m["td"]["b"]))), float(math.exp(z @ np.array(m["fg"]["b"])))


def simulate(rng: np.random.Generator, lam_td: float, lam_fg: float, p_xp: float, p_2: float, n=N_SIM) -> np.ndarray:
    td = rng.poisson(lam_td, n)
    conv = rng.multinomial(td, [1 - p_xp - p_2, p_xp, p_2])
    return 6 * td + conv[:, 1] + 2 * conv[:, 2] + 3 * rng.poisson(lam_fg, n)


# ---------------------------------------------------------------- evaluation helpers

def cover_probs_sim(margins: np.ndarray, line: float) -> tuple[float, float]:
    return float((margins > -line).mean()), float((margins < -line).mean())


def cover_probs_pmf(pmf: np.ndarray, line: float) -> tuple[float, float]:
    return float(pmf[MG > -line].sum()), float(pmf[MG < -line].sum())


def ats_record(rows: list[dict], line_key: str, pick_key: str) -> dict:
    w = l = 0
    for r in rows:
        line = r.get(line_key)
        if line is None or (isinstance(line, float) and math.isnan(line)):
            continue
        m = r["margin"]
        if m == -line:
            continue
        home_cov = m > -line
        if (r[pick_key] == "home") == home_cov:
            w += 1
        else:
            l += 1
    n = w + l
    r_ = w / n if n else float("nan")
    return {"W": w, "L": l, "N": n, "win_rate": r_, "z_vs_50": (w - n / 2) / math.sqrt(n / 4) if n else None}


def paired(rows: list[dict], line_key: str, a: str, b: str) -> dict:
    """On games where picks a and b differ (and no push): wins for a; z vs 50%."""
    w = n = 0
    for r in rows:
        line = r.get(line_key)
        if line is None or r[a] == r[b] or r["margin"] == -line:
            continue
        n += 1
        w += int((r[a] == "home") == (r["margin"] > -line))
    return {"differ": n, "a_wins": w, "b_wins": n - w, "z": (w - n / 2) / math.sqrt(n / 4) if n else None}


def summarize(rows: list[dict], key: str) -> dict:
    """Score accuracy for projection `key` (fields <key>_h, <key>_a, <key>_ll)."""
    pm = np.array([r[f"{key}_h"] - r[f"{key}_a"] for r in rows])
    pt = np.array([r[f"{key}_h"] + r[f"{key}_a"] for r in rows])
    am = np.array([r["margin"] for r in rows]); at = np.array([r["total"] for r in rows])
    sc = np.array([abs(r[f"{key}_h"] - r["hs"]) for r in rows] + [abs(r[f"{key}_a"] - r["as"]) for r in rows])
    out = {"n": len(rows), "team_score_mae": float(sc.mean()), "margin_mae": float(np.abs(pm - am).mean()),
           "total_mae": float(np.abs(pt - at).mean()), "margin_bias": float((pm - am).mean()),
           "total_bias": float((pt - at).mean()),
           "winner_rate": float(np.mean([np.sign(p) == np.sign(a) for p, a in zip(pm, am) if a != 0]))}
    if all(f"{key}_ll" in r for r in rows):
        out["margin_ll"] = float(np.mean([r[f"{key}_ll"] for r in rows]))
    return out


# ---------------------------------------------------------------- run

def load(cache: str, log=print) -> dict:
    import nflreadpy as nfl
    sched, _ = nflverse.pull("schedules", save=False)
    sched = sched.filter(pl.col("season").is_between(FIRST, LIVE))
    sums = pl.concat([game_sums(pl.read_parquet(Path(cache) / f"pbp_{s}.parquet")) for s in range(FIRST, LIVE + 1)])
    ts = nfl.load_team_stats(seasons=list(range(FIRST, LIVE + 1)))
    games = P.team_games(ts, sched)
    log(f"team-game sums: {sums.height}; team-games with scores: {games.height}")
    return {"sched": sched, "sums": sums, "games": games}


def run(cache: str, log=print) -> dict:
    ctx = load(cache, log)
    sched, games = ctx["sched"], ctx["games"]
    tw = team_weeks(ctx["sums"], sched)
    means = league_means(tw)
    std = season_to_date(tw)
    feat = features(tw, std, means)
    df = games.select("game_id", "season", "week", "team", "opp", "home", "td", "fg", "pat", "saf", "pts") \
        .join(feat.drop("season", "week", "opp"), on=["game_id", "team"], how="left") \
        .filter(pl.col("week").is_between(MIN_WEEK, MAX_WEEK))
    n_all = df.height
    df_ok = df.drop_nulls(FEATURES)
    bad_games = set(df.filter(pl.any_horizontal([pl.col(f).is_null() for f in FEATURES]))["game_id"].to_list())
    df_ok = df_ok.filter(~pl.col("game_id").is_in(list(bad_games)))
    log(f"team-games weeks {MIN_WEEK}-{MAX_WEEK}: {n_all}; games dropped for a missing value: {len(bad_games)}")
    miss = df.select([pl.col(f).is_null().sum().alias(f) for f in FEATURES]).row(0, named=True)
    log("missing by feature: " + str({k: v for k, v in miss.items() if v}))
    log("dropped by season: " + str(df.filter(pl.col("game_id").is_in(list(bad_games))).group_by("season").len().sort("season").rows()))

    # ---- validation 1: point in time
    rng_chk = np.random.default_rng(7)
    pit_fail, pit_n = 0, 0
    for s in range(TRAIN[0], TEST_B + 1):
        g = df_ok.filter(pl.col("season") == s)
        for i in rng_chk.choice(g.height, 2, replace=False):
            r = g.row(int(i), named=True)
            at = season_to_date_at(tw, s, r["week"])
            own = at.filter(pl.col("team") == r["team"]).row(0, named=True)
            opp = at.filter(pl.col("team") == r["opp"]).row(0, named=True)
            for m in METRICS:
                pit_n += 2
                pit_fail += abs(own[f"so_{m}"] - means[s - 1][m] - r[f"off_{m}"]) > 1e-12
                pit_fail += abs(opp[f"sa_{m}"] - means[s - 1][m] - r[f"def_{m}"]) > 1e-12
    log(f"point-in-time check: {pit_fail} mismatches in {pit_n} values")

    train = df_ok.filter(pl.col("season").is_between(*TRAIN))
    model = fit(train)
    log(f"fit on {train.height} team-games; p_xp {model['p_xp']:.4f} p_2 {model['p_2']:.4f}")

    # ---- validation 3: sanity
    lam = [rates(model, r) for r in train.iter_rows(named=True)]
    proj_pts = np.mean([lt * (6 + model["p_xp"] + 2 * model["p_2"]) + 3 * lf for lt, lf in lam])
    act_pts = float((6 * train["td"] + train["pat"] + 3 * train["fg"]).mean())
    eos = tw.filter(pl.col("season").is_between(*TRAIN)).group_by("season", "team").agg(
        (pl.col("o_ppd_n").sum() / pl.col("o_ppd_d").sum()).alias("ppd"))
    ppg = games.filter(pl.col("season").is_between(*TRAIN)).group_by("season", "team").agg(pl.col("pts").mean())
    j = eos.join(ppg, on=["season", "team"])
    ppd_corr = float(np.corrcoef(j["ppd"].to_numpy(), j["pts"].to_numpy())[0, 1])
    log(f"sanity: projected {proj_pts:.2f} vs actual {act_pts:.2f} (TD/FG points); ppd vs ppg corr {ppd_corr:.3f}")

    # ---- per-game projections for the test seasons
    rng = np.random.default_rng(SEED)
    test = df_ok.filter(pl.col("season") >= TEST_A[0])
    by_game: dict = {}
    for r in test.iter_rows(named=True):
        by_game.setdefault(r["game_id"], {})[("h" if r["home"] == 1 else "a")] = r
    sch = {r["game_id"]: r for r in sched.iter_rows(named=True)}
    v1 = _v1(games, test.filter(pl.col("season") <= TEST_B), log)
    rows, sim_check = [], []
    for gid in sorted(by_game, key=lambda g: (sch[g]["season"], sch[g]["week"], g)):
        pair = by_game[gid]
        if "h" not in pair or "a" not in pair:
            continue
        s = sch[gid]
        hl, al = rates(model, pair["h"]), rates(model, pair["a"])
        hp = simulate(rng, *hl, model["p_xp"], model["p_2"])
        ap = simulate(rng, *al, model["p_xp"], model["p_2"])
        sim_check.append(abs(hp.mean() - (hl[0] * (6 + model["p_xp"] + 2 * model["p_2"]) + 3 * hl[1])))
        mg = hp - ap
        margin = int(s["home_score"] - s["away_score"])
        close = -float(s["spread_line"]) if s["spread_line"] is not None else None
        row = {"game_id": gid, "season": s["season"], "week": s["week"], "home": s["home_team"], "away": s["away_team"],
               "hs": int(s["home_score"]), "as": int(s["away_score"]), "margin": margin,
               "total": int(s["home_score"] + s["away_score"]), "close": close, "close_total": s["total_line"],
               "v7_h": float(hp.mean()), "v7_a": float(ap.mean()),
               "v7_ll": math.log(max(float((mg == margin).mean()), LL_FLOOR)), "_mg": mg}
        if close is not None:
            ph, pa = cover_probs_sim(mg, close)
            row["v7_pick_close"] = "home" if ph > pa else "away"
            row["v7_p_home_close"] = ph / (ph + pa) if ph + pa else 0.5
        if gid in v1:
            pmf_h, pmf_a = v1[gid]
            x = np.arange(P.MAXP + 1)
            mpmf = np.convolve(pmf_h, pmf_a[::-1]); mpmf /= mpmf.sum()
            row.update({"v1_h": float(pmf_h @ x), "v1_a": float(pmf_a @ x),
                        "v1_ll": math.log(max(float(mpmf[MG == margin][0]), LL_FLOOR)), "_v1pmf": mpmf})
            if close is not None:
                ph, pa = cover_probs_pmf(mpmf, close)
                row["v1_pick_close"] = "home" if ph > pa else "away"
        rows.append(row)
    log(f"simulation check: mean |sim mean - analytic| = {np.mean(sim_check):.3f} points over {len(sim_check)} teams")

    res = {"validation": {"point_in_time_mismatches": pit_fail, "point_in_time_values": pit_n,
                          "sim_vs_analytic_mean_abs": float(np.mean(sim_check)),
                          "train_projected_pts": float(proj_pts), "train_actual_pts": act_pts,
                          "ppd_vs_ppg_corr": ppd_corr, "games_dropped_missing": len(bad_games),
                          "train_team_games": train.height},
           "model": {"features": FEATURES, "td": model["td"], "fg": model["fg"], "p_xp": model["p_xp"],
                     "p_2": model["p_2"]}}

    # ---- Test A and Test B vs close and v1
    for name, (lo, hi) in (("test_a", TEST_A), ("test_b", (TEST_B, TEST_B))):
        rr = [r for r in rows if lo <= r["season"] <= hi and "v1_h" in r]
        out = {"v7": summarize(rr, "v7"), "v1": summarize(rr, "v1")}
        cl = [r for r in rr if r["close"] is not None]
        out["market"] = {"margin_mae": float(np.mean([abs(-r["close"] - r["margin"]) for r in cl])),
                         "total_mae": float(np.mean([abs(r["close_total"] - r["total"]) for r in cl
                                                     if r["close_total"] is not None])), "n": len(cl)}
        out["ats_close_v7"] = ats_record(cl, "close", "v7_pick_close")
        out["ats_close_v1"] = ats_record(cl, "close", "v1_pick_close")
        out["paired_close_v7_vs_v1"] = paired(cl, "close", "v7_pick_close", "v1_pick_close")
        res[name] = out

    # ---- Test B: CBS open vs the live model's 2025 picks
    hold = list(csv.DictReader(open(config.ROOT / "data/backtests/holdout2025_games.csv")))
    hb = {h["game_id"]: h for h in hold}
    cb = []
    for r in rows:
        if r["season"] != TEST_B or r["game_id"] not in hb or hb[r["game_id"]]["cbs_open"] in ("", None):
            continue
        line = float(hb[r["game_id"]]["cbs_open"])
        ph, pa = cover_probs_sim(r["_mg"], line)
        cb.append({"margin": r["margin"], "cbs": line, "v7": "home" if ph > pa else "away",
                   "live": hb[r["game_id"]]["pick"]})
    res["test_b"]["cbs_open"] = {"v7": ats_record(cb, "cbs", "v7"), "live": ats_record(cb, "cbs", "live"),
                                 "paired_v7_vs_live": paired(cb, "cbs", "v7", "live")}

    # ---- 2026 live: pool line, official pick, logged v1 / v3
    res["live_2026"], live_rows = _live(rows)
    games_out = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    return {"results": res, "games": games_out, "live_rows": live_rows}


def _v1(games: pl.DataFrame, target: pl.DataFrame, log) -> dict:
    """Walk-forward v1 point pmfs (as frozen: H=8, lambda=5) for the Test A/B games."""
    t = target.select("game_id", "season", "week", "team", "opp", "home").sort("season", "week")
    r = v1_rates(games, t)
    log(f"v1 walk-forward rates: {r.height} team-games")
    home = dict(zip(t["game_id"].to_list(), [None] * t.height))
    side = {(g, tm): h for g, tm, h in zip(t["game_id"], t["team"], t["home"])}
    out: dict = {}
    for x in r.iter_rows(named=True):
        pmf = P.points_pmf(x["lam_td"], x["lam_fg"], x["p_xp"], x["p_2"])
        out.setdefault(x["game_id"], [None, None])[0 if side[(x["game_id"], x["team"])] == 1 else 1] = pmf
    del home
    return {g: (h, a) for g, (h, a) in out.items() if h is not None and a is not None}


def _live(rows: list[dict]) -> tuple[dict, list[dict]]:
    pred = list(csv.DictReader(open(config.ROOT / "data/predictions/predictions.csv")))
    latest = {}
    for p in pred:
        latest[p["game_id"]] = p                               # file order: later rows supersede
    proj = list(csv.DictReader(open(config.ROOT / "data/predictions/projections.csv")))
    pj: dict = {}
    for p in proj:
        pj.setdefault(p["game_id"], {})[p["model_version"]] = p
    live = []
    for r in rows:
        if r["season"] != LIVE or r["game_id"] not in latest:
            continue
        p = latest[r["game_id"]]
        if p["league_line"] in ("", None) or p["pick"] not in ("home", "away"):
            continue
        line = float(p["league_line"])
        ph, pa = cover_probs_sim(r["_mg"], line)
        x = {"game_id": r["game_id"], "week": r["week"], "home": r["home"], "away": r["away"], "hs": r["hs"],
             "as": r["as"], "margin": r["margin"], "total": r["total"], "pool_line": line,
             "v7_h": r["v7_h"], "v7_a": r["v7_a"], "v7": "home" if ph > pa else "away",
             "v7_p_home": ph / (ph + pa) if ph + pa else 0.5, "official": p["pick"]}
        for key, mv in (("v1", "proj-poisson-v1"), ("v3", "proj-players-v3")):
            q = pj.get(r["game_id"], {}).get(mv)
            if q:
                x[f"{key}_h"], x[f"{key}_a"] = float(q["proj_home_pts"]), float(q["proj_away_pts"])
                x[key] = "home" if float(q["proj_p_home_cover"]) > 0.5 else "away"
        live.append(x)
    both = [x for x in live if "v1_h" in x and "v3_h" in x]
    out = {"n_official": len(live), "pool_line": {
        "v7": ats_record(live, "pool_line", "v7"), "official": ats_record(live, "pool_line", "official"),
        "paired_v7_vs_official": paired(live, "pool_line", "v7", "official")},
        "scores_same_games": {"n": len(both), "v7": summarize(both, "v7"), "v1": summarize(both, "v1"),
                              "v3": summarize(both, "v3")}}
    if both:
        out["pool_line"]["v1"] = ats_record(both, "pool_line", "v1")
        out["pool_line"]["v3"] = ats_record(both, "pool_line", "v3")
        out["pool_line"]["v7_same_games"] = ats_record(both, "pool_line", "v7")
    return out, live


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", default=str(config.ROOT / "data/backtests/factors_v7.json"))
    a = ap.parse_args()
    o = run(a.cache)
    Path(a.out).write_text(json.dumps(o["results"], indent=1, default=float))
    Path(a.out).with_name("factors_v7_games.json").write_text(
        json.dumps({"games": o["games"], "live_2026": o["live_rows"]}, default=float))
    print(json.dumps(o["results"], indent=1, default=float)[:200])


if __name__ == "__main__":
    main()
