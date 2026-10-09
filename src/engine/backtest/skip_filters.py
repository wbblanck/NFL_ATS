"""Skip filters (docs/skip_filters_preregistration.md): each model's pool pick, bet at the closing line at -110, only on the
games a pre-listed rule keeps. Every (model, rule) is reported; Holm across the family, on confirmation seasons, decides.

The no-filter baseline of each model must reproduce data/backtests/bettable.json exactly; `main` checks it."""
from __future__ import annotations

import json
import math

import numpy as np
import polars as pl

from engine import config
from engine.backtest import bettable as B
from engine.backtest import patterns as P
from engine.data import nflverse
from engine.picks import hybrid

BE = B.BREAK_EVEN
MIN_N = 200
TOTAL_CUT = 45.0
WEEK_CUT = 8
PROB_CUTS = {"P1": 0.52, "P2": 0.54, "P3": 0.56}


def _seasons(a: int, b: int) -> set[int]:
    return set(range(a, b + 1))


# (discovery seasons, confirmation seasons); Hybrid's selection years 2014-2019 are excluded entirely.
WINDOWS = {
    "official": (_seasons(2008, 2016), _seasons(2017, 2025)),
    "keynum": (_seasons(2007, 2016), _seasons(2017, 2021)),
    "v1": (_seasons(2007, 2016), _seasons(2017, 2021)),
    "hybrid": (_seasons(2007, 2013), {2020, 2021}),
    "v3": (set(), set()),           # descriptive only: all of 2022-2025 is reported, no split
}
FAMILY = ("official", "keynum", "v1", "hybrid")

DESC = {
    "BASE": "no filter (bet every pick)",
    "M1": "move > 0 (skip no-move games)", "M2": "move >= 1", "M3": "move >= 2", "M4": "move >= 3 (Max)",
    "M5": "move < 1 (Lean only)", "M6": "move < 2 (Lean and Solid)", "M7": "move < 3 (skip Max)",
    "P1": "cover probability >= 0.52", "P2": "cover probability >= 0.54", "P3": "cover probability >= 0.56",
    "K1": "a 3 or 7 is crossed", "K2": "no 3 or 7 crossed",
    "S1": "|stale spread| <= 3", "S2": "3 < |stale spread| <= 7", "S3": "|stale spread| > 7",
    "U1": "pick is the favorite on the stale line", "U2": "pick is the underdog on the stale line",
    "T1": "closing total >= 45", "T2": "closing total < 45",
    "W1": "week <= 8", "W2": "week >= 9",
    "D1": "division game", "D2": "not a division game",
    "A1": "live, key-number and v1 all pick the same side", "A2": "not all three pick the same side",
}


def masks(m: dict) -> dict[str, np.ndarray]:
    """Rule ID -> boolean keep-mask over one model's picks. `m` holds arrays: pick_home, stale and close (home spreads),
    week, total (nan when missing), div; optionally prob (probability the pick covers) and agree."""
    stale, close = m["stale"], m["close"]
    move = np.abs(close - stale)
    a, b = np.abs(stale), np.abs(close)
    cross = np.zeros(len(stale), bool)
    for k in (3, 7):
        cross |= (np.minimum(a, b) < k) & (k < np.maximum(a, b))
    fav = (m["pick_home"] & (stale < 0)) | (~m["pick_home"] & (stale > 0))
    dog = (m["pick_home"] & (stale > 0)) | (~m["pick_home"] & (stale < 0))
    out = {
        "M1": move > 0, "M2": move >= 1, "M3": move >= 2, "M4": move >= 3,
        "M5": move < 1, "M6": move < 2, "M7": move < 3,
        "K1": cross, "K2": ~cross,
        "S1": a <= 3, "S2": (a > 3) & (a <= 7), "S3": a > 7,
        "U1": fav, "U2": dog,
        "T1": m["total"] >= TOTAL_CUT, "T2": m["total"] < TOTAL_CUT,
        "W1": m["week"] <= WEEK_CUT, "W2": m["week"] > WEEK_CUT,
        "D1": m["div"], "D2": ~m["div"],
    }
    if "prob" in m:
        for rid, c in PROB_CUTS.items():
            out[rid] = m["prob"] >= c
    if "agree" in m:
        out["A1"] = m["agree"]
        out["A2"] = ~m["agree"]
    return out


