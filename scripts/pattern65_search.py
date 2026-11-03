"""Exploratory search for subsets of picks that cover at ~65%+ ATS.

Exploratory by design (Will asked to see 65% patterns even if they are noise). The point of
the script is to size how much of what it finds is luck:
  * enumerate every 1-, 2- and 3-way feature subset with >= MIN_N picks,
  * compare the number/strength of >=65% subsets with 500 label-shuffled copies of the same data,
  * freeze the >=65% subsets found in a discovery window and score them out of sample.

Usage: python scripts/pattern65_search.py NFLVERSE_GAMES_CSV OUT_JSON
nflverse games.csv: https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv
Nothing here changes a pick.
"""
from __future__ import annotations

import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RNG = np.random.default_rng(20261103)
N_SHUF = 500


# ----------------------------------------------------------------------------- features
def add_features(df: pd.DataFrame, g: pd.DataFrame) -> pd.DataFrame:
    """df needs: game_id, season, week, home_team, away_team, pick (home/away), line (grade line,
    canonical: negative = home favored), mkt (market line known at pick time or NaN), p_home, w (1/0)."""
    g = g.set_index("game_id")
    cols = ["weekday", "gametime", "div_game", "roof", "home_rest", "away_rest", "total_line"]
    df = df.join(g[cols], on="game_id")
    pick_home = df.pick.eq("home")
    df["pick_team"] = np.where(pick_home, df.home_team, df.away_team)
    pick_line = np.where(pick_home, df.line, -df.line)  # spread of the picked team
    f = pd.DataFrame(index=df.index)
    f["side"] = np.where(pick_home, "home", "away")
    f["role"] = np.where(pick_line < 0, "fav", np.where(pick_line > 0, "dog", "pk"))
    a = np.abs(df.line)
    f["spread"] = pd.cut(a, [-1, 3, 6, 9.5, 99], labels=["<=3", "3.5-6", "6.5-9.5", "10+"]).astype(str)
    f["keyline"] = np.select([a == 3, a == 7, (a % 1) == 0.5, (a % 1) == 0], ["exactly 3", "exactly 7", "half-pt", "whole-other"], "x")
    f["week"] = pd.cut(df.week, [0, 4, 9, 14, 30], labels=["w1-4", "w5-9", "w10-14", "w15+"]).astype(str)
    hr = df.gametime.fillna("13:00").str[:2].astype(int)
    f["slot"] = np.select(
        [df.weekday.eq("Thursday"), df.weekday.eq("Monday"), df.weekday.isin(["Friday", "Saturday", "Tuesday", "Wednesday"]),
         df.weekday.eq("Sunday") & (hr >= 19), df.weekday.eq("Sunday") & (hr >= 15)],
        ["Thu", "Mon", "SatFri", "SNF", "Sun-late"], "Sun-early")
    f["div"] = np.where(df.div_game == 1, "div", "nondiv")
    f["roof"] = np.where(df.roof.isin(["dome", "closed"]), "indoor", "outdoor")
    pr = np.where(pick_home, df.home_rest, df.away_rest)
    orr = np.where(pick_home, df.away_rest, df.home_rest)
    d = pr - orr
    f["rest"] = np.select([d >= 2, d <= -2], ["rest+", "rest-"], "rest=")
    f["total"] = pd.cut(df.total_line, [0, 40, 44, 48, 99], labels=["<=40", "40.5-44", "44.5-48", "48.5+"]).astype(str)
    f["team"] = df.pick_team
    if df.p_home.notna().any():
        conf = (df.p_home - 0.5).abs()
        f["conf"] = pd.cut(conf, [-1, 0.025, 0.05, 0.08, 1], labels=["c<2.5", "c2.5-5", "c5-8", "c8+"]).astype(str)
    if df.mkt.notna().any():
        mv = df.mkt - df.line  # + = market moved toward away
        toward_pick = np.where(pick_home, -mv, mv)  # + = market moved toward the picked side
        f["move"] = np.select([toward_pick >= 2, toward_pick >= 0.5, toward_pick <= -0.5], ["with2+", "with<2", "against"], "none")
    f["season_i"] = df.season
    f = f.fillna("na")
    return f


