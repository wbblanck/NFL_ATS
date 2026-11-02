"""Team ATS form test (docs/ats_form_preregistration.md).

Does a team's season-to-date record against the spread predict its next cover beyond the live model?"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
import polars as pl

from engine.backtest import total as T
from engine.backtest.holdout2025 import cbs_opens_2025
from engine.data import nflverse
from engine.models.margin_dist import TotalDist

FIT, HOLD = (2008, 2016), [*range(2017, 2022), 2025]


def net_ats(sched: pl.DataFrame) -> dict:
    """(game_id, team) -> covers minus non-covers vs the close in earlier REG games of the same season."""
    s = nflverse.with_kickoff(sched).filter(pl.col("game_type") == "REG", pl.col("result").is_not_null(),
                                            pl.col("spread_line").is_not_null()).sort("kickoff_utc", "game_id")
    net: dict[tuple, int] = defaultdict(int)
    out = {}
    for g in s.iter_rows(named=True):
        yr, h, a = g["season"], g["home_team"], g["away_team"]
        out[(g["game_id"], h)], out[(g["game_id"], a)] = net[(yr, h)], net[(yr, a)]
        m, sp = g["result"], g["spread_line"]          # spread_line > 0: home favored
        if m != sp:
            net[(yr, h)] += 1 if m > sp else -1
            net[(yr, a)] += -1 if m > sp else 1
    return out


def dataset() -> pl.DataFrame:
    df, sched = T.load()
    reg = sched.filter(pl.col("game_type") == "REG")
    d = df.join(reg.select("game_id", "week", "home_team", "away_team"), on="game_id") \
        .join(cbs_opens_2025(sched), on="game_id", how="left") \
        .with_columns(pl.when(pl.col("season") <= 2021).then(pl.col("open")).otherwise(pl.col("cbs_open")).alias("line"))
    d = d.filter(pl.col("season").is_in([*range(2008, 2022), 2025]), pl.col("line").is_not_null(),
                 pl.col("margin") != -pl.col("line"))
    p = np.empty(d.height)
    s = d["season"].to_numpy()
    for yr in np.unique(s):
        tr = df.filter(pl.col("season") < yr)
        td = TotalDist("shifted_total").fit(tr["close"].to_numpy(), tr["margin"].to_numpy(), tr["total"].to_numpy())
        k = s == yr
        p[k] = td.sf(-d["line"].to_numpy()[k], d["close"].to_numpy()[k], d["total"].to_numpy()[k])
    form = net_ats(sched)
    D = [form[(g, h)] - form[(g, a)] for g, h, a in zip(d["game_id"], d["home_team"], d["away_team"])]
    return d.with_columns(pl.Series("p", np.clip(p, 1e-4, 1 - 1e-4)), pl.Series("D", D),
                          (pl.col("margin") > -pl.col("line")).cast(pl.Float64).alias("y"))


def z_side(y, p, side_home, sel) -> dict:
    """Side S = home where side_home else away; z of S's wins against the model's own probabilities."""
    yS = np.where(side_home, y, 1 - y)[sel]
    pS = np.where(side_home, p, 1 - p)[sel]
    n, W, E = len(yS), float(yS.sum()), float(pS.sum())
    z = (W - E) / math.sqrt(float((pS * (1 - pS)).sum())) if n else float("nan")
    return {"n": n, "won": int(W), "expected": round(E, 1), "z": round(z, 3),
            "p": math.erfc(abs(z) / math.sqrt(2)) if n else float("nan")}


def fit_beta(y, p, D) -> float:
    """MLE of beta in logit(p') = logit(p) + beta*D (Newton)."""
    o, b = np.log(p / (1 - p)), 0.0
    for _ in range(50):
        q = 1 / (1 + np.exp(-(o + b * D)))
        g, h = float(((y - q) * D).sum()), float((q * (1 - q) * D * D).sum())
        step = g / h
        b += step
        if abs(step) < 1e-10:
            break
    return b


def logloss(y, q) -> float:
    return float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q)))