def _stats(g: np.ndarray, sel: np.ndarray) -> dict:
    """g: +1 win, -1 loss, 0 push (pushes are left out). Returns the record, return and one-sided z vs break-even."""
    w = int(((g == 1) & sel).sum())
    l = int(((g == -1) & sel).sum())
    n = w + l
    out = {"n": n, "W": w, "L": l, "win_rate": None, "ci_lo": None, "ci_hi": None, "roi": None, "z": None,
           "p_one_sided": None}
    if n:
        r = w / n
        z = (r - BE) / math.sqrt(BE * (1 - BE) / n)
        lo, hi = B.wilson(w, n)
        out.update(win_rate=r, ci_lo=lo, ci_hi=hi, roi=(w * B.WIN + l * B.LOSS) / n, z=z,
                   p_one_sided=0.5 * math.erfc(z / math.sqrt(2)))
    return out


def _schedule() -> pl.DataFrame:
    s, _ = nflverse.pull("schedules", save=False)
    return s.filter(pl.col("game_type") == "REG").select(
        "game_id", pl.col("week").alias("wk"), pl.col("total_line").cast(pl.Float64), pl.col("div_game").cast(pl.Boolean))


def _model(df: pl.DataFrame, stale_col: str, pick_home, prob=None, agree=None) -> dict:
    stale = df[stale_col].cast(pl.Float64).to_numpy()
    close = df["close"].cast(pl.Float64).to_numpy()
    margin = df["margin"].cast(pl.Float64).to_numpy()
    m = {"pick_home": np.asarray(pick_home, bool), "stale": stale, "close": close, "week": df["wk"].to_numpy(),
         "total": df["total_line"].cast(pl.Float64).fill_null(float("nan")).to_numpy(),
         "div": df["div_game"].cast(pl.Boolean).fill_null(False).to_numpy()}
    if prob is not None:
        m["prob"] = np.asarray(prob, float)
    if agree is not None:
        m["agree"] = np.asarray(agree, bool)
    return {"m": m, "season": df["season"].to_numpy(), "g": B.grade(m["pick_home"], margin, close),
            "gs": B.grade(m["pick_home"], margin, stale)}


def build() -> dict:
    sched = _schedule()
    out = {}
    off = P.dataset().join(sched, on="game_id", how="left")
    ph = (off["p_live"] > 0.5).to_numpy()
    p = off["p_live"].to_numpy()
    out["official"] = _model(off, "line", ph, np.where(ph, p, 1 - p))
    fr = B.frame().join(sched, on="game_id", how="left")
    live_h = (fr["p_live"] > 0.5).to_numpy()
    key_h = (fr["p_key"] > 0.5).to_numpy()
    v1_h = (fr["p_v1"] > 0.5).to_numpy()
    agree = (live_h == key_h) & (key_h == v1_h)
    pk, pv = fr["p_key"].to_numpy(), fr["p_v1"].to_numpy()
    out["keynum"] = _model(fr, "open", key_h, np.where(key_h, pk, 1 - pk), agree)
    out["v1"] = _model(fr, "open", v1_h, np.where(v1_h, pv, 1 - pv), agree)
    drift = fr["close"].to_numpy() - fr["open"].to_numpy()
    out["hybrid"] = _model(fr, "open", np.where(np.abs(drift) >= hybrid.MIN_MOVE, live_h, v1_h), None, agree)
    v = pl.read_csv(config.ROOT / "data" / "backtests" / "v3_history.csv").join(sched, on="game_id", how="left")
    p3 = v["p_v3"].to_numpy()
    h3 = p3 > 0.5
    out["v3"] = _model(v, "line", h3, np.where(h3, p3, 1 - p3))
    return out


