"""Edge search with the AusSportsBetting data (docs/edge2_preregistration.md). Hypotheses H1-H5 against the
book's own half-point opening line, compared with the live model on the games where the picks differ."""
from __future__ import annotations

import math

import numpy as np
import polars as pl

from engine.backtest import gap2022 as G
from engine.backtest import total as T
from engine.models.margin_dist import TotalDist
from engine.picks.grading import is_half_point

DISC, CONF = (2014, 2019), (2020, 2024)
B_GRID = np.arange(-6, 6.001, 0.25)
C_GRID = np.arange(0, 1.001, 0.05)


def dataset() -> tuple[pl.DataFrame, pl.DataFrame]:
    """Book lines joined to nflverse outcomes/totals, 2014-2024 half-point opens with prices."""
    df, sched = T.load()
    reg = sched.filter(pl.col("game_type") == "REG")
    m = G.match(G.load_xlsx(), reg.filter(pl.col("season").is_between(2014, 2024)))
    d = df.join(m, on="game_id").join(reg.select("game_id", "week"), on="game_id") \
        .filter(pl.col("b_open").is_not_null(), pl.col("b_close").is_not_null(), pl.col("hp").is_not_null(),
                pl.col("hml").is_not_null()) \
        .filter(pl.col("b_open").map_elements(is_half_point, return_dtype=pl.Boolean)) \
        .with_columns(((1 / pl.col("hp")) / (1 / pl.col("hp") + 1 / pl.col("ap"))).alias("q_cover"),
                      ((1 / pl.col("hml")) / (1 / pl.col("hml") + 1 / pl.col("aml"))).alias("q_win"),
                      (pl.col("margin") > -pl.col("b_open")).alias("home_cov"))
    return d.sort("season", "week", "game_id"), df


def dists(df: pl.DataFrame, seasons) -> dict:
    out = {}
    for s in seasons:
        tr = df.filter(pl.col("season") < s)
        out[s] = TotalDist("shifted_total").fit(tr["close"].to_numpy(), tr["margin"].to_numpy(), tr["total"].to_numpy())
    return out


def p_cover(d: pl.DataFrame, D: dict, market: np.ndarray) -> np.ndarray:
    p = np.empty(d.height)
    s = d["season"].to_numpy()
    for yr, td in D.items():
        k = s == yr
        if k.any():
            p[k] = td.sf(-d["b_open"].to_numpy()[k], market[k], d["total"].to_numpy()[k])
    return p


def ml_spread(d: pl.DataFrame, D: dict) -> np.ndarray:
    """Spread whose home win probability under the live distribution equals the no-vig moneyline probability."""
    grid = np.arange(-30, 30.001, 0.1)
    out = np.empty(d.height)
    for i, r in enumerate(d.select("season", "total", "q_win").iter_rows()):
        w = D[r[0]].sf(np.zeros_like(grid), grid, np.full_like(grid, r[1]))   # decreasing in the spread
        out[i] = grid[np.argmin(np.abs(w - r[2]))]
    return out


def loglik(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def compare(rule: np.ndarray, base: np.ndarray, y: np.ndarray) -> dict:
    """rule/base: picks (True = home). y: home covered."""
    diff = rule != base
    r_only = int(((rule == y) & diff).sum())
    b_only = int(((base == y) & diff).sum())
    n = int(diff.sum())
    wr, wb = int((rule == y).sum()), int((base == y).sum())
    return {"N": int(len(y)), "rule_W": wr, "base_W": wb, "differ": n, "rule_only": r_only, "base_only": b_only,
            "z": (r_only - b_only) / math.sqrt(n) if n else 0.0,
            "p_one_sided": 0.5 * math.erfc(((r_only - b_only) / math.sqrt(n)) / math.sqrt(2)) if n else 1.0}


def split(d, lo, hi):
    return (d["season"].to_numpy() >= lo) & (d["season"].to_numpy() <= hi)


def run_market(d: pl.DataFrame, df: pl.DataFrame) -> dict:
    D = dists(df, range(2014, 2025))
    y = d["home_cov"].to_numpy()
    close = d["b_close"].to_numpy()
    base_p = p_cover(d, D, close)
    base = base_p > 0.5
    disc, conf = split(d, *DISC), split(d, *CONF)
    out = {"baseline": {k: {"W": int((base == y)[m].sum()), "N": int(m.sum())} for k, m in (("disc", disc), ("conf", conf))}}
    # H1 price tie-break in no-move games
    nomove = close == d["b_open"].to_numpy()
    hp, ap = d["hp"].to_numpy(), d["ap"].to_numpy()
    h1 = base.copy()
    k = nomove & (hp != ap)
    h1[k] = hp[k] < ap[k]
    out["H1"] = {"no_move_games": {"disc": int((nomove & disc).sum()), "conf": int((nomove & conf).sum())},
                 "priced_no_move": {"disc": int((k & disc).sum()), "conf": int((k & conf).sum())},
                 "disc": compare(h1[disc], base[disc], y[disc]), "conf": compare(h1[conf], base[conf], y[conf])}
    # H2 price-adjusted market
    qc = d["q_cover"].to_numpy() - 0.5
    ll = [(b, loglik(p_cover(d, D, close + b * qc)[disc], y[disc])) for b in B_GRID]
    b = max(ll, key=lambda t: t[1])[0]
    h2 = p_cover(d, D, close + b * qc) > 0.5
    out["H2"] = {"b": float(b), "b_loglik_curve": [(float(x), v) for x, v in ll],
                 "disc": compare(h2[disc], base[disc], y[disc]), "conf": compare(h2[conf], base[conf], y[conf])}
    # H3 moneyline-implied spread
    sml = ml_spread(d, D)
    ll = [(c, loglik(p_cover(d, D, close + c * (sml - close))[disc], y[disc])) for c in C_GRID]
    c = max(ll, key=lambda t: t[1])[0]
    h3 = p_cover(d, D, close + c * (sml - close)) > 0.5
    out["H3"] = {"c": float(c), "c_loglik_curve": [(float(x), v) for x, v in ll],
                 "ml_minus_spread": {"mean_abs": float(np.mean(np.abs(sml - close))),
                                     "share_ge_1": float(np.mean(np.abs(sml - close) >= 1))},
                 "disc": compare(h3[disc], base[disc], y[disc]), "conf": compare(h3[conf], base[conf], y[conf])}
    out["_picks"] = {"base": base, "h1": h1, "h2": h2, "h3": h3, "nomove": nomove}
    return out


def v1_cover(d: pl.DataFrame, sched: pl.DataFrame) -> np.ndarray:
    """proj-poisson-v1 (live constants), refit before each week, P(home covers the book open)."""
    import nflreadpy as nfl
    from engine.backtest import projection_eval as PE
    from engine.models import projection as P
    from engine.picks import final
    games = P.team_games(nfl.load_team_stats(seasons=list(range(1999, 2025))), sched)
    tgt = d.join(sched.select("game_id", "home_team", "away_team"), on="game_id").select(
        "game_id", "season", "week", "home_team", "away_team")
    pr = PE.project_games(games, tgt, final.PROJ_H, final.PROJ_LAM)
    return np.array([x.p_home_cover(o) if x else 0.5 for x, o in zip(pr, d["b_open"].to_list())])


def run_projection(d: pl.DataFrame, base: np.ndarray, nomove: np.ndarray, pv: np.ndarray, lo: int, hi: int) -> dict:
    y = d["home_cov"].to_numpy()
    m = split(d, lo, hi) & ~np.isnan(pv)
    pick = pv > 0.5
    tb = base.copy()
    tb[nomove] = pick[nomove]
    return {"full": compare(pick[m], base[m], y[m]), "tiebreak": compare(tb[m], base[m], y[m]),
            "no_move_games": int((nomove & m).sum())}


def cluster_boot(d: pl.DataFrame, stat, mask: np.ndarray, n=4000, seed=7) -> tuple[float, float]:
    """95% interval of stat(idx) resampling whole weeks (games in a week share news and market moves)."""
    rng = np.random.default_rng(seed)
    wk = (d["season"] * 100 + d["week"]).to_numpy()
    ids = np.unique(wk[mask])
    groups = {w: np.where((wk == w) & mask)[0] for w in ids}
    vals = []
    for _ in range(n):
        pick = rng.choice(ids, len(ids), replace=True)
        vals.append(stat(np.concatenate([groups[w] for w in pick])))
    return float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975))


