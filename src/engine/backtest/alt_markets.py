"""Three real-money market tests, each pre-registered before any result:

- teasers through 3 and 7 (docs/teaser_preregistration.md)
- second-half (halftime) lines (docs/halftime_preregistration.md)
- predicting the open-to-close move and betting the opener (docs/move_preregistration.md)

None of these touches the pool pick. Prices are not in the data: single bets are graded at an assumed -110
(break-even 52.38%), teasers at a 2-team 6-point price of -120 (per-leg break-even 73.85%), -110 also reported.

Sign conventions as in the rest of the engine: a home spread S is negative when home is favored; margin =
home - away; home covers S if margin > -S.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from pathlib import Path

import numpy as np
import polars as pl
from bs4 import BeautifulSoup

from engine import config
from engine.data import nflverse, sbro

BE_SINGLE = 110 / 210                     # -110 single bet


def teaser_breakeven(price: float, legs: int = 2) -> float:
    """Per-leg win rate at which a `legs`-team teaser at American `price` breaks even (independent legs)."""
    dec = 1 + (100 / -price if price < 0 else price / 100)
    return (1 / dec) ** (1 / legs)


# --------------------------------------------------------------------------------------------- data

def schedule() -> tuple[pl.DataFrame, str]:
    return nflverse.pull("schedules", save=False)


def reg_games(sched: pl.DataFrame) -> pl.DataFrame:
    """Completed regular-season games with a closing spread: one row per game, home perspective."""
    return (sched.filter(pl.col("game_type") == "REG", pl.col("result").is_not_null(),
                         pl.col("spread_line").is_not_null())
            .select("game_id", "season", "week", "gameday", "home_team", "away_team",
                    pl.col("result").alias("margin"), (-pl.col("spread_line")).alias("close"),
                    pl.col("total_line").alias("total"))
            .sort("season", "week", "game_id"))


# ------------------------------------------------------------------------------------------ teasers

WONG_DOG = (1.5, 2.0, 2.5)                # side's closing spread (positive = underdog), teased to +7.5..+8.5
WONG_FAV = (-7.5, -8.0, -8.5)             # teased to -1.5..-2.5
TEASE = 6.0


def teaser_legs(g: pl.DataFrame) -> pl.DataFrame:
    """Every Wong-window side at the close. A game has at most one (its two sides are +s and -s)."""
    rows = []
    for r in g.iter_rows(named=True):
        for side, s, m in (("home", r["close"], r["margin"]), ("away", -r["close"], -r["margin"])):
            if s in WONG_DOG or s in WONG_FAV:
                x = m + s + TEASE
                rows.append({"game_id": r["game_id"], "season": r["season"], "week": r["week"], "side": side,
                             "spread": s, "teased": s + TEASE, "kind": "dog" if s > 0 else "fav",
                             "total": r["total"], "half": s % 1 != 0,
                             "result": "W" if x > 0 else ("P" if x == 0 else "L")})
    return pl.DataFrame(rows, schema={"game_id": pl.Utf8, "season": pl.Int64, "week": pl.Int64, "side": pl.Utf8,
                                      "spread": pl.Float64, "teased": pl.Float64, "kind": pl.Utf8,
                                      "total": pl.Float64, "half": pl.Boolean, "result": pl.Utf8})


# -------------------------------------------------------------------------------- SBRO, full columns

def _num(v: str) -> float | None:
    v = v.strip().lower()
    if v in ("pk", "pick", "pk'"):
        return 0.0
    try:
        return float(v)
    except ValueError:
        return None


def _split_2h(a: str, b: str) -> tuple[int | None, float | None, float | None, str]:
    """2H column: one row holds the second-half spread (favorite's row), the other the second-half total.
    The larger number is the total. Returns (index of the spread row, spread, total, status)."""
    x, y = _num(a), _num(b)
    if x is None or y is None:
        return None, None, None, "unparsable"
    if x == y:
        return None, None, None, "ambiguous"
    i, sp, tot = (0, x, y) if x < y else (1, y, x)
    if not (0 <= sp <= 21 and 10 <= tot <= 45):
        return None, None, None, "out_of_range"
    return i, sp, tot, "ok"


def parse_page_full(html: str, season: int) -> list[dict]:
    """sbro.parse_page plus quarter scores, closing moneylines and the second-half line."""
    base = sbro.parse_page(html, season)
    t = BeautifulSoup(html, "lxml").find("table")
    rows = [[c.get_text(strip=True) for c in r.find_all(["td", "th"])] for r in t.find_all("tr")]
    hdr, body = rows[0], rows[1:]
    ix = {k: hdr.index(k) for k in ("1st", "2nd", "3rd", "4th", "Final", "ML", "2H")}
    out = []
    for rec, r1, r2 in zip(base, body[0::2], body[1::2]):
        rec = dict(rec)
        try:
            q1 = [int(r1[ix[k]]) for k in ("1st", "2nd", "3rd", "4th")]
            q2 = [int(r2[ix[k]]) for k in ("1st", "2nd", "3rd", "4th")]
            rec["h1_team1"], rec["h1_team2"] = q1[0] + q1[1], q2[0] + q2[1]
            rec["ot_team1"], rec["ot_team2"] = rec["score1"] - sum(q1), rec["score2"] - sum(q2)
            rec["quarters_status"] = "ok" if rec["ot_team1"] >= 0 and rec["ot_team2"] >= 0 else "quarters_exceed_final"
        except ValueError:
            rec["h1_team1"] = rec["h1_team2"] = rec["ot_team1"] = rec["ot_team2"] = None
            rec["quarters_status"] = "unparsable"
        i, sp, tot, st = _split_2h(r1[ix["2H"]], r2[ix["2H"]])
        rec["h2_team1_spread"] = None if i is None else (-sp if i == 0 else sp)
        rec["h2_total"], rec["h2_status"] = tot, st
        for k, r in (("ml1", r1), ("ml2", r2)):
            try:
                rec[k] = float(r[ix["ML"]])
            except ValueError:
                rec[k] = None
        out.append(rec)
    return out


def sbro_full(sched: pl.DataFrame, raw_dir: Path | None = None) -> pl.DataFrame:
    """One row per matched SBRO game, oriented to the nflverse home team."""
    raw_dir = raw_dir or config.ROOT / "data" / "raw" / "sbro"
    rows = []
    for f in sorted(raw_dir.glob("nfl-odds-*.html")):
        season = int(re.search(r"nfl-odds-(\d{4})", f.name).group(1))
        rows += parse_page_full(f.read_text(), season)
    m = sbro.match_schedule(pl.DataFrame(rows, infer_schema_length=None), sched)
    m = m.filter(pl.col("match_status").is_in(["ok", "score_mismatch_sbro_score_ignored"]))
    out = []
    for r in m.iter_rows(named=True):
        t1_home = r["home_team"] in sbro.resolve(r["team1_raw"], r["season"])
        h, a = ("1", "2") if t1_home else ("2", "1")
        h2s = r["h2_team1_spread"]
        out.append({
            "game_id": r["game_id"], "season": r["season"], "week": r["week"],
            "open": r["open_home_spread"], "sbro_close": r["close_home_spread"],
            "h1_margin": None if r["h1_team1"] is None else r[f"h1_team{h}"] - r[f"h1_team{a}"],
            # second half includes overtime: final score minus first-half points
            "h2_margin": None if r["h1_team1"] is None else
            (r[f"score{h}"] - r[f"h1_team{h}"]) - (r[f"score{a}"] - r[f"h1_team{a}"]),
            "h2_spread": None if h2s is None else (h2s if t1_home else -h2s),
            "h2_total": r["h2_total"], "h2_status": r["h2_status"], "quarters_status": r["quarters_status"],
            "ml_home": r[f"ml{h}"], "ml_away": r[f"ml{a}"], "match_status": r["match_status"]})
    return pl.DataFrame(out, infer_schema_length=None)


# ------------------------------------------------------------------------------ ratings (move test)

def ratings_before(g: pl.DataFrame, season: int, week: int, target: str, lam: float, window: int = 16
                   ) -> tuple[dict, float] | None:
    """Ridge least squares, target = HFA + r_home - r_away, on the last `window` played weeks before
    (season, week). target = 'line' fits the closing lines' expected margin (-close); 'margin' fits results."""
    key = g["season"] * 100 + g["week"]
    prior = g.filter(key < season * 100 + week)
    if prior.height == 0:
        return None
    wk = (prior["season"] * 100 + prior["week"]).unique().sort()
    keep = wk.tail(window).to_list()
    p = prior.filter((pl.col("season") * 100 + pl.col("week")).is_in(keep))
    teams = sorted(set(p["home_team"].to_list()) | set(p["away_team"].to_list()))
    ti = {t: i for i, t in enumerate(teams)}
    n, k = p.height, len(teams)
    X = np.zeros((n, k + 1))
    X[:, k] = 1.0
    for r, (h, a) in enumerate(zip(p["home_team"].to_list(), p["away_team"].to_list())):
        X[r, ti[h]], X[r, ti[a]] = 1.0, -1.0
    y = (-p["close"].to_numpy()) if target == "line" else p["margin"].to_numpy().astype(float)
    P = np.eye(k + 1) * lam
    P[k, k] = 0.0                                     # home advantage is not shrunk
    beta = np.linalg.solve(X.T @ X + P, X.T @ y)
    return {t: beta[ti[t]] for t in teams}, float(beta[k])


def rating_lines(g: pl.DataFrame, target: str, lam: float, seasons: tuple[int, int]) -> pl.DataFrame:
    """Predicted home spread for every game in `seasons`, from data before its week."""
    out = []
    for (s, w), grp in g.filter(pl.col("season").is_between(*seasons)).group_by(["season", "week"]):
        fit = ratings_before(g, s, w, target, lam)
        if fit is None:
            continue
        r, hfa = fit
        for gid, h, a in zip(grp["game_id"].to_list(), grp["home_team"].to_list(), grp["away_team"].to_list()):
            if h in r and a in r:
                out.append({"game_id": gid, "pred": -(hfa + r[h] - r[a])})
    return pl.DataFrame(out)


# ------------------------------------------------------------------------------------------- stats

def week_boot(season: np.ndarray, week: np.ndarray, stat, n: int = 4000, seed: int = 7) -> tuple[float, float]:
    """2.5% and 97.5% quantiles of stat(idx), resampling whole weeks."""
    rng = np.random.default_rng(seed)
    wk = season * 100 + week
    ids = np.unique(wk)
    groups = [np.where(wk == w)[0] for w in ids]
    vals = np.empty(n)
    for b in range(n):
        pick = rng.integers(0, len(ids), len(ids))
        vals[b] = stat(np.concatenate([groups[j] for j in pick]))
    return float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975))


