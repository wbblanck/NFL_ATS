"""Bettable record (docs/bettable_preregistration.md): each model's pool pick, bet at the closing line at -110.

Win = the picked team covers the nflverse closing spread; pushes are refunded and left out of the record. The
decision rule is a one-sided z against the 52.38% break-even, Holm-corrected over the four models."""
from __future__ import annotations

import json
import math

import numpy as np
import polars as pl

from engine import config
from engine.backtest import projection_eval as PE
from engine.data import sbro
from engine.models.margin_dist import MarginDist
from engine.picks import hybrid

BREAK_EVEN = 110 / 210                                   # 52.38%: win rate that pays for -110
WIN, LOSS = 100 / 110, -1.0
H, LAM = 8, 5.0                                          # v1, frozen (docs/projection_report.md)
HYBRID_SELECTION = (2014, 2019)                          # the Hybrid rule was chosen on these seasons


def grade(pick_home: np.ndarray, margin: np.ndarray, close: np.ndarray) -> np.ndarray:
    """+1 the pick covers the closing line, -1 it loses, 0 push. close is the home spread (negative = home favored)."""
    home_cover = np.sign(margin + close)
    return np.where(pick_home, home_cover, -home_cover)


def wilson(w: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return (float("nan"), float("nan"))
    p = w / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def summarize(g: np.ndarray) -> dict:
    w, l, push = int((g == 1).sum()), int((g == -1).sum()), int((g == 0).sum())
    n = w + l
    rate = w / n if n else float("nan")
    se0 = math.sqrt(BREAK_EVEN * (1 - BREAK_EVEN) / n) if n else float("nan")
    z = (rate - BREAK_EVEN) / se0 if n else float("nan")
    lo, hi = wilson(w, n)
    return {"W": w, "L": l, "push": push, "n": n, "win_rate": rate, "ci95": [lo, hi],
            "units": w * WIN + l * LOSS, "roi": (w * WIN + l * LOSS) / n if n else float("nan"),
            "z_vs_break_even": z, "p_one_sided": 0.5 * math.erfc(z / math.sqrt(2)) if n else float("nan")}


def holm(ps: dict[str, float], alpha: float = 0.05) -> dict[str, bool]:
    out, alive = {}, True
    for rank, (k, p) in enumerate(sorted(ps.items(), key=lambda kv: kv[1])):
        ok = alive and p <= alpha / (len(ps) - rank)
        out[k], alive = ok, ok
    return out


def frame() -> pl.DataFrame:
    """2007-2021 SBRO opens with the closing line, the result, and each model's cover probability (walk-forward)."""
    sched, games = PE.data()
    sb = sbro.match_schedule(sbro.load_all(config.ROOT / "data" / "raw" / "sbro"), sched) \
        .select("game_id", pl.col("open_home_spread").alias("open"))
    reg = sched.filter(pl.col("game_type") == "REG", pl.col("result").is_not_null(), pl.col("spread_line").is_not_null())
    tgt = reg.filter(pl.col("season").is_between(2007, 2021)).join(sb, on="game_id").filter(
        pl.col("open").is_not_null(), pl.col("result") != -pl.col("open"))
    pr = PE.project_games(games, tgt, H, LAM)
    ok = np.array([x is not None for x in pr])
    tgt, pr = tgt.filter(pl.Series(ok)), [x for x in pr if x is not None]
    openl = tgt["open"].to_numpy()
    p_v1 = np.array([x.p_home_cover(o) if abs(abs(o) % 1 - 0.5) < 1e-9 else
                     x.margin_pmf[np.arange(-PE.P.MAXP, PE.P.MAXP + 1) > -o].sum() for x, o in zip(pr, openl)])
    p_live, p_key = np.zeros(tgt.height), np.zeros(tgt.height)
    s = tgt["season"].to_numpy()
    for yr in range(2007, 2022):
        m = s == yr
        hist = reg.filter(pl.col("season") < yr)
        te = tgt.filter(pl.col("season") == yr)
        for kind, out in (("shifted", p_live), ("keynum", p_key)):
            md = MarginDist(kind).fit(-hist["spread_line"].to_numpy(), hist["result"].to_numpy())
            out[m] = md.sf(-te["open"].to_numpy(), -te["spread_line"].to_numpy())
    return tgt.select("game_id", "season", pl.col("result").alias("margin"), (-pl.col("spread_line")).alias("close"),
                      "open").with_columns(pl.Series("p_live", p_live), pl.Series("p_key", p_key),
                                           pl.Series("p_v1", p_v1))


def run() -> dict:
    out: dict = {"break_even": BREAK_EVEN, "models": {}}
    # --- live model: patterns.dataset(), 2008-2025 ---
    from engine.backtest import patterns as P
    d = P.dataset()
    g = grade(d["p_live"].to_numpy() > 0.5, d["margin"].to_numpy(), d["close"].to_numpy())
    s = d["season"].to_numpy()
    out["models"]["live"] = {"window": "2008-2025", "all": summarize(g),
                             "by_period": {lab: summarize(g[(s >= a) & (s <= b)]) for lab, a, b in
                                           (("2008-2013", 2008, 2013), ("2014-2024", 2014, 2024), ("2025", 2025, 2025))},
                             "vs_stale_line": summarize(np.where(d["p_live"].to_numpy() > 0.5, 1, -1) *
                                                        np.where(d["y"].to_numpy() == 1, 1, -1))}
    # --- keynum, v1, hybrid on the SBRO frame, 2007-2021 ---
    f = frame()
    margin, close, openl, season = (f[c].to_numpy() for c in ("margin", "close", "open", "season"))
    live_h, key_h, v1_h = (f[c].to_numpy() > 0.5 for c in ("p_live", "p_key", "p_v1"))
    drift = close - openl
    hyb_h = np.where(np.abs(drift) >= hybrid.MIN_MOVE, live_h, v1_h)
    in_sel = (season >= HYBRID_SELECTION[0]) & (season <= HYBRID_SELECTION[1])
    for name, pick in (("keynum", key_h), ("v1", v1_h), ("hybrid", hyb_h), ("live_sbro_frame", live_h)):
        g = grade(pick, margin, close)
        dec = ~in_sel if name == "hybrid" else np.ones_like(in_sel)
        out["models"][name] = {"window": "2007-2013 + 2020-2021" if name == "hybrid" else "2007-2021",
                               "all": summarize(g), "decision": summarize(g[dec]),
                               "by_period": {lab: summarize(g[(season >= a) & (season <= b)]) for lab, a, b in
                                             (("2007-2013", 2007, 2013), ("2014-2019", 2014, 2019), ("2020-2021", 2020, 2021))},
                               "vs_stale_line": summarize(np.where(pick, np.sign(margin + openl), -np.sign(margin + openl)))}
    # --- v3 (docs/v3_history_preregistration.md): the as-registered model on 2022-2025, same bet ---
    v3p = config.ROOT / "data" / "backtests" / "v3_history.csv"
    if v3p.exists():
        h = pl.read_csv(v3p)
        hm, hc, hl, hs = (h[c].to_numpy() for c in ("margin", "close", "line", "season"))
        for name, col in (("v3", "p_v3"), ("v1_v3_games", "p_v1"), ("live_v3_games", "p_live")):
            pick = h[col].to_numpy() > 0.5
            g = grade(pick, hm, hc)
            out["models"][name] = {"window": "2022-2025", "all": summarize(g),
                                   "by_period": {"2022-2024": summarize(g[hs <= 2024]), "2025": summarize(g[hs == 2025])},
                                   "vs_stale_line": summarize(grade(pick, hm, hl))}
    # --- decision: live (2008-2025 all), keynum, v1 (2007-2021), hybrid (outside its selection years), v3 (2022-2025);
    #     Holm over the family (four before v3 existed, five with it) ---
    dec = {"live": out["models"]["live"]["all"], "keynum": out["models"]["keynum"]["all"],
           "v1": out["models"]["v1"]["all"], "hybrid": out["models"]["hybrid"]["decision"]}
    if "v3" in out["models"]:
        dec["v3"] = out["models"]["v3"]["all"]
    ok = holm({k: v["p_one_sided"] for k, v in dec.items()})
    out["decision"] = {k: {**{kk: v[kk] for kk in ("n", "win_rate", "ci95", "roi", "z_vs_break_even", "p_one_sided")},
                           "profitable_at_-110": ok[k]} for k, v in dec.items()}
    return out


def main() -> None:
    res = run()
    p = config.ROOT / "data" / "backtests" / "bettable.json"
    p.write_text(json.dumps(res, indent=1))
    print(p)
    for k, v in res["decision"].items():
        print(f"{k:8s} n={v['n']:5d}  win {v['win_rate']*100:.1f}% [{v['ci95'][0]*100:.1f}, {v['ci95'][1]*100:.1f}]  "
              f"roi {v['roi']*100:+.1f}%  z {v['z_vs_break_even']:+.2f}  profitable: {v['profitable_at_-110']}")