# ----------------------------------------------------------------------------- stats
def binom_p_ge(w: int, n: int, p0: float) -> float:
    """exact one-sided P(X >= w), log-space."""
    if n == 0:
        return 1.0
    lp = [math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1) + k * math.log(p0) + (n - k) * math.log(1 - p0) for k in range(w, n + 1)]
    m = max(lp)
    return min(1.0, math.exp(m) * sum(math.exp(x - m) for x in lp))


def build_subsets(f: pd.DataFrame, feats: list[str], max_way: int, min_n: int, team_max_way: int = 2):
    """Return membership matrix (rows x subsets, float32) and labels."""
    cols, labels = [], []
    for way in range(1, max_way + 1):
        for combo in itertools.combinations(feats, way):
            if "team" in combo and way > team_max_way:
                continue
            key = f[list(combo)].astype(str).agg("|".join, axis=1)
            for val, idx in key.groupby(key).groups.items():
                if len(idx) >= min_n:
                    v = np.zeros(len(f), dtype=np.float32)
                    v[f.index.get_indexer(idx)] = 1
                    cols.append(v)
                    labels.append(" & ".join(f"{c}={x}" for c, x in zip(combo, val.split("|"))))
    return np.stack(cols, axis=1), labels


def scan(f: pd.DataFrame, y: np.ndarray, feats: list[str], max_way: int, min_n: int, target: float = 0.65, label: str = ""):
    M, labels = build_subsets(f, feats, max_way, min_n)
    n = M.sum(0)
    w = M.T @ y.astype(np.float32)
    rate = w / n
    base = y.mean()
    real_hits = int(((rate >= target) & (n >= min_n)).sum())
    # permutation null (same subsets, shuffled outcomes)
    null_hits, null_max_rate, null_top = [], [], []
    Y = np.stack([RNG.permutation(y) for _ in range(N_SHUF)], axis=1).astype(np.float32)
    Wn = M.T @ Y
    Rn = Wn / n[:, None]
    null_hits = (Rn >= target).sum(0)
    # strongest rate among subsets with n>=min_n, and strongest among n>=50
    out = {
        "label": label, "rows": int(len(y)), "base_rate": float(base), "n_subsets": int(M.shape[1]), "min_n": min_n, "target": target,
        "real_hits": real_hits,
        "null_hits_mean": float(null_hits.mean()), "null_hits_p95": float(np.percentile(null_hits, 95)),
        "null_hits_ge_real": float((null_hits >= real_hits).mean()),
    }
    for nmin in (min_n, 50, 100):
        sel = n >= nmin
        out[f"real_max_rate_n{nmin}"] = float(rate[sel].max()) if sel.any() else None
        out[f"null_max_rate_n{nmin}_median"] = float(np.median(Rn[sel].max(0))) if sel.any() else None
        out[f"null_max_rate_n{nmin}_p95"] = float(np.percentile(Rn[sel].max(0), 95)) if sel.any() else None
    rows = []
    for j in np.where(rate >= target)[0]:
        wi, ni = int(w[j]), int(n[j])
        rows.append({"subset": labels[j], "n": ni, "w": wi, "rate": float(rate[j]), "p_vs_50": binom_p_ge(wi, ni, 0.5),
                     "p_vs_base": binom_p_ge(wi, ni, base)})
    rows.sort(key=lambda r: r["p_vs_50"])
    out["hits"] = rows
    # Holm over all subsets tested vs the base rate
    pv = sorted(binom_p_ge(int(w[j]), int(n[j]), base) for j in np.where(rate >= 0.58)[0])
    m = M.shape[1]
    out["holm_best_p_vs_base"] = pv[0] if pv else None
    out["holm_bar_first"] = 0.05 / m
    return out, M, labels


