"""Batch 6 (docs/batch6_preregistration.md): the nfl-betting-model batch 3-5 models against the CBS pool line.

  python scripts/batch6.py reproduce <cache>  2022-2025 weeks 2-18 against nflverse's closing spread: checks the
                                              registered numbers from nfl-betting-model and prints the per-game SDs
                                              used for power; writes data/gamesim/batch6_reproduce.json
  python scripts/batch6.py test <cache>       2026 weeks 10-18 against the pool line, run once after week 18 is final;
                                              refuses earlier; writes data/gamesim/batch6.json
<cache> gets nflverse schedules, injuries and play-by-play 1999-2026 on first use (2026 refreshed).
Research only: reads data/lines/league_lines.csv and data/predictions/predictions.csv, never writes to them.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import polars as pl
import xgboost as xgb

from engine.data import league_lines
from engine.gamesim import batch5 as B5, elo as E, kalman as KF, personnel as P, tdfg as T, xgb as X

ROOT = Path(__file__).resolve().parents[1]
K = ROOT / "data" / "gamesim"
SEASONS = list(range(1999, 2027))
B, ALPHA, MIN_GAMES = 2000, 0.05, 100
TEST_WEEKS, DESC_WEEKS = range(10, 19), range(2, 10)
# Values the deterministic tie-break (smallest QB id) gives on 2022-2025 weeks 2-18 vs the close, pinned 2026-11-12 before any
# week 10-18 result (the rule was chosen first; the numbers are what it produced, not tuned toward the registered ones).
TIE_SENSITIVE = {"mae_eloqb_expected": 9.92322, "mae_xgb": 10.00478}
FAMILY = ("Q", "X")
COLS = ["season_type", "qb_dropback", "qb_epa", "passer_player_id", "rusher_player_id", "posteam", "defteam",
        "game_id", "game_date", "season", "week", "epa", "play_type"]

_spec = importlib.util.spec_from_file_location("batch2", ROOT / "scripts" / "batch2.py")
B2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B2)
home_covers, pick_home, record, binom_p, binom_lower = B2.home_covers, B2.pick_home, B2.record, B2.binom_p, B2.binom_lower


def cache(d: Path, refresh: bool = True):
    import nflreadpy as nfl

    d.mkdir(parents=True, exist_ok=True)
    for s in SEASONS:
        f = d / f"pbp_{s}.parquet"
        if not f.exists() or (refresh and s == 2026):
            nfl.load_pbp(seasons=[s]).select(COLS).write_parquet(f)
    if refresh or not (d / "schedules.parquet").exists():
        nfl.load_schedules(seasons=SEASONS).write_parquet(d / "schedules.parquet")
        nfl.load_injuries(seasons=list(range(2009, 2027))).write_parquet(d / "injuries.parquet")


# ---------------------------------------------------------------- probabilities and scoring
def p_home_cover(pm, ms, spread):
    """P(home covers) with pushes removed. pm: (G, len(ms)) margin probabilities; spread canonical (home line)."""
    t = -np.asarray(spread, float)[:, None]
    over = (pm * (ms[None, :] > t)).sum(1)
    push = (pm * (ms[None, :] == t)).sum(1)
    return np.clip(over / (1 - push), 1e-12, 1 - 1e-12)


def logloss(p, y):
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def boot_mean(v, seed=7):
    """Game-level bootstrap of the mean (batch 2 addendum: nine week clusters are too few)."""
    rng = np.random.default_rng(seed)
    n = len(v)
    return np.array([v[rng.integers(0, n, n)].mean() for _ in range(B)])


# ---------------------------------------------------------------- forecasts
def frame(d: Path, last: int):
    """Every regular-season game of seasons <= last with a result: Elo, Elo + QB (expected starter), XGBoost fair
    home margins (nflverse sign: positive = home wins by that much), plus margin distributions."""
    ek = json.loads((K / "elo_constants.json").read_text())
    k1 = json.loads((K / "batch1_constants.json").read_text())
    k3 = json.loads((K / "batch3_constants.json").read_text())
    k5 = json.loads((K / "batch5_constants.json").read_text())
    gk = json.loads((K / "gamesim_constants.json").read_text())
    sched = pl.read_parquet(d / "schedules.parquet").filter(pl.col("season") <= last)
    games = E.prep(sched)
    lvl = E.scoring_level(games)
    r = E.run(games, ek["k"], ek["h"], ek["c"]).join(lvl, on="game_id")
    mh, ma = E.means(r["d"], r["level"], ek["b"])
    f = r.select("game_id", pl.col("d").alias("elo_d"), "level", pl.Series("elo_fair", mh - ma))
    kf, _, _ = KF.run(games, k1["kalman"])
    f = f.join(kf.select("game_id", "kalman", "kalman_var"), on="game_id")
    pbp = pl.concat([pl.read_parquet(d / f"pbp_{s}.parquet", columns=COLS) for s in range(1999, last + 1)],
                    how="diagonal_relaxed")
    qg = P.qb_games(pbp)
    inj = pl.read_parquet(d / "injuries.parquet").filter(pl.col("game_type") == "REG", pl.col("season") <= last)
    rater = P.QBRater(qg, gk["personnel"]["replacement"])

    def qb_deltas(first_injury_season):
        # As registered: batch 3 G1 read injury reports from 2022 on, batch 4 from 2015 on (its cache). Earlier
        # seasons then fall back to "last game's starter", which moves Elo + QB's carried-over ratings slightly.
        e = T.expected_starters(sched, qg, inj.filter(pl.col("season") >= first_injury_season), P.FRANCHISE, P._day)
        return P.qb_delta(e, qg, rater).with_columns(pl.col("team").replace(E.FRANCHISE))
    # Elo + QB with the expected starter (batch 3 G1)
    eq = k1["eloqb"]
    q3 = qb_deltas(2022)
    qb = {(g, t): v for g, t, v in zip(q3["game_id"], q3["team"], q3["qb_delta"])}
    rq = E.run(games, eq["k"], eq["h"], eq["c"], qb, eq["q"]).join(lvl, on="game_id")
    qh, qa = E.means(rq["d"], rq["level"], eq["b"])
    f = f.join(rq.select("game_id", pl.Series("eloqb", qh - qa)), on="game_id")
    # XGBoost features (batch 4 build)
    qbd = qb_deltas(2015)
    roll = X.rolling_epa(pbp.filter(pl.col("season") >= 2010))
    FR = E.FRANCHISE
    s = sched.filter(pl.col("game_type") == "REG", pl.col("result").is_not_null()).with_columns(
        pl.col("home_team").replace(FR).alias("ht"), pl.col("away_team").replace(FR).alias("at"),
        pl.col("roof").is_in(["dome", "closed"]).cast(int).alias("dome"), pl.col("div_game").cast(int))
    s = s.join(games.select("game_id", pl.col("neutral").cast(int)), on="game_id").join(f, on="game_id")
    s = s.join(qbd.select("game_id", pl.col("team").alias("ht"), pl.col("qb_delta").alias("qb_h")), on=["game_id", "ht"], how="left") \
        .join(qbd.select("game_id", pl.col("team").alias("at"), pl.col("qb_delta").alias("qb_a")), on=["game_id", "at"], how="left") \
        .join(roll.select("game_id", pl.col("team").alias("ht"), pl.col("off8").alias("off8_h"), pl.col("def8").alias("def8_h")),
              on=["game_id", "ht"], how="left") \
        .join(roll.select("game_id", pl.col("team").alias("at"), pl.col("off8").alias("off8_a"), pl.col("def8").alias("def8_a")),
              on=["game_id", "at"], how="left").sort("game_id")
    booster = xgb.Booster()
    booster.load_model(str(K / "batch4_model.json"))
    s = s.with_columns(pl.Series("xgb", booster.predict(xgb.DMatrix(s.select(X.FEATURES).to_numpy().astype(float)))))
    return s, ek, k3, k5


def dists(x: pl.DataFrame, ek, k3, k5) -> dict:
    """Margin distributions per game (rows aligned with x): NB (batch 2 Elo), TD/FG, S1, K1."""
    dd, lv = x["elo_d"].to_numpy(), x["level"].to_numpy()
    mh, ma = E.means(dd, lv, ek["b"])
    full, nb = E.margin_dist(E.nb_pmf(mh, ek["theta"]), E.nb_pmf(ma, ek["theta"]))
    th, ta = T.game_pmfs(dd, lv, k3)
    _, td = E.margin_dist(th, ta)
    s1 = B5.s1_margin(dd, lv, k3, k5["s1"]["c0"])
    k1 = B5.k1_dist(x["elo_fair"].to_numpy(), k5["k1"]["sigma"], k5["k1"]["w"])
    return {"nb": (full, nb), "tdfg": (full, td), "s1": (full, s1), "k1": (B5.M, k1)}


SIDES = {"elo": "elo_fair", "eloqb": "eloqb", "xgb": "xgb"}


def score(x: pl.DataFrame, pm: dict, spread_col: str) -> dict:
    """Per model: side record and margin MAE; per distribution: cover log loss and side record. spread canonical."""
    y = x.drop_nulls(spread_col)
    keep = x[spread_col].is_not_null().to_numpy()
    m = y["result"].to_numpy().astype(float)
    sp = y[spread_col].to_numpy().astype(float)
    out = {"games": x.height, "with_line": y.height, "line_mae": float(np.abs(-sp - m).mean()) if y.height else None}
    for name, col in SIDES.items():
        rr = record(y[col].to_numpy(), sp, m)
        out[name] = {"correct": int(np.nansum(rr)), "graded": int(np.sum(~np.isnan(rr))),
                     "rate": float(np.nanmean(rr)) if np.any(~np.isnan(rr)) else None,
                     "mae": float(np.abs(x[col].to_numpy() - x["result"].to_numpy()).mean())}
    c = home_covers(m, sp)
    ok = ~np.isnan(c)
    ln2 = math.log(2)
    for name, (ms, p) in pm.items():
        pc = p_home_cover(p[keep][ok], ms, sp[ok])
        ll = logloss(pc, c[ok])
        side = np.where(pc > 0.5, 1.0, np.where(pc < 0.5, 0.0, np.nan))
        hit = np.where(np.isnan(side), np.nan, (side == c[ok]).astype(float))
        out[name] = {"n": int(ok.sum()), "cover_logloss": float(ll.mean()), "gain_vs_coin": float((ln2 - ll).mean()),
                     "sd_gain": float((ln2 - ll).std()), "side_correct": int(np.nansum(hit)),
                     "side_graded": int(np.sum(~np.isnan(hit))), "_v": ln2 - ll}
    return out


def strip(o):
    return {k: (strip(v) if isinstance(v, dict) else v) for k, v in o.items() if not k.startswith("_")}


# ---------------------------------------------------------------- commands
def reproduce(d, refresh: bool = True):
    d = Path(d)
    cache(d, refresh)
    s, ek, k3, k5 = frame(d, 2025)
    x = s.filter(pl.col("season").is_between(2022, 2025), pl.col("week").is_between(2, 18)) \
        .drop_nulls(["spread_line", "home_spread_odds", "away_spread_odds"]).sort("game_id") \
        .with_columns((-pl.col("spread_line")).alias("close"))
    pm = dists(x, ek, k3, k5)
    sc = score(x, pm, "close")
    m = x["result"].to_numpy().astype(int)
    share = {}
    for v in (3, 7, 14):
        share[v] = {"actual": float(np.mean(np.abs(m) == v)),
                    **{k: float(p[:, np.abs(ms) == v].sum(1).mean()) for k, (ms, p) in pm.items()}}
    # registered numbers in nfl-betting-model (batch 3, 4, 5 reports), 1,023 games / 994 without a push
    reg = {"games": 1023, "mae_elo": 9.964, "mae_eloqb_expected": 9.921, "mae_xgb": 10.003,
           "ll_nb": 0.7129, "ll_tdfg": 0.7077, "ll_s1": 0.7117, "ll_k1": 0.7168,
           "share3_tdfg": 0.056, "share3_s1": 0.064, "share3_k1": 0.143}
    got = {"games": x.height, "mae_elo": sc["elo"]["mae"], "mae_eloqb_expected": sc["eloqb"]["mae"],
           "mae_xgb": sc["xgb"]["mae"], "ll_nb": sc["nb"]["cover_logloss"], "ll_tdfg": sc["tdfg"]["cover_logloss"],
           "ll_s1": sc["s1"]["cover_logloss"], "ll_k1": sc["k1"]["cover_logloss"],
           "share3_tdfg": share[3]["tdfg"], "share3_s1": share[3]["s1"], "share3_k1": share[3]["k1"]}
    tol = {k: (0 if k == "games" else 0.0006) for k in reg}  # registered numbers are rounded
    # The expected-starter QB depended on an arbitrary tie-break when two QBs had the same dropbacks in the previous game
    # (audit 2026-11-09). Ties now go to the smallest id. The two MAEs that read the expected starter therefore (a) must
    # still be near the numbers registered in nfl-betting-model (within 0.006, the spread seen across tie resolutions) and
    # (b) must equal the pinned values the fixed rule produces, which makes this check deterministic. See the amendment
    # in docs/batch6_preregistration.md.
    for k in TIE_SENSITIVE:
        tol[k] = 0.006
    check = {k: {"registered": reg[k], "here": got[k], "ok": abs(got[k] - reg[k]) <= tol[k]} for k in reg}
    for k, v in TIE_SENSITIVE.items():
        check[k + "_pinned"] = {"registered": v, "here": got[k], "ok": abs(got[k] - v) <= 0.00002}
    power = {n: {"sd_gain": sc[n]["sd_gain"], "se_130": sc[n]["sd_gain"] / math.sqrt(130)} for n in ("tdfg", "s1", "k1", "nb")}
    res = {"check": check, "all_ok": all(v["ok"] for v in check.values()), "margin_share": share,
           "power": power, "vs_close": strip(sc)}
    (K / "batch6_reproduce.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    if not res["all_ok"]:
        raise SystemExit("reproduction failed: see check")


def pool_and_picks(x: pl.DataFrame) -> pl.DataFrame:
    lines = pl.DataFrame([{"game_id": r["game_id"], "pool": float(r["spread"]), "at": r["recorded_at"]}
                          for r in league_lines.load()]).sort("at").unique("game_id", keep="last").drop("at")
    picks = pl.read_csv(ROOT / "data" / "predictions" / "predictions.csv", infer_schema_length=0) \
        .filter(pl.col("supersedes").is_null() | (pl.col("supersedes") == "")) \
        .select("game_id", "pick").unique("game_id", keep="last")
    return x.join(lines, on="game_id", how="left").join(picks, on="game_id", how="left").sort("game_id")


def holm(res: dict) -> dict:
    order = sorted(res, key=lambda n: res[n]["p"])
    stop = False
    for i, n in enumerate(order):
        lvl = ALPHA / (len(order) - i)
        ok = (not stop) and res[n]["p"] <= lvl and res[n]["n"] >= MIN_GAMES
        res[n].update({"holm_level": lvl, "pass": bool(ok)})
        stop = stop or not ok
    return res


def run_tests(x: pl.DataFrame, pm: dict) -> dict:
    """The two registered tests (Q, X; Holm) and the descriptive cover log loss of TD/FG, S1 and K1 against the pool
    line, on frame x (with column pool) and its distributions pm."""
    sc = score(x, pm, "pool")
    res = {}
    for name, col in (("Q", "eloqb"), ("X", "xgb")):
        k, n = sc[col]["correct"], sc[col]["graded"]
        res[name] = {"model": col, "n": n, "correct": k, "rate": k / n if n else None, "p": binom_p(k, n) if n else 1.0}
    res = holm(res)
    for name in FAMILY:
        r = res[name]
        r["lower_bound"] = binom_lower(r["correct"], r["n"], r["holm_level"]) if r["n"] else None
    desc = {}
    for dist in ("tdfg", "s1", "k1", "nb"):
        v = sc[dist]["_v"]
        dr = boot_mean(v) if len(v) else np.array([0.0])
        desc[dist] = {"n": len(v), "cover_logloss": sc[dist]["cover_logloss"],
                      "gain_vs_coin": float(v.mean()) if len(v) else None,
                      "interval_90": [float(np.quantile(dr, 0.05)), float(np.quantile(dr, 0.95))]}
    res["cover_logloss_descriptive"] = desc
    return res


def test(d):
    d = Path(d)
    cache(d)
    sched = pl.read_parquet(d / "schedules.parquet").filter(pl.col("season") == 2026, pl.col("game_type") == "REG",
                                                              pl.col("week").is_in(list(TEST_WEEKS)))
    if sched.height == 0 or sched.filter(pl.col("result").is_null()).height:
        raise SystemExit("weeks 10-18 are not all final; the test runs once, after week 18")
    s, ek, k3, k5 = frame(d, 2026)
    out = {}
    for label, weeks in (("test_weeks_10_18", TEST_WEEKS), ("desc_weeks_2_9", DESC_WEEKS)):
        x = pool_and_picks(s.filter(pl.col("season") == 2026, pl.col("week").is_in(list(weeks))))
        pm = dists(x, ek, k3, k5)
        out[label] = {"descriptive": strip(score(x, pm, "pool"))}
        if label == "test_weeks_10_18":
            xp = x.drop_nulls("pool")
            out[label]["tests"] = run_tests(xp, dists(xp, ek, k3, k5))
        off = x.drop_nulls("pool").filter(pl.col("pick").is_in(["home", "away"]))
        if off.height:
            sp = off["pool"].to_numpy().astype(float)
            out[label]["descriptive"]["agree_with_official"] = {
                c: float(np.nanmean(pick_home(off[c].to_numpy(), sp) == (off["pick"] == "home").to_numpy()))
                for c in SIDES.values()}
    (K / "batch6.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    {"reproduce": reproduce, "test": test}[sys.argv[1]](sys.argv[2])