def record(won: np.ndarray, season: np.ndarray, week: np.ndarray, breakeven: float) -> dict:
    """Win rate with a week-clustered 95% interval; PASS if the lower end (one-sided 97.5%) clears breakeven."""
    won = won.astype(float)
    n = len(won)
    if n == 0:
        return {"n": 0}
    rate = float(won.mean())
    lo, hi = week_boot(season, week, lambda ix: won[ix].mean())
    return {"n": n, "wins": int(won.sum()), "rate": rate, "ci95": [lo, hi], "breakeven": breakeven,
            "z_vs_50": (rate - 0.5) / math.sqrt(0.25 / n), "pass": lo > breakeven}


# ------------------------------------------------------------------------------------------- tests

def run_teasers(g: pl.DataFrame) -> dict:
    legs = teaser_legs(g)
    be120, be110 = teaser_breakeven(-120), teaser_breakeven(-110)
    out = {"breakeven_-120": be120, "breakeven_-110": be110}
    for era, (lo, hi) in {"2015_2025": (2015, 2025), "1999_2014": (1999, 2014)}.items():
        e = legs.filter(pl.col("season").is_between(lo, hi))
        h = e.filter(pl.col("half"))
        med = float(h["total"].median()) if h.height else None
        sets = {"H1_all_half_point_legs": h, "H2_total_at_or_below_median": h.filter(pl.col("total") <= med)}
        res = {"median_total": med}
        for name, d in sets.items():
            won = (d["result"] == "W").to_numpy()
            res[name] = record(won, d["season"].to_numpy(), d["week"].to_numpy(), be120)
            res[name]["beats_-110"] = res[name]["n"] > 0 and res[name]["ci95"][0] > be110
            res[name]["by_kind"] = {k: {"n": d.filter(pl.col("kind") == k).height,
                                        "rate": float((d.filter(pl.col("kind") == k)["result"] == "W").mean())
                                        if d.filter(pl.col("kind") == k).height else None}
                                    for k in ("dog", "fav")}
        w = e.filter(~pl.col("half"))
        res["whole_number_legs"] = {"n": w.height, "W": int((w["result"] == "W").sum()),
                                    "P": int((w["result"] == "P").sum()), "L": int((w["result"] == "L").sum())}
        out[era] = res
    return out


