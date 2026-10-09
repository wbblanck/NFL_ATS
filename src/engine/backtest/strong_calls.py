"""Strong calls (docs/strong_calls_preregistration.md): do tiers by the size of the market move separate winning
pool picks from the rest, out of sample?

Move = |closing line - stale line| (half-point lines, so values are 0, 0.5, 1, 1.5, ...). Tiers, fixed in advance:
Lean < 1, Solid 1 to <2, Strong 2 to <3, Max 3+. A pick wins if its team covers the stale line (the pool's game)."""
from __future__ import annotations

import json
import math

import numpy as np

from engine import config
from engine.backtest import bettable as B
from engine.backtest import patterns as P

TIERS = [("Lean", 0.0, 1.0), ("Solid", 1.0, 2.0), ("Strong", 2.0, 3.0), ("Max", 3.0, 99.0)]
DISC, CONF = (2008, 2016), (2017, 2025)


def tier_of(move: np.ndarray) -> np.ndarray:
    t = np.zeros(len(move), int)
    for i, (_, lo, hi) in enumerate(TIERS):
        t[(move >= lo) & (move < hi)] = i
    return t


def rate(win: np.ndarray) -> dict:
    n = int(len(win))
    w = int(win.sum())
    lo, hi = B.wilson(w, n)
    p = w / n if n else float("nan")
    se0 = math.sqrt(0.25 / n) if n else float("nan")
    z = (p - 0.5) / se0 if n else float("nan")
    return {"W": w, "L": n - w, "n": n, "win_rate": p, "ci95": [lo, hi], "z_vs_50": z,
            "p_one_sided": 0.5 * math.erfc(z / math.sqrt(2)) if n else float("nan")}


def diff_test(a: np.ndarray, b: np.ndarray) -> dict:
    """One-sided two-proportion z: group a wins more than group b."""
    na, nb = len(a), len(b)
    pa, pb = a.mean(), b.mean()
    p = (a.sum() + b.sum()) / (na + nb)
    z = (pa - pb) / math.sqrt(p * (1 - p) * (1 / na + 1 / nb))
    return {"n_a": na, "n_b": nb, "rate_a": float(pa), "rate_b": float(pb), "diff": float(pa - pb), "z": float(z),
            "p_one_sided": 0.5 * math.erfc(z / math.sqrt(2))}


def trend_test(tier: np.ndarray, win: np.ndarray) -> dict:
    """Cochran-Armitage score test for a rising win rate across tiers 0..3 (the score test of the logistic slope)."""
    p = win.mean()
    t = tier.astype(float)
    tb = t.mean()
    num = float(((t - tb) * (win - p)).sum())
    den = math.sqrt(p * (1 - p) * float(((t - tb) ** 2).sum()))
    z = num / den
    return {"z": z, "p_one_sided": 0.5 * math.erfc(z / math.sqrt(2))}


def run() -> dict:
    d = P.dataset()
    season = d["season"].to_numpy()
    p = d["p_live"].to_numpy()
    pick_home = p > 0.5
    win = pick_home == (d["y"].to_numpy() == 1)                      # covers the stale line
    move = np.abs(d["drift"].to_numpy())
    tier = tier_of(move)
    close_g = B.grade(pick_home, d["margin"].to_numpy(), d["close"].to_numpy())
    line, close = d["line"].to_numpy(), d["close"].to_numpy()
    cross = np.array([any(min(abs(a), abs(b)) < k < max(abs(a), abs(b)) for k in (3, 7)) for a, b in zip(line, close)])
    disc = (season >= DISC[0]) & (season <= DISC[1])
    conf = (season >= CONF[0]) & (season <= CONF[1])
    out: dict = {"tiers": [t[0] for t in TIERS], "n": int(len(win))}
    out["by_tier"] = {}
    for i, (name, lo, hi) in enumerate(TIERS):
        m = tier == i
        out["by_tier"][name] = {"share": float(m.mean()), "all": rate(win[m]), "discovery": rate(win[m & disc]),
                                "confirmation": rate(win[m & conf]), "vs_close": B.summarize(close_g[m]),
                                "by_season": {int(s): rate(win[m & (season == s)])["win_rate"] for s in np.unique(season)
                                              if (m & (season == s)).sum() >= 15}}
    # --- hypotheses, decided on the confirmation period ---
    H: dict = {}
    strong = tier >= 2
    H["H1_move_2plus"] = {**rate(win[strong & conf]), "discovery_rate": rate(win[strong & disc])["win_rate"]}
    H["H2_move_3plus"] = {**rate(win[(tier == 3) & conf]), "discovery_rate": rate(win[(tier == 3) & disc])["win_rate"]}
    H["H3_trend"] = {**trend_test(tier[conf], win[conf].astype(float)), "discovery_z": trend_test(tier[disc], win[disc].astype(float))["z"]}
    H["H5_key_cross"] = {**diff_test(win[cross & conf], win[~cross & conf]),
                         "discovery_rate": float(win[cross & disc].mean())}
    # --- H4: agreement of live, v1 and keynum on the SBRO frame (2007-2021) ---
    f = B.frame()
    fs = f["season"].to_numpy()
    openl, margin = f["open"].to_numpy(), f["margin"].to_numpy()
    live_h, key_h, v1_h = (f[c].to_numpy() > 0.5 for c in ("p_live", "p_key", "p_v1"))
    agree = (live_h == key_h) & (live_h == v1_h)
    fwin = live_h == (margin > -openl)                                # the live pick vs the stale open
    fconf = (fs >= CONF[0]) & (fs <= 2021)
    fdisc = (fs >= 2007) & (fs <= DISC[1])
    H["H4_agreement"] = {**diff_test(fwin[agree & fconf], fwin[~agree & fconf]),
                         "discovery_rate_agree": float(fwin[agree & fdisc].mean()), "agree_share": float(agree.mean())}
    ps = {k: v["p_one_sided"] for k, v in H.items()}
    ok = B.holm(ps)
    for k in H:
        H[k]["holm_pass"] = bool(ok[k])
    disc_ok = {"H1_move_2plus": H["H1_move_2plus"]["discovery_rate"] > 0.5, "H2_move_3plus": H["H2_move_3plus"]["discovery_rate"] > 0.5,
               "H3_trend": H["H3_trend"]["discovery_z"] > 0, "H4_agreement": H["H4_agreement"]["discovery_rate_agree"] > 0.5,
               "H5_key_cross": H["H5_key_cross"]["discovery_rate"] > 0.5}
    for k in H:
        H[k]["real_strong_call"] = bool(H[k]["holm_pass"] and disc_ok[k])
    out["hypotheses"] = H
    out["periods"] = {"discovery": list(DISC), "confirmation": list(CONF)}
    return out


def main() -> None:
    res = run()
    p = config.ROOT / "data" / "backtests" / "strong_calls.json"
    p.write_text(json.dumps(res, indent=1))
    print(p)
    for name, v in res["by_tier"].items():
        a, c, b = v["all"], v["confirmation"], v["vs_close"]
        print(f"{name:7s} share {v['share']*100:4.1f}%  all {a['W']}-{a['L']} {a['win_rate']*100:.1f}%  conf {c['win_rate']*100:.1f}% (n={c['n']})  "
              f"vs close {b['win_rate']*100:.1f}% roi {b['roi']*100:+.1f}%")
    for k, v in res["hypotheses"].items():
        print(k, "p=%.4f" % v["p_one_sided"], "holm:", v["holm_pass"], "real:", v["real_strong_call"])