def run() -> dict:
    built = build()
    rows, fam_p = [], {}
    baseline = {}
    for name, bm in built.items():
        m, season, g, gs = bm["m"], bm["season"], bm["g"], bm["gs"]
        disc, conf = WINDOWS[name]
        allw = disc | conf
        ALL = np.isin(season, sorted(allw)) if allw else np.ones(len(g), bool)
        DISC = np.isin(season, sorted(disc)) if disc else np.zeros(len(g), bool)
        CONF = np.isin(season, sorted(conf)) if conf else np.zeros(len(g), bool)
        rules = {"BASE": np.ones(len(g), bool), **masks(m)}
        for rid, sel in rules.items():
            sa, sd, sc = _stats(g, sel & ALL), _stats(g, sel & DISC), _stats(g, sel & CONF)
            pool = _stats(gs, sel & CONF)
            in_fam = name in FAMILY and rid != "BASE" and sc["n"] >= MIN_N
            key = f"{name}|{rid}"
            if in_fam:
                fam_p[key] = sc["p_one_sided"]
            row = {"model": name, "rule": rid, "description": DESC[rid], "in_family": in_fam,
                   "all_n": sa["n"], "all_W": sa["W"], "all_L": sa["L"], "all_win": sa["win_rate"], "all_roi": sa["roi"],
                   "disc_n": sd["n"], "disc_win": sd["win_rate"], "disc_roi": sd["roi"],
                   "conf_n": sc["n"], "conf_win": sc["win_rate"], "conf_ci_lo": sc["ci_lo"], "conf_ci_hi": sc["ci_hi"],
                   "conf_roi": sc["roi"], "conf_z": sc["z"], "conf_p": sc["p_one_sided"],
                   "pool_conf_win": pool["win_rate"]}
            rows.append(row)
            if rid == "BASE":
                baseline[name] = {"all": sa, "disc": sd, "conf": sc}
    ok = B.holm(fam_p) if fam_p else {}
    for r in rows:
        key = f"{r['model']}|{r['rule']}"
        r["holm_pass"] = bool(ok[key]) if r["in_family"] else None
        r["disc_above_be"] = bool(r["disc_win"] is not None and r["disc_win"] > BE and r["disc_n"] >= MIN_N)
        r["real"] = bool(r["in_family"] and r["holm_pass"] and r["disc_above_be"])
    real = [f"{r['model']}|{r['rule']}" for r in rows if r["real"]]
    top = {}
    for name in FAMILY:
        fam = [r for r in rows if r["model"] == name and r["in_family"]]
        top[name] = [{"rule": r["rule"], "description": r["description"], "conf_n": r["conf_n"],
                      "conf_win": r["conf_win"], "conf_z": r["conf_z"], "disc_win": r["disc_win"],
                      "holm_pass": r["holm_pass"]} for r in sorted(fam, key=lambda r: -r["conf_z"])[:5]]
    return {"family_size": len(fam_p), "holm_pass": int(sum(ok.values())), "real": real, "rows": rows,
            "baseline": baseline, "top": top, "min_n": MIN_N, "break_even": BE}


def check_against_bettable(res: dict) -> dict:
    """The no-filter baselines must equal the bettable backtest (same picks, same games, same bet)."""
    bt = json.loads((config.ROOT / "data" / "backtests" / "bettable.json").read_text())["models"]
    want = {"official": bt["live"]["all"], "keynum": bt["keynum"]["all"], "v1": bt["v1"]["all"],
            "hybrid": bt["hybrid"]["decision"]}
    out = {}
    for name, w in want.items():
        got = res["baseline"][name]["all"]
        out[name] = {"expected": [w["W"], w["L"]], "got": [got["W"], got["L"]],
                     "match": got["W"] == w["W"] and got["L"] == w["L"]}
    return out


FIELDS = ["model", "rule", "description", "in_family", "all_n", "all_W", "all_L", "all_win", "all_roi", "disc_n",
          "disc_win", "disc_roi", "conf_n", "conf_win", "conf_ci_lo", "conf_ci_hi", "conf_roi", "conf_z", "conf_p",
          "holm_pass", "disc_above_be", "real", "pool_conf_win"]


def main() -> int:
    res = run()
    chk = check_against_bettable(res)
    out_csv = config.ROOT / "data" / "backtests" / "skip_filters.csv"
    pl.DataFrame(res["rows"]).select(FIELDS).write_csv(out_csv)
    out_json = config.ROOT / "data" / "backtests" / "skip_filters.json"
    out_json.write_text(json.dumps({**{k: v for k, v in res.items() if k != "rows"}, "check": chk}, indent=1, default=float))
    print(out_csv)
    print("baseline reproduces bettable.json:", {k: v["match"] for k, v in chk.items()})
    print(f"family tests: {res['family_size']}  Holm pass: {res['holm_pass']}  real skip rules: {res['real'] or 'none'}")
    for name in FAMILY:
        print(name, "top 3 by confirmation z:",
              [(t["rule"], round(t["conf_win"] * 100, 1), t["conf_n"], round(t["conf_z"], 2)) for t in res["top"][name][:3]])
    return 0 if all(v["match"] for v in chk.values()) else 1