def run_halftime(g: pl.DataFrame, sb: pl.DataFrame) -> dict:
    d = (sb.filter(pl.col("h2_status") == "ok", pl.col("quarters_status") == "ok")
         .join(g.select("game_id", "close"), on="game_id")
         .with_columns((-pl.col("h2_spread")).alias("l2"), (-pl.col("close")).alias("c")))
    # home covers the 2H line if h2_margin > -h2_spread; pushes dropped
    d = d.with_columns((pl.col("h2_margin") + pl.col("h2_spread")).alias("x")).filter(pl.col("x") != 0)
    d = d.with_columns((pl.col("x") > 0).alias("home_cov"))
    fit_d = d.filter(pl.col("season").is_between(2007, 2014))
    test = d.filter(pl.col("season").is_between(2015, 2021))
    out = {"games_used": {"fit_2007_2014": fit_d.height, "test_2015_2021": test.height}}
    # H1: back the team trailing at halftime
    t = test.filter(pl.col("h1_margin") != 0)
    bet_home = (t["h1_margin"] < 0).to_numpy()
    won = bet_home == t["home_cov"].to_numpy()
    out["H1_back_halftime_trailer"] = record(won, t["season"].to_numpy(), t["week"].to_numpy(), BE_SINGLE)
    # H2: OLS fitted on 2007-2014, bet the side of (prediction - 2H line) on 2015-2021
    X = np.column_stack([np.ones(fit_d.height), fit_d["l2"], fit_d["c"], fit_d["h1_margin"]]).astype(float)
    beta, *_ = np.linalg.lstsq(X, fit_d["h2_margin"].to_numpy().astype(float), rcond=None)
    Xt = np.column_stack([np.ones(test.height), test["l2"], test["c"], test["h1_margin"]]).astype(float)
    edge = Xt @ beta - test["l2"].to_numpy()
    keep = edge != 0
    won2 = (edge[keep] > 0) == test["home_cov"].to_numpy()[keep]
    out["H2_regression_side"] = record(won2, test["season"].to_numpy()[keep], test["week"].to_numpy()[keep], BE_SINGLE)
    out["H2_coefficients_2007_2014"] = dict(zip(["const", "h2_line", "pregame_close", "h1_margin"], map(float, beta)))
    return out


