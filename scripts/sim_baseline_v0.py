"""V0 baseline diagnostics for the game simulator (research only, descriptive).

Reads data/gamesim/g3_2022_2025.parquet (written by scripts/gamesim_reproduce.py) and reports, per season and pooled:
margin MAE/bias, 3-point and other key-margin frequencies (sim vs actual), margin-distribution log loss, ATS Brier and
calibration against the closing line, and the same for Elo and for a plain normal benchmark centred on the close.

Sign convention (this repo): spread negative = home favored; home covers when margin > -spread.
Nothing here changes the simulator or the live pipeline.
"""
import json
import sys
from math import erf, sqrt
from pathlib import Path

import numpy as np
import polars as pl

K = Path(__file__).resolve().parents[1] / "data" / "gamesim"
KEYS = [1, 2, 3, 4, 6, 7, 8, 10, 14]
V = np.arange(-60, 61)
ALPHA = 0.1  # additive smoothing on the 1000-run histogram for log loss (121 cells)
SIMS = 1000


def ncdf(x):
    return 0.5 * (1 + np.vectorize(erf)(x / sqrt(2)))


def normal_dist(mu, sd):
    """Probability mass on integer margins -60..60 for N(mu, sd), cells +-0.5, tails folded into the ends."""
    edges = np.concatenate([[-np.inf], V[:-1] + 0.5, [np.inf]])
    cdf = np.array([[0.0 if e == -np.inf else 1.0 if e == np.inf else ncdf((e - m) / sd) for e in edges] for m in mu])
    return np.diff(cdf, axis=1)


def cover_probs(dist, spread):
    """P(home covers) excluding pushes, and P(push). dist: n x 121 mass on integer margins."""
    thr = -spread
    gt = np.array([dist[i, V > thr[i]].sum() for i in range(len(thr))])
    eq = np.array([dist[i, V == thr[i]].sum() if float(thr[i]).is_integer() else 0.0 for i in range(len(thr))])
    return gt / np.clip(1 - eq, 1e-9, None), eq


def point_cover(fair, spread):
    """Side from a point forecast: home if fair margin > -spread, ties None."""
    d = fair - (-spread)
    return np.where(d > 0, 1.0, np.where(d < 0, 0.0, np.nan))


def summarise(df: pl.DataFrame, sd: float) -> dict:
    n = df.height
    margin = df["margin"].to_numpy().astype(float)
    spread = df["close_spread"].to_numpy().astype(float)
    sim = df["sim_fair"].to_numpy()
    elo = df["elo_fair"].to_numpy()
    dist = np.stack([df[f"m_{v}"].to_numpy() for v in V], axis=1)
    out = {"games": n}
    out["margin_mae"] = {"sim": float(np.abs(sim - margin).mean()), "elo": float(np.abs(elo - margin).mean()),
                         "close": float(np.abs(-spread - margin).mean())}
    out["margin_bias_home"] = {"sim": float((sim - margin).mean()), "elo": float((elo - margin).mean()),
                               "close": float((-spread - margin).mean())}
    idx = np.clip(margin.astype(int), -60, 60) + 60
    # margin distribution log loss (sim, smoothed; normal benchmark on the close; Elo has no distribution here)
    sm = (dist * SIMS + ALPHA) / (SIMS + 121 * ALPHA)
    nd = normal_dist(-spread, sd)
    out["margin_logloss"] = {"sim": float(-np.log(sm[np.arange(n), idx]).mean()),
                             "normal_on_close": float(-np.log(np.clip(nd[np.arange(n), idx], 1e-9, None)).mean())}
    # key margins (absolute value): actual vs mean sim mass vs benchmark
    keys = {}
    for k in KEYS:
        act = float((np.abs(margin) == k).mean())
        s = float((dist[:, V == k].sum(1) + dist[:, V == -k].sum(1)).mean())
        b = float((nd[:, V == k].sum(1) + nd[:, V == -k].sum(1)).mean())
        keys[str(k)] = {"actual": act, "sim": s, "normal_on_close": b}
    out["key_margins"] = keys
    # ATS: exclude pushes; probability scores with sim distribution and benchmark
    p_sim, push_sim = cover_probs(dist, spread)
    p_nrm, _ = cover_probs(nd, spread)
    push = margin == -spread
    keep = ~push
    y = (margin > -spread)[keep].astype(float)
    out["ats"] = {"games_no_push": int(keep.sum()), "pushes": int(push.sum())}
    for name, p in (("sim", p_sim), ("normal_on_close", p_nrm)):
        pp = np.clip(p[keep], 1e-6, 1 - 1e-6)
        out["ats"][f"brier_{name}"] = float(((pp - y) ** 2).mean())
        out["ats"][f"logloss_{name}"] = float(-(y * np.log(pp) + (1 - y) * np.log(1 - pp)).mean())
    out["ats"]["brier_5050"] = 0.25
    for name, fair in (("sim", sim), ("elo", elo)):
        side = point_cover(fair, spread)[keep]
        m = ~np.isnan(side)
        w = int((side[m] == y[m]).sum())
        out["ats"][f"{name}_record_all"] = [w, int(m.sum()) - w]
        big = m & (np.abs(fair[keep] + spread[keep]) >= 1.5)
        wb = int((side[big] == y[big]).sum())
        out["ats"][f"{name}_record_gap_1p5"] = [wb, int(big.sum()) - wb]
    # calibration of sim cover probability (deciles by equal width)
    bins = [0, 0.35, 0.45, 0.5, 0.55, 0.65, 1.0001]
    cal = []
    pk = p_sim[keep]
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (pk >= lo) & (pk < hi)
        if m.sum():
            cal.append({"bin": f"{lo:.2f}-{min(hi, 1):.2f}", "n": int(m.sum()), "mean_p": float(pk[m].mean()),
                        "actual": float(y[m].mean())})
    out["calibration"] = cal
    out["calibration_error_ece"] = float(sum(c["n"] * abs(c["mean_p"] - c["actual"]) for c in cal) / max(len(pk), 1))
    return out


def main(path=None):
    df = pl.read_parquet(path or K / "g3_2022_2025.parquet")
    # benchmark sd: pooled std of (margin + close_spread) over all games; descriptive only (uses the same games)
    sd = float((df["margin"] + df["close_spread"]).std())
    res = {"normal_benchmark_sd": sd, "pooled": summarise(df, sd)}
    for s in sorted(df["season"].unique().to_list()):
        res[str(s)] = summarise(df.filter(pl.col("season") == s), sd)
    out = K / "v0_baseline.json"
    out.write_text(json.dumps(res, indent=1))
    p = res["pooled"]
    print(f"games {p['games']}  normal sd {sd:.3f}")
    print("margin MAE", {k: round(v, 3) for k, v in p["margin_mae"].items()})
    print("margin logloss", {k: round(v, 4) for k, v in p["margin_logloss"].items()})
    print("ats", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in p["ats"].items()})
    print("3-pt", p["key_margins"]["3"])
    print("ECE", round(p["calibration_error_ece"], 4))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