def run() -> dict:
    d = dataset()
    y, p, D, wk, s = (d[c].to_numpy() for c in ("y", "p", "D", "week", "season"))
    fit, hold = (s >= FIT[0]) & (s <= FIT[1]), np.isin(s, HOLD)
    out = {"games": d.height, "fit_games": int(fit.sum()), "holdout_games": int(hold.sum()), "tests": {}}
    for name, k in (("form_side", 2), ("form_strong", 4)):
        base = (wk >= 4) & (np.abs(D) >= k)
        out["tests"][name] = {lab: z_side(y, p, D > 0, base & m) for lab, m in
                              (("all", np.ones_like(fit)), ("2008-2016", fit), ("holdout", hold))}
    beta = fit_beta(y[fit], p[fit], D[fit])
    q = 1 / (1 + np.exp(-(np.log(p / (1 - p)) + beta * D)))
    diff = hold & ((q > 0.5) != (p > 0.5))
    var_right = int(((q > 0.5) == (y == 1))[diff].sum())
    n = int(diff.sum())
    zs = (var_right - n / 2) / math.sqrt(n / 4) if n else float("nan")
    out["tests"]["form_variant"] = {
        "beta": round(beta, 4), "holdout_differing": n, "variant_won": var_right, "official_won": n - var_right,
        "z": round(zs, 3), "p": math.erfc(abs(zs) / math.sqrt(2)) if n else float("nan"),
        "logloss_official": round(logloss(y[hold], p[hold]), 5), "logloss_variant": round(logloss(y[hold], q[hold]), 5),
        "official_record_holdout": f"{int(((p > 0.5) == (y == 1))[hold].sum())}/{int(hold.sum())}",
        "variant_record_holdout": f"{int(((q > 0.5) == (y == 1))[hold].sum())}/{int(hold.sum())}"}
    ps = sorted(((v["all"]["p"] if "all" in v else v["p"]), k) for k, v in out["tests"].items())
    alive = True
    for r, (pv, k) in enumerate(ps):
        thr = 0.05 / (len(ps) - r)
        alive = alive and pv <= thr
        out["tests"][k]["holm"] = {"p": pv, "threshold": thr, "pass": alive}
    return out


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def forward_2026(beta: float) -> dict:
    """Descriptive 2026 check: form graded against the pool line, official picks from predictions.csv."""
    from engine import config
    from engine.data import league_lines, store
    from engine.picks.grading import Result, grade_league
    sched, _ = nflverse.regular_season_schedule([2026], save=False)
    lines = {r["game_id"]: float(r["spread"]) for r in league_lines.load()}
    preds = {r["game_id"]: r for r in store.read_rows(config.path("predictions") / "predictions.csv")
             if not r.get("supersedes")}
    net: dict[str, int] = defaultdict(int)
    rows = []
    for g in sched.sort("kickoff_utc", "game_id").iter_rows(named=True):
        gid, h, a = g["game_id"], g["home_team"], g["away_team"]
        if gid not in lines or g["home_score"] is None:
            continue
        res = grade_league(g["home_score"], g["away_score"], lines[gid])
        Dg = net[h] - net[a]
        pr = preds.get(gid)
        rows.append({"game_id": gid, "week": g["week"], "D": Dg, "home_covered": res == Result.HOME_COVER,
                     "p": _num(pr["p_home_cover"]) if pr else None,
                     "official": pr["pick"] if pr else None})
        w = 1 if res == Result.HOME_COVER else -1
        net[h] += w
        net[a] -= w
    f = [r for r in rows if r["week"] >= 4 and abs(r["D"]) >= 2]
    hot_won = sum((r["D"] > 0) == r["home_covered"] for r in f)
    picked = [r for r in rows if r["p"] is not None]
    flips, off_w = [], 0
    for r in picked:
        o = math.log(r["p"] / (1 - r["p"]))
        qv = 1 / (1 + math.exp(-(o + beta * r["D"])))
        off_right = (r["official"] == "home") == r["home_covered"]
        off_w += off_right
        if (qv > 0.5) != (r["official"] == "home"):
            flips.append({"game_id": r["game_id"], "D": r["D"], "p_home": r["p"], "official": r["official"],
                          "official_right": off_right})
    return {"graded": len(rows), "form_side_games": len(f), "hot_team_won": hot_won,
            "picked": len(picked), "official_won": off_w, "variant_flips": flips,
            "variant_won": off_w + sum(-1 if x["official_right"] else 1 for x in flips)}


if __name__ == "__main__":
    import json
    r = run()
    r["forward_2026"] = forward_2026(r["tests"]["form_variant"]["beta"])
    print(json.dumps(r, indent=1))