def apply_frozen(sel_labels: list[str], f: pd.DataFrame, y: np.ndarray) -> dict:
    """Score a frozen list of subset labels on new data (each pick scored once per subset it belongs to,
    and separately as the union)."""
    w_tot = n_tot = 0
    union = np.zeros(len(f), dtype=bool)
    per = []
    for lab in sel_labels:
        mask = np.ones(len(f), dtype=bool)
        for part in lab.split(" & "):
            c, v = part.split("=", 1)
            mask &= f[c].astype(str).to_numpy() == v
        n, w = int(mask.sum()), int(y[mask].sum())
        per.append((lab, n, w))
        w_tot += w
        n_tot += n
        union |= mask
    return {"subsets": len(sel_labels), "pooled_n": n_tot, "pooled_w": w_tot, "pooled_rate": w_tot / n_tot if n_tot else None,
            "union_n": int(union.sum()), "union_w": int(y[union].sum()), "union_rate": float(y[union].mean()) if union.any() else None,
            "per": per}


# ----------------------------------------------------------------------------- data
def load_backtest(g: pd.DataFrame) -> pd.DataFrame:
    d = pd.read_csv(ROOT / "data/backtests/phase7_predictions.csv")
    d = d[d.o.isin(["W", "L"])].copy()
    d["w"] = (d.o == "W").astype(int)
    d["line"] = d.open
    d["mkt"] = d.close
    meta = pd.read_csv(ROOT / "data/processed/sbro_lines.csv")[["game_id", "home_team", "away_team"]]
    d = d.merge(meta, on="game_id", how="left")
    return d.reset_index(drop=True)


def load_2025() -> pd.DataFrame:
    d = pd.read_csv(ROOT / "data/backtests/holdout2025_games.csv")
    d = d[d.o.isin(["W", "L"])].copy()
    d["season"] = 2025
    d["w"] = (d.o == "W").astype(int)
    d["line"] = d.cbs_open
    d["mkt"] = d.close
    return d.reset_index(drop=True)


def load_gap2022() -> pd.DataFrame:
    """2022-24 model picks graded vs the bet365 open (AusSportsBetting nfl.xlsx, personal use, gitignored).
    Needs data/backtests/gap2022_games.csv from `engine.backtest.gap2022.run()`."""
    d = pd.read_csv(ROOT / "data/backtests/gap2022_games.csv")
    d["w"] = d.win.astype(int)
    d["line"] = d.b_open
    d["mkt"] = d.close
    d["pick"] = np.where(d.p_home > 0.5, "home", "away")
    d["home_team"] = d.game_id.str.split("_").str[3]
    d["away_team"] = d.game_id.str.split("_").str[2]
    return d.reset_index(drop=True)


def load_live(g: pd.DataFrame) -> pd.DataFrame:
    p = pd.read_csv(ROOT / "data/predictions/predictions.csv")
    p = p.merge(g[["game_id", "home_score", "away_score"]], on="game_id")
    p = p[p.home_score.notna()].copy()
    cov = (p.home_score - p.away_score) + p.league_line
    p = p[cov != 0].copy()
    p["w"] = ((cov[cov != 0] > 0) == (p.pick == "home")).astype(int)
    p["line"] = p.league_line
    p["mkt"] = p.market_at_lock
    p["p_home"] = pd.to_numeric(p.p_home_cover, errors="coerce")
    p["fallback"] = np.where(p.data_status.eq("incomplete"), "fallback-pick", "model-pick")
    return p.reset_index(drop=True)