MOVE_MODELS = {"A_market_memory": ("line", 1.0), "B_margin_rating": ("margin", 20.0)}
MOVE_K = 1.0


def close_on_open_and_pred(close: np.ndarray, open_: np.ndarray, pred: np.ndarray) -> float:
    """Coefficient on pred in OLS close = a + b*open + c*pred. Regressing (close - open) on (pred - open)
    instead is biased by the shared open term: a useless pred gets a positive slope when the open is noisy."""
    X = np.column_stack([np.ones(len(close)), open_, pred])
    return float(np.linalg.lstsq(X, close, rcond=None)[0][2])


def run_move(g: pl.DataFrame, sb: pl.DataFrame, seasons: tuple[int, int] = (2007, 2021)) -> dict:
    d = sb.filter(pl.col("open").is_not_null()).join(g.select("game_id", "close", "margin"), on="game_id")
    d = d.filter(pl.col("season").is_between(*seasons))
    out = {"games_with_open": d.height}
    for name, (target, lam) in MOVE_MODELS.items():
        pr = rating_lines(g, target, lam, seasons)
        e = d.join(pr, on="game_id").with_columns((pl.col("pred") - pl.col("open")).alias("D"))
        cl, op, pd_ = e["close"].to_numpy(), e["open"].to_numpy(), e["pred"].to_numpy()
        s, w = e["season"].to_numpy(), e["week"].to_numpy()
        coef = lambda ix: close_on_open_and_pred(cl[ix], op[ix], pd_[ix])  # noqa: E731
        res = {"games": e.height, "pred_coef_on_close": coef(np.arange(len(cl))),
               "pred_coef_ci95": list(week_boot(s, w, coef, n=2000))}
        bet = np.abs(e["D"].to_numpy()) >= MOVE_K
        b = e.filter(pl.Series(bet))
        bet_home = (b["D"] < 0).to_numpy()                 # ratings want home more favored than the open
        x = b["margin"].to_numpy() + b["open"].to_numpy()
        keep = x != 0
        won = bet_home[keep] == (x[keep] > 0)
        res["bet_at_open_|D|>=1"] = record(won, b["season"].to_numpy()[keep], b["week"].to_numpy()[keep], BE_SINGLE)
        toward = np.where(bet_home, b["open"].to_numpy() - b["close"].to_numpy(),
                          b["close"].to_numpy() - b["open"].to_numpy())
        res["close_moved_toward_bet"] = {"share_toward": float((toward > 0).mean()),
                                         "share_away": float((toward < 0).mean()),
                                         "mean_points": float(toward.mean())}
        out[name] = res
    return out


def run(out_path: Path | None = None) -> dict:
    import json

    sched, sid = schedule()
    g = reg_games(sched)
    sb = sbro_full(sched)
    res = {"generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "nflverse_snapshot": sid,
           "teasers": run_teasers(g.filter(pl.col("season") <= 2025)),
           "halftime": run_halftime(g, sb), "move": run_move(g, sb)}
    out_path = out_path or config.ROOT / "data" / "backtests" / "alt_markets.json"
    out_path.write_text(json.dumps(res, indent=1, default=str))
    return res
