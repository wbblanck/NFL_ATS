"""Batch 2 (docs/batch2_preregistration.md): Elo against the CBS pool line (A2) and the Elo + simulator average (C1).

  python scripts/batch2.py describe <cache>   weeks 1-9 of 2026 and 2022-2025, descriptive; writes docs/batch2_describe.md
  python scripts/batch2.py test <cache>       weeks 10-18 of 2026, run once after week 18 is final; refuses earlier;
                                              writes docs/batch2_report.md and data/gamesim/batch2.json
<cache> gets nflverse schedules, play-by-play 2015-2026, injuries, snaps and players on first use (2026 refreshed).
Research only: reads data/lines/league_lines.csv and data/predictions/predictions.csv, never writes to them.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import polars as pl

from engine.gamesim import elo as EL, engine as E, personnel as P, run as R, teams as TM

ROOT = Path(__file__).resolve().parents[1]
K = ROOT / "data" / "gamesim"
SEASONS = list(range(2015, 2027))
SIMS, SEED, B, ALPHA = 1000, 101, 2000, 0.05
TEST_WEEKS, DESC_WEEKS = range(10, 19), range(1, 10)


def cache(d: Path, refresh: bool = True):
    import nflreadpy as nfl

    d.mkdir(parents=True, exist_ok=True)
    for s in SEASONS:
        f = d / f"pbp_{s}.parquet"
        if not f.exists() or (refresh and s == 2026):
            nfl.load_pbp(seasons=[s]).write_parquet(f)
    if refresh or not (d / "schedules.parquet").exists():
        nfl.load_schedules(seasons=list(range(1999, 2027))).write_parquet(d / "schedules.parquet")
        nfl.load_injuries(seasons=SEASONS).write_parquet(d / "injuries.parquet")
        nfl.load_snap_counts(seasons=SEASONS).write_parquet(d / "snaps.parquet")
        nfl.load_players().write_parquet(d / "players.parquet")


# ---------------------------------------------------------------- grading
def home_covers(margin, spread):
    """Canonical sign: spread = home line, negative = home favored. Returns 1 cover, 0 not, nan push."""
    v = np.asarray(margin, float) + np.asarray(spread, float)
    return np.where(v > 0, 1.0, np.where(v < 0, 0.0, np.nan))


def pick_home(fair, spread):
    """1 = home, 0 = away, nan = no pick (model's fair margin exactly on the line)."""
    v = np.asarray(fair, float) + np.asarray(spread, float)
    return np.where(v > 0, 1.0, np.where(v < 0, 0.0, np.nan))


def record(fair, spread, margin):
    """Per pick: 1 correct, 0 wrong, nan push or no pick."""
    p, c = pick_home(fair, spread), home_covers(margin, spread)
    return np.where(np.isnan(p) | np.isnan(c), np.nan, (p == c).astype(float))


def binom_p(k: int, n: int) -> float:
    """One-sided exact binomial p: P(X >= k | n, 1/2)."""
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n


def binom_lower(k: int, n: int, alpha: float) -> float:
    """One-sided exact (Clopper-Pearson) lower bound of the cover rate."""
    lo, hi = 0.0, k / n if n else 0.0
    for _ in range(60):
        mid = (lo + hi) / 2
        tail = sum(math.comb(n, i) * mid ** i * (1 - mid) ** (n - i) for i in range(k, n + 1))
        lo, hi = (mid, hi) if tail < alpha else (lo, mid)
    return lo


def boot(fn, cl, seed=7):
    ids = np.unique(cl)
    grp = [np.where(cl == c)[0] for c in ids]
    rng = np.random.default_rng(seed)
    return np.array([fn(np.concatenate([grp[j] for j in rng.integers(0, len(ids), len(ids))])) for _ in range(B)])


# ---------------------------------------------------------------- forecasts
def forecasts(d: Path, season: int, weeks) -> pl.DataFrame:
    k = json.loads((K / "gamesim_constants.json").read_text())
    T = json.loads((K / "gamesim_league.json").read_text())
    ek = json.loads((K / "elo_constants.json").read_text())
    sched = pl.read_parquet(d / "schedules.parquet")
    played = sched.filter(pl.col("result").is_not_null())
    pbp = pl.concat([pl.read_parquet(d / f"pbp_{s}.parquet") for s in SEASONS], how="diagonal_relaxed")
    games = played.filter(pl.col("season") == season, pl.col("game_type") == "REG", pl.col("week").is_in(list(weeks))) \
        .select("season", "week", "game_id", "home_team", "away_team", "result", "spread_line",
                (pl.col("location") == "Neutral").alias("neutral"))
    kicks, xps = R.kick_pools(pbp)
    fac = TM.factors(TM.game_stats(pbp, T), k["league"], k["h"], k["k"], k["r"])
    qg = P.qb_games(pbp)
    pk = k["personnel"]
    qbd = P.qb_delta(sched, qg, P.QBRater(qg, pk["replacement"]))
    inj = P.injury_loss(pl.read_parquet(d / "injuries.parquet"), pl.read_parquet(d / "snaps.parquet"),
                        pl.read_parquet(d / "players.parquet"), sched)
    inp = P.inputs(qbd, inj, sched).filter(pl.col("game_id").is_in(games["game_id"].implode()))
    out, _ = R.simulate_games(games, fac, E.Tables(T), kicks, xps, k["hfa"], sims=SIMS, seed=SEED,
                              shift=P.shifts(inp, pk["coefs"]))
    eg = EL.prep(played.filter(pl.col("season") <= season))
    er = EL.run(eg, ek["k"], ek["h"], ek["c"]).join(EL.scoring_level(eg), on="game_id")
    mh, ma = EL.means(er["d"], er["level"], ek["b"])
    er = er.select("game_id", pl.Series("elo", mh - ma))
    lines = pl.read_csv(ROOT / "data" / "lines" / "league_lines.csv").select("game_id", pl.col("spread").alias("pool"))
    picks = pl.read_csv(ROOT / "data" / "predictions" / "predictions.csv", infer_schema_length=0) \
        .filter(pl.col("supersedes").is_null() | (pl.col("supersedes") == "")) \
        .select("game_id", "pick").unique("game_id", keep="last")
    x = games.join(out.select("game_id", pl.col("fair").alias("sim")), on="game_id").join(er, on="game_id") \
        .join(lines, on="game_id", how="left").join(picks, on="game_id", how="left") \
        .with_columns(((pl.col("elo") + pl.col("sim")) / 2).alias("avg"), (-pl.col("spread_line")).alias("close"))
    return x.sort("game_id")


def stats(x: pl.DataFrame) -> dict:
    y = x.drop_nulls("pool")
    m, pool = y["result"].to_numpy().astype(float), y["pool"].to_numpy().astype(float)
    out = {"games": x.height, "with_pool_line": y.height}
    for c in ("elo", "sim", "avg"):
        r = record(y[c].to_numpy(), pool, m)
        out[c] = {"correct": int(np.nansum(r)), "graded": int(np.sum(~np.isnan(r))),
                  "rate": float(np.nanmean(r)) if np.any(~np.isnan(r)) else None,
                  "mae": float(np.abs(x[c].to_numpy() - x["result"].to_numpy()).mean())}
    out["pool_mae"] = float(np.abs(-pool - m).mean()) if y.height else None
    off = y.filter(pl.col("pick").is_in(["home", "away"]))
    if off.height:
        eh = pick_home(off["elo"].to_numpy(), off["pool"].to_numpy().astype(float))
        out["elo_agrees_with_official"] = float(np.nanmean(eh == (off["pick"] == "home").to_numpy()))
        out["official_compared"] = off.height
    return out


def describe(d):
    d = Path(d)
    cache(d)
    x = forecasts(d, 2026, DESC_WEEKS)
    s = stats(x)
    g = pl.read_parquet(K / "g3_2022_2025.parquet")
    m = g["margin"].to_numpy()
    e, si = g["elo_fair"].to_numpy(), g["sim_fair"].to_numpy()
    a = (e + si) / 2
    dE, dS = np.abs(e - m) - np.abs(a - m), np.abs(si - m) - np.abs(a - m)
    hist = {"games": g.height, "mae_elo": float(np.abs(e - m).mean()), "mae_sim": float(np.abs(si - m).mean()),
            "mae_avg": float(np.abs(a - m).mean()), "sd_dE": float(dE.std()), "sd_dS": float(dS.std()),
            "se_dE_130": float(dE.std() / np.sqrt(130)), "se_dS_130": float(dS.std() / np.sqrt(130))}
    res = {"2026_weeks_1_9": s, "2022_2025": hist}
    (K / "batch2_describe.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


def test(d):
    d = Path(d)
    cache(d)
    sched = pl.read_parquet(d / "schedules.parquet").filter(pl.col("season") == 2026, pl.col("game_type") == "REG",
                                                              pl.col("week").is_in(list(TEST_WEEKS)))
    if sched.filter(pl.col("result").is_null()).height:
        raise SystemExit("weeks 10-18 are not all final; the test runs once, after week 18")
    x = forecasts(d, 2026, TEST_WEEKS)
    y = x.drop_nulls("pool")
    m, pool = y["result"].to_numpy().astype(float), y["pool"].to_numpy().astype(float)
    r = record(y["elo"].to_numpy(), pool, m)
    ok = ~np.isnan(r)
    rr = r[ok]
    res = {"A2": {"graded": int(ok.sum()), "correct": int(rr.sum()), "rate": float(rr.mean()),
                  "p": binom_p(int(rr.sum()), int(ok.sum()))}}
    mm = x["result"].to_numpy().astype(float)
    dE = np.abs(x["elo"].to_numpy() - mm) - np.abs(x["avg"].to_numpy() - mm)
    dS = np.abs(x["sim"].to_numpy() - mm) - np.abs(x["avg"].to_numpy() - mm)
    cx = np.arange(x.height)  # games as units (addendum: nine week clusters are too few for a cluster bootstrap)
    drE, drS = boot(lambda ix: dE[ix].mean(), cx), boot(lambda ix: dS[ix].mean(), cx)
    res["C1"] = {"n": x.height, "gain_vs_elo": float(dE.mean()), "gain_vs_sim": float(dS.mean()),
                 "p_vs_elo": float((drE <= 0).mean()), "p_vs_sim": float((drS <= 0).mean()), "drE": drE, "drS": drS}
    res["C1"]["p"] = max(res["C1"]["p_vs_elo"], res["C1"]["p_vs_sim"])
    order = sorted(("A2", "C1"), key=lambda n: res[n]["p"])
    stop = False
    for i, n in enumerate(order):
        lvl = ALPHA / (len(order) - i)
        passed = (not stop) and res[n]["p"] <= lvl
        res[n].update({"holm_level": lvl, "pass": bool(passed)})
        stop = stop or not passed
    res["A2"]["lower_bound"] = binom_lower(res["A2"]["correct"], res["A2"]["graded"], res["A2"]["holm_level"])
    lv = res["C1"]["holm_level"]
    res["C1"]["ci_vs_elo"] = [float(np.quantile(res["C1"].pop("drE"), q)) for q in (lv, 1 - lv)]
    res["C1"]["ci_vs_sim"] = [float(np.quantile(res["C1"].pop("drS"), q)) for q in (lv, 1 - lv)]
    res["descriptive"] = stats(x)
    (K / "batch2.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    {"describe": describe, "test": test}[sys.argv[1]](sys.argv[2])