def load_market(g: pd.DataFrame) -> pd.DataFrame:
    """Every regular-season game 1999-2025, nflverse close; rows = (game, side). w = side covers."""
    x = g[(g.game_type == "REG") & g.spread_line.notna() & g.result.notna() & (g.season <= 2025)].copy()
    x["line"] = -x.spread_line  # canonical: negative = home favored
    x["cv"] = x.result + x.line  # home covers if > 0
    x = x[x.cv != 0]
    rows = []
    for side in ("home", "away"):
        r = x[["game_id", "season", "week", "home_team", "away_team", "line"]].copy()
        r["pick"] = side
        r["w"] = ((x.cv > 0) == (side == "home")).astype(int)
        r["mkt"] = np.nan
        r["p_home"] = np.nan
        rows.append(r)
    return pd.concat(rows).reset_index(drop=True)


def main(games_csv: str, out_json: str) -> None:
    g = pd.read_csv(games_csv)
    out: dict = {}

    # ---- A. backtest picks 2007-2021 (graded vs SBRO open), discovery/test splits
    bt = load_backtest(g)
    fb = add_features(bt, g)
    feats = ["side", "role", "spread", "keyline", "week", "slot", "div", "roof", "rest", "total", "conf", "move", "team"]
    y = bt.w.to_numpy()
    out["A_all"], _, _ = scan(fb, y, feats, 3, 30, label="backtest 2007-21 all (in-sample)")
    out["A_all"]["hits"] = out["A_all"]["hits"][:60]

    for name, dmask in (("early", bt.season <= 2014), ("late", bt.season >= 2015)):
        tmask = ~dmask
        r, _, labs = scan(fb[dmask].reset_index(drop=True), y[dmask], feats, 3, 25, label=f"discovery {name}")
        sel = [h["subset"] for h in r["hits"]]
        res = {"discovery": {k: v for k, v in r.items() if k != "hits"}, "n_selected": len(sel),
               "selected_top": r["hits"][:15]}
        res["test_backtest_other_half"] = {k: v for k, v in apply_frozen(sel, fb[tmask].reset_index(drop=True), y[tmask]).items() if k != "per"}
        # 2025 CBS open + 2026 live (available only for fully-covered feature sets)
        for nm, loader in (("test_2022_24_bet365", lambda: load_gap2022()), ("test_2025_cbs", lambda: load_2025()), ("test_2026_live", lambda: load_live(g))):
            t = loader()
            ft = add_features(t, g)
            sel_t = [s for s in sel if all(part.split("=", 1)[0] in ft.columns for part in s.split(" & "))]
            res[nm] = {k: v for k, v in apply_frozen(sel_t, ft, t.w.to_numpy()).items() if k != "per"}
            res[nm]["rows"] = int(len(t))
        if name == "early":
            # how did each discovery-window hit do in the later window, per subset
            fl = fb[tmask].reset_index(drop=True)
            per = apply_frozen(sel, fl, y[tmask])["per"]
            res["per_subset_test"] = [{"subset": a, "test_n": b, "test_w": c} for a, b, c in per if b >= 15][:40]
        out[f"A_disc_{name}"] = res


    # ---- A2. named candidates across every window, plus the move-size table
    cands = {
        "move>=2 (all)": "move=with2+", "wk10-14 & move>=2": "week=w10-14 & move=with2+",
        "wk10-14 & model conf 8+": "week=w10-14 & conf=c8+", "half-pt, outdoor, conf 8+": "keyline=half-pt & roof=outdoor & conf=c8+",
        "half-pt, outdoor, move>=2": "keyline=half-pt & roof=outdoor & move=with2+",
        "fav on exactly 3, small move": "role=fav & keyline=exactly 3 & move=with<2",
        "div, outdoor, move>=2": "div=div & roof=outdoor & move=with2+", "spread<=3": "spread=<=3",
        "spread<=3 & outdoor": "spread=<=3 & roof=outdoor",
    }
    gp, c25, lv0 = load_gap2022(), load_2025(), load_live(g)
    sets = {"2007-14": (fb, y, (bt.season <= 2014).to_numpy()), "2015-21": (fb, y, (bt.season >= 2015).to_numpy()),
            "2022-24": (add_features(gp, g), gp.w.to_numpy(), None), "2025": (add_features(c25, g), c25.w.to_numpy(), None),
            "2026": (add_features(lv0, g), lv0.w.to_numpy(), None)}
    out["candidates"] = {}
    for name, sub in cands.items():
        out["candidates"][name] = {}
        for wn, (ff, yy, mk) in sets.items():
            m = np.ones(len(ff), bool) if mk is None else mk.copy()
            for part in sub.split(" & "):
                c, v = part.split("=", 1)
                m &= ff[c].astype(str).to_numpy() == v
            out["candidates"][name][wn] = [int(yy[m].sum()), int(m.sum())]
    out["move_table"] = {}
    for wn, d in (("2007-21", bt), ("2022-24", gp), ("2025", c25), ("2026", lv0)):
        tw = np.where(d.pick.eq("home"), -(d.mkt - d.line), d.mkt - d.line)
        out["move_table"][wn] = {lab: [int(d.w[(tw >= lo) & (tw < hi)].sum()), int(((tw >= lo) & (tw < hi)).sum())]
                                 for lab, lo, hi in (("<0.5", -99, 0.5), ("0.5-1.5", 0.5, 1.5), ("1.5-2.5", 1.5, 2.5), ("2.5+", 2.5, 99), ("2+", 2, 99))}

    # ---- A3. subsets that reach 65% in BOTH halves of 2007-21 (>=15 picks each): real vs shuffled labels
    Mb, _lb = build_subsets(fb, feats, 3, 30)
    e = (bt.season <= 2014).to_numpy().astype(np.float32)
    ne, nl = Mb.T @ e, Mb.T @ (1 - e)
    okb = (ne >= 15) & (nl >= 15)

    def both(yv):
        yv = yv.astype(np.float32)
        return int((((Mb.T @ (yv * e)) / ne >= 0.65) & ((Mb.T @ (yv * (1 - e))) / nl >= 0.65) & okb).sum())
    nb = [both(RNG.permutation(y)) for _ in range(300)]
    out["both_halves"] = {"real": both(y), "null_mean": float(np.mean(nb)), "null_p95": float(np.percentile(nb, 95)),
                          "p_null_ge_real": float(np.mean(np.array(nb) >= both(y)))}

    # ---- B. live 2026 picks (pool line), sliced
    lv = load_live(g)
    fl = add_features(lv, g)
    fl["fallback"] = lv.fallback
    fl["flag"] = np.where(lv["flags"].fillna("").str.contains("MEDIAN"), "median", "pinnacle/other")
    yl = lv.w.to_numpy()
    out["B_live"], _, _ = scan(fl, yl, ["side", "role", "spread", "week", "slot", "div", "roof", "rest", "conf", "move", "fallback", "flag"], 2, 12, label="2026 live picks")
    out["B_live_n"] = {"n": int(len(lv)), "w": int(yl.sum())}

    # ---- C. market-only side patterns, nflverse close 1999-2025, discovery 1999-2012 / test 2013-2025
    mk = load_market(g)
    fm = add_features(mk, g)
    fm["fav_side"] = fm.role  # same as role
    mfeats = ["side", "role", "spread", "keyline", "week", "slot", "div", "roof", "rest", "total", "team"]
    ym = mk.w.to_numpy()
    out["C_all"], _, _ = scan(fm, ym, mfeats, 3, 100, label="market sides 1999-2025")
    out["C_all"]["hits"] = out["C_all"]["hits"][:40]
    dm = mk.season <= 2012
    r, _, _ = scan(fm[dm].reset_index(drop=True), ym[dm], mfeats, 3, 100, label="market discovery 1999-2012")
    sel = [h["subset"] for h in r["hits"]]
    out["C_disc"] = {"discovery": {k: v for k, v in r.items() if k != "hits"}, "n_selected": len(sel), "selected_top": r["hits"][:15],
                     "test_2013_25": {k: v for k, v in apply_frozen(sel, fm[~dm].reset_index(drop=True), ym[~dm]).items() if k != "per"}}
    Path(out_json).write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