def season_sim(rates=(0.514, 0.549, 0.56), games=272, weeks=17, n=100_000, seed=11) -> dict:
    rng = np.random.default_rng(seed)
    out = {}
    per = games // weeks
    for r in rates:
        w = rng.binomial(1, r, size=(n, weeks, per))
        season = w.sum(axis=(1, 2))
        wk = w.sum(axis=2)
        out[str(r)] = {"mean": float(season.mean()), "p5": float(np.quantile(season, .05)),
                       "p95": float(np.quantile(season, .95)), "P_ge_141": float((season >= 141).mean()),
                       "P_ge_150": float((season >= 150).mean()), "P_below_136": float((season < 136).mean()),
                       "weeks_12plus_per_season": float((wk >= 12).sum(axis=1).mean())}
    return out


def run(v1_cover_arr=None, v3_cover_arr=None) -> dict:
    d, df = dataset()
    r = run_market(d, df)
    P = r.pop("_picks")
    y = d["home_cov"].to_numpy()
    _, sched = T.load()
    pv1 = v1_cover(d, sched) if v1_cover_arr is None else v1_cover_arr
    r["H4"] = {s: run_projection(d, P["base"], P["nomove"], pv1, *rng) for s, rng in (("disc", DISC), ("conf", CONF))}
    if v3_cover_arr is not None:
        r["H5"] = run_projection(d, P["base"], P["nomove"], v3_cover_arr, 2022, 2024)
    fam = {"H1": r["H1"]["conf"], "H2": r["H2"]["conf"], "H3": r["H3"]["conf"],
           "H4a": r["H4"]["conf"]["full"], "H4b": r["H4"]["conf"]["tiebreak"]}
    if "H5" in r:
        fam.update(H5a=r["H5"]["full"], H5b=r["H5"]["tiebreak"])
    order = sorted(fam, key=lambda k: fam[k]["p_one_sided"])
    holm, alive = {}, True
    for i, k in enumerate(order):
        thr = 0.05 / (len(order) - i)
        ok = alive and fam[k]["p_one_sided"] <= thr
        alive = ok
        holm[k] = {"p": fam[k]["p_one_sided"], "threshold": thr, "pass": ok}
    r["holm"] = holm
    conf = split(d, *CONF)
    base = P["base"]
    r["baseline_conf_ci95_week_bootstrap"] = cluster_boot(d, lambda ix: float((base[ix] == y[ix]).mean()), conf)
    close = d["b_close"].to_numpy()
    drift = close - d["b_open"].to_numpy()
    r["baseline_by_move"] = {}
    for lab, k in (("no_move", drift == 0), ("half_pt", np.abs(drift) == 0.5), ("1_plus", np.abs(drift) >= 1)):
        for per, m in (("2014_2019", split(d, *DISC)), ("2020_2024", conf)):
            mm = k & m
            r["baseline_by_move"][f"{lab}_{per}"] = {"W": int((base == y)[mm].sum()), "N": int(mm.sum())}
    r["season_sim"] = season_sim()
    return r
