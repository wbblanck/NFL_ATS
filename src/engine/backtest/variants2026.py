"""Pick-model variants on the 2026 season (docs/variants2026_preregistration.md). Research only: reads the
recorded picks, projections and captures, writes data/backtests/variants2026.json, changes nothing live."""
from __future__ import annotations

import datetime as dt
import json
import math
import statistics

import numpy as np
import polars as pl

from engine import config
from engine.data import league_lines, nflverse, sbro
from engine.models import projection as P
from engine.models.margin_dist import MarginDist, TotalDist
from engine.picks import final, hybrid
from engine.picks.grading import is_half_point

KEYS = (3, 6, 7, 10)
FRESH_MIN, SNAP_BEFORE, SNAP_AFTER = 10, 10, 2
HOLD = {"pinnacle": 0.027}
HOLD_OTHER = 0.045
AGREE_MIN = 0.60
TREND_HOURS, K_MIN_GAMES = 18, 10
CANDS = ("C1", "C2", "C3", "C4", "C5a", "C5b", "C5c", "C6a", "C6b", "C6c", "C7", "C8", "C9")
TRACKED = ("official", "keynum", "v1", "v3", "hybrid")
PROB_CANDS = ("C1", "C2", "C3", "C5a", "C5b", "C5c")


def _t(s) -> dt.datetime:
    return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def _f(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- inputs

class Ctx:
    """Schedules, fitted distributions (cached per cut-off time) and v1 ratings (cached per week)."""

    def __init__(self):
        import nflreadpy as nfl
        self.sched, _ = nflverse.regular_season_schedule(save=False)
        self.sched_all, _ = nflverse.pull("schedules", save=False)
        self.pg = P.team_games(nfl.load_team_stats(seasons=list(range(1999, 2027))), self.sched_all)
        self._t, self._d, self._r = {}, {}, {}

    def tdist(self, now) -> TotalDist:
        if now not in self._t:
            self._t[now] = final.fit_total_dist(self.sched, now)
        return self._t[now]

    def keynum(self, now) -> MarginDist:
        if now not in self._d:
            dist, _ = final.fit_dist(self.sched, now)
            self._d[now] = MarginDist(kind=final.SHADOW).fit(dist.c, dist.m)
        return self._d[now]

    def v1(self, week, home, away):
        if week not in self._r:
            self._r[week] = P.fit(self.pg, 2026 * 25 + week, 2026, final.PROJ_H, final.PROJ_LAM)
        rt = self._r[week]
        q = rt.rates(P.FRANCHISE.get(home, home), P.FRANCHISE.get(away, away))
        return rt, q


def _proj(rt, q):
    return P.Projection(P.points_pmf(q["home_td"], q["home_fg"], rt.p_xp, rt.p_2),
                        P.points_pmf(q["away_td"], q["away_fg"], rt.p_xp, rt.p_2))


def _v3(ctx: Ctx, ids: list[str]) -> dict:
    """Recomputed v3 (approximate: injury and depth data as of today) for games with no recorded v3 row."""
    from engine.models import players_v3_live as L
    if not ids:
        return {}
    v3 = L.loader(ctx.sched, ctx.sched_all)(ids)
    feats = {(r["game_id"], r["team"]): r for r in v3["features"].iter_rows(named=True)}
    m, out = v3["model"], {}
    for g in ctx.sched.filter(pl.col("game_id").is_in(ids)).iter_rows(named=True):
        h, a = P.FRANCHISE.get(g["home_team"], g["home_team"]), P.FRANCHISE.get(g["away_team"], g["away_team"])
        fh, fa = feats.get((g["game_id"], h)), feats.get((g["game_id"], a))
        if not (fh and fa and all(f[c] is not None for f in (fh, fa) for c in m["features"])):
            continue
        rt, q = ctx.v1(g["week"], g["home_team"], g["away_team"])
        q3 = {"home_td": q["home_td"] * L.multiplier(fh, m, "td"), "home_fg": q["home_fg"] * L.multiplier(fh, m, "fg"),
              "away_td": q["away_td"] * L.multiplier(fa, m, "td"), "away_fg": q["away_fg"] * L.multiplier(fa, m, "fg")}
        out[g["game_id"]] = _proj(rt, q3)
    return out


def _captures() -> pl.DataFrame:
    m = pl.read_csv(config.path("lines") / "market_captures.csv", infer_schema_length=0)
    return m.filter(pl.col("status") == "ok", pl.col("home_spread").is_not_null()).with_columns(
        pl.col("captured_at").str.to_datetime(time_zone="UTC").alias("cap"),
        pl.col("book_last_update").str.to_datetime(time_zone="UTC", strict=False).alias("upd"),
        pl.col("home_spread").cast(pl.Float64), pl.col("home_price_decimal").cast(pl.Float64, strict=False))


def _snapshot(caps: pl.DataFrame, gid: str, at: dt.datetime) -> list[dict]:
    x = caps.filter(pl.col("game_id") == gid, pl.col("cap") >= at - dt.timedelta(minutes=SNAP_BEFORE),
                    pl.col("cap") <= at + dt.timedelta(minutes=SNAP_AFTER)).sort("cap")
    last = {}
    for r in x.iter_rows(named=True):
        last[r["book"]] = r
    return [{"book": b, "spread": r["home_spread"], "price": r["home_price_decimal"],
             "fresh": r["upd"] is not None and (r["cap"] - r["upd"]).total_seconds() <= FRESH_MIN * 60}
            for b, r in sorted(last.items())]


def _earlier(caps: pl.DataFrame, gid: str, lock: dt.datetime):
    x = caps.filter(pl.col("game_id") == gid, pl.col("cap") <= lock - dt.timedelta(hours=TREND_HOURS))
    if x.height == 0:
        return None
    t = x["cap"].max()
    return float(statistics.median(x.filter(pl.col("cap") == t)["home_spread"].to_list()))


def build(ctx: Ctx | None = None) -> list[dict]:
    ctx = ctx or Ctx()
    S = {g["game_id"]: g for g in ctx.sched.filter(pl.col("season") == 2026, pl.col("result").is_not_null()).to_dicts()}
    ll = {r["game_id"]: float(r["spread"]) for r in league_lines.load()}
    preds = {r["game_id"]: r for r in pl.read_csv(config.path("predictions") / "predictions.csv",
                                                   infer_schema_length=0).to_dicts()}
    proj = {}
    for r in pl.read_csv(config.path("predictions") / "projections.csv", infer_schema_length=0).to_dicts():
        proj[(r["game_id"], r["model_version"])] = r
    hyp = {r["game_id"]: r for r in pl.read_csv(config.ROOT / "data/hypothetical/missed_picks_2026-10-20.csv",
                                                infer_schema_length=0).to_dicts()
           if r["group"] in ("no_row", "no_market") and r["status"] == "ok"}
    caps = _captures()
    rows = []
    for gid, g in sorted(S.items(), key=lambda kv: kv[1]["kickoff_utc"]):
        L = ll.get(gid)
        if L is None or not is_half_point(L):
            continue
        pr = preds.get(gid)
        live = pr is not None and pr["pick_rule"] == "argmax_cover_prob" and _f(pr["market_at_lock"]) is not None
        if g["week"] <= 2:
            bucket, m, now, T = "early", -g["spread_line"], g["lock_utc"], g["total_line"]
        elif live:
            bucket, m, now = "live", _f(pr["market_at_lock"]), _t(pr["created_at"])
            T = _f(pr["market_total"]) or g["total_line"]
        elif gid in hyp:
            bucket, m, now, T = "rebuilt", _f(hyp[gid]["pinnacle_home_spread"]), _t(hyp[gid]["as_of_utc"]), g["total_line"]
        else:
            continue
        td = ctx.tdist(now)
        p_calc = td.cover_probs(m, L, T)[0]
        if bucket == "live":
            p_off, off_home = _f(pr["p_home_cover"]), pr["pick"] == "home"
            p_key = _f(pr["shadow_p_home_keynum"])
        elif bucket == "rebuilt":
            p_off = _f(hyp[gid]["p_home_cover"])
            off_home = hyp[gid]["pick_team"] == g["home_team"]
            p_key = None
        else:
            p_off, off_home, p_key = p_calc, p_calc > 0.5, None
        if p_key is None:
            p_key = ctx.keynum(now).cover_probs(m, L)[0]
        rec1, rec3 = proj.get((gid, "proj-poisson-v1")), proj.get((gid, "proj-players-v3"))
        flags = []
        if rec1 and bucket == "live":
            p_v1, P_v1 = _f(rec1["proj_p_home_cover"]), _f(rec1["proj_line"])
        else:
            rt, q = ctx.v1(g["week"], g["home_team"], g["away_team"])
            x = _proj(rt, q)
            p_v1, P_v1 = x.p_home_cover(L), x.model_line()
            flags.append("v1_recomputed")
        p_v3 = P_v3 = None
        if rec3 and bucket == "live" and _f(rec3["proj_p_home_cover"]) is not None:
            p_v3, P_v3 = _f(rec3["proj_p_home_cover"]), _f(rec3["proj_line"])
        row = {"game_id": gid, "week": g["week"], "bucket": bucket, "home": g["home_team"], "away": g["away_team"],
               "L": L, "m": m, "T": T, "margin": g["result"], "close": -g["spread_line"], "now": now.isoformat(),
               "lock": g["lock_utc"].isoformat(), "p_off": p_off, "p_calc": p_calc, "off_home": off_home,
               "p_key": p_key, "p_v1": p_v1, "P_v1": P_v1, "p_v3": p_v3, "P_v3": P_v3, "flags": flags,
               "market_src": None, "snap": [], "m_earlier": None}
        if bucket == "live":
            fl = pr["flags"] or ""
            row["market_src"] = ("oddspapi" if "ODDSPAPI" in fl or "ODDSLINK" in fl
                                 else "pinnacle" if pr["feature_version"] == "market:pinnacle" else "median")
            row["snap"] = _snapshot(caps, gid, now)
            row["m_earlier"] = _earlier(caps, gid, g["lock_utc"])
        rows.append(row)
    need = [r["game_id"] for r in rows if r["p_v3"] is None]
    try:
        v3 = _v3(ctx, need)
    except Exception as e:                         # v3 inputs unavailable: those games keep no v3
        print("v3 recompute failed:", repr(e)[:200])
        v3 = {}
    for r in rows:
        if r["p_v3"] is None and r["game_id"] in v3:
            r["p_v3"], r["P_v3"] = v3[r["game_id"]].p_home_cover(r["L"]), v3[r["game_id"]].model_line()
            r["flags"].append("v3_recomputed")
    for r in rows:
        r["_td"] = ctx.tdist(_t(r["now"]))
    return rows


# ---------------------------------------------------------------- candidates

def _side(p):
    return None if p is None else p > 0.5


def _hyb(r, fill):
    """Hybrid rule with a given no-move fill (True = home, None = missing -> official)."""
    if abs(r["m"] - r["L"]) >= hybrid.MIN_MOVE or fill is None:
        return r["off_home"]
    return fill


def _invert(td, b, q, T):
    grid = np.arange(b - 3, b + 3.001, 0.05)
    p = td.sf(np.full(grid.size, -b), grid, np.full(grid.size, T))
    return float(grid[np.argmin(np.abs(p - q))])


def _market_c1(r):
    if r["bucket"] != "live" or r["market_src"] == "oddspapi":
        return r["m"]
    fresh = [s for s in r["snap"] if s["fresh"]]
    pin = [s["spread"] for s in fresh if s["book"] == "pinnacle"]
    if pin:
        return pin[0]
    if len(fresh) >= 3:
        return statistics.median(s["spread"] for s in fresh)
    return r["m"]


def _market_c2(r):
    if r["bucket"] != "live" or r["market_src"] == "oddspapi":
        return r["m"]
    src = [s for s in r["snap"] if s["book"] == "pinnacle"] if r["market_src"] == "pinnacle" else r["snap"]
    adj = [_invert(r["_td"], s["spread"], (1 / s["price"]) / (1 + HOLD.get(s["book"], HOLD_OTHER)), r["T"])
           for s in src if s["price"]]
    return statistics.median(adj) if adj else r["m"]


def _k_by_week(rows):
    lv = [r for r in rows if r["bucket"] == "live" and r["m_earlier"] is not None]
    out = {}
    for w in sorted({r["week"] for r in rows}):
        tr = [r for r in lv if r["week"] < w]
        if len(tr) < K_MIN_GAMES:
            out[w] = 0.0
            continue
        x = np.array([r["m"] - r["m_earlier"] for r in tr])
        y = np.array([r["close"] - r["m"] for r in tr])
        out[w] = float(np.clip((x @ y) / (x @ x), 0, 1)) if (x @ x) > 0 else 0.0
    return out


def _agree(r):
    s = [x["spread"] for x in r["snap"]]
    if not s or r["m"] == r["L"]:
        return None
    side = np.sign(r["m"] - r["L"])
    return float(np.mean([np.sign(b - r["L"]) == side for b in s]))


def _straddle(L, m):
    lo, hi = min(L, m), max(L, m)
    return any(lo <= k * sg <= hi for k in KEYS for sg in (1, -1)) and L != m


def apply(rows: list[dict], w: float) -> None:
    K = _k_by_week(rows)
    for r in rows:
        td, L, T = r["_td"], r["L"], r["T"]
        pv = lambda mk: td.cover_probs(mk, L, T)[0]
        v1, v3, key = _side(r["p_v1"]), _side(r["p_v3"]), _side(r["p_key"])
        hyb = _hyb(r, v1)
        r["picks"] = {"official": r["off_home"], "keynum": key, "v1": v1, "v3": v3, "hybrid": hyb}
        r["probs"] = {"official": r["p_off"]}
        c = {}
        r["k"] = K[r["week"]]
        r["m_c1"], r["m_c2"] = _market_c1(r), _market_c2(r)
        r["m_c3"] = (r["m"] + r["k"] * (r["m"] - r["m_earlier"])
                     if r["bucket"] == "live" and r["m_earlier"] is not None else r["m"])
        for k in ("C1", "C2", "C3"):
            mk = r["m_" + k.lower()]
            if mk == r["m"]:                       # same market as the official pick: same pick
                c[k], r["probs"][k] = r["off_home"], r["p_off"]
            else:
                r["probs"][k] = pv(mk)
                c[k] = r["probs"][k] > 0.5
        r["agree"] = _agree(r) if r["bucket"] == "live" else None
        gate = r["agree"] is not None and abs(r["m"] - L) >= hybrid.MIN_MOVE and r["agree"] < AGREE_MIN
        c["C4"] = (v1 if v1 is not None else r["off_home"]) if gate else hyb
        Ps = {"C5a": r["P_v1"], "C5b": r["P_v3"],
              "C5c": None if r["P_v1"] is None or r["P_v3"] is None else (r["P_v1"] + r["P_v3"]) / 2}
        for k, Pj in Ps.items():
            if Pj is None:
                c[k], r["probs"][k] = r["off_home"], r["p_off"]
            else:
                r["probs"][k] = pv(r["m"] + w * (Pj - r["m"]))
                c[k] = r["probs"][k] > 0.5
        avg = None if r["p_v1"] is None or r["p_v3"] is None else (r["p_v1"] + r["p_v3"]) / 2 > 0.5
        c["C6a"], c["C6b"], c["C6c"] = _hyb(r, v3), _hyb(r, avg), _hyb(r, key)
        c["C7"] = (not r["off_home"]) if (v1 is not None and v3 is not None and v1 != r["off_home"]
                                          and v3 != r["off_home"]) else r["off_home"]
        votes = [x for x in r["picks"].values() if x is not None]
        h = sum(votes)
        c["C8"] = r["off_home"] if 2 * h == len(votes) else 2 * h > len(votes)
        c["C9"] = key if (_straddle(L, r["m"]) and key is not None) else r["off_home"]
        r["picks"].update(c)
        r["home_cov"] = r["margin"] > -L
        r["cov_margin"] = r["margin"] + L          # home's margin over the pool line


# ---------------------------------------------------------------- statistics

def binom_sf(k: int, n: int) -> float:
    """P(X >= k), X ~ Bin(n, 1/2)."""
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n if n else 1.0


def holm(ps: dict[str, float], alpha=0.05) -> dict[str, bool]:
    order = sorted(ps, key=ps.get)
    out, ok = {}, True
    for i, k in enumerate(order):
        ok = ok and ps[k] <= alpha / (len(order) - i)
        out[k] = ok
    return out


def _wk_boot(rows, f, n=4000, seed=7):
    rng = np.random.default_rng(seed)
    wk = sorted({r["week"] for r in rows})
    G = {w: [r for r in rows if r["week"] == w] for w in wk}
    vals = []
    for _ in range(n):
        s = [x for w in rng.choice(wk, len(wk)) for x in G[w]]
        vals.append(f(s))
    return float(np.quantile(vals, .025)), float(np.quantile(vals, .975))


def _cm(r, k):
    p = r["picks"][k]
    return None if p is None else (r["cov_margin"] if p else -r["cov_margin"])


def evaluate(rows: list[dict]) -> dict:
    out = {"n": len(rows), "buckets": {}, "records": {}, "primary": {}, "secondary": {}}
    for b in ("early", "live", "rebuilt", "all"):
        rs = [r for r in rows if b == "all" or r["bucket"] == b]
        out["buckets"][b] = len(rs)
        rec = {}
        for k in TRACKED + CANDS:
            g = [r for r in rs if r["picks"][k] is not None]
            wns = sum(r["picks"][k] == r["home_cov"] for r in g)
            rec[k] = [wns, len(g) - wns]
        out["records"][b] = rec
    ps = {}
    for k in CANDS:
        d = [r for r in rows if r["picks"][k] != r["picks"]["official"]]
        wc = sum(r["picks"][k] == r["home_cov"] for r in d)
        ps[k] = binom_sf(wc, len(d))
        bk = {b: [sum(r["picks"][k] == r["home_cov"] for r in d if r["bucket"] == b),
                  sum(r["bucket"] == b for r in d)] for b in ("early", "live", "rebuilt")}
        out["primary"][k] = {"differ": len(d), "cand_wins": wc, "official_wins": len(d) - wc, "p": ps[k],
                             "by_bucket": bk}
    for k, ok in holm(ps).items():
        out["primary"][k]["holm_pass"] = ok
    for k in CANDS:
        diff = lambda s: float(np.mean([_cm(r, k) - _cm(r, "official") for r in s])) if s else 0.0
        sec = {"cover_margin_diff": diff(rows), "ci95": _wk_boot(rows, diff)}
        if k in PROB_CANDS:
            y = np.array([r["home_cov"] for r in rows], float)
            pc, po = (np.array([r["probs"][x] for r in rows]) for x in (k, "official"))
            sec["brier"], sec["brier_official"] = float(np.mean((pc - y) ** 2)), float(np.mean((po - y) ** 2))
        for ref in ("hybrid",) if k in ("C4", "C6a", "C6b", "C6c") else ():
            d = [r for r in rows if r["picks"][k] != r["picks"][ref]]
            sec["vs_hybrid"] = [sum(r["picks"][k] == r["home_cov"] for r in d), len(d)]
        out["secondary"][k] = sec
    n = len(rows)
    lo = next(k for k in range(n + 1) if 1 - binom_sf(k + 1, n) >= 0.025)
    out["null_band_wins"] = [lo, n - lo]
    return out


# ---------------------------------------------------------------- history

def _sbro_set():
    sched, _ = nflverse.pull("schedules", save=False)
    reg = sched.filter(pl.col("game_type") == "REG", pl.col("result").is_not_null(),
                       pl.col("spread_line").is_not_null(), pl.col("total_line").is_not_null())
    base = reg.select("game_id", "season", "week", "home_team", "away_team", pl.col("result").alias("margin"),
                      (-pl.col("spread_line")).alias("close"), pl.col("total_line").alias("total"))
    sb = sbro.match_schedule(sbro.load_all(config.ROOT / "data" / "raw" / "sbro"), sched) \
        .select("game_id", pl.col("open_home_spread").alias("open"))
    return base.join(sb, on="game_id", how="left"), sched


def _v1_hist(d: pl.DataFrame, sched) -> np.ndarray:
    import nflreadpy as nfl
    from engine.backtest import projection_eval as PE
    games = P.team_games(nfl.load_team_stats(seasons=list(range(1999, 2022))), sched)
    pr = PE.project_games(games, d.select("game_id", "season", "week", "home_team", "away_team"),
                          final.PROJ_H, final.PROJ_LAM)
    return np.array([x.model_line() if x else np.nan for x in pr])


def history() -> dict:
    df, sched = _sbro_set()
    d = df.filter(pl.col("season").is_between(2007, 2021), pl.col("open").is_not_null()) \
        .filter(pl.col("open").map_elements(is_half_point, return_dtype=pl.Boolean)).sort("season", "week")
    Pv = _v1_hist(d, sched)
    L, m, T, M, s = (d[c].to_numpy() for c in ("open", "close", "total", "margin", "season"))
    fit = (s <= 2013) & ~np.isnan(Pv)
    x, y = (m - Pv)[fit], (M + m)[fit]
    w = float(np.clip((x @ y) / (x @ x), 0, 1))
    out = {"w": w, "w_raw": float((x @ y) / (x @ x)), "w_fit_games": int(fit.sum())}
    sets = {}
    po, pk, pb = (np.full(d.height, np.nan) for _ in range(3))
    for yr in range(2007, 2022):
        tr = df.filter(pl.col("season") < yr)
        td = TotalDist("shifted_total").fit(tr["close"].to_numpy(), tr["margin"].to_numpy(), tr["total"].to_numpy())
        kd = MarginDist(kind=final.SHADOW).fit(tr["close"].to_numpy(), tr["margin"].to_numpy())
        k = s == yr
        po[k] = td.sf(-L[k], m[k], T[k])
        pk[k] = kd.sf(-L[k], m[k])
        mb = np.where(np.isnan(Pv[k]), m[k], m[k] + w * (Pv[k] - m[k]))
        pb[k] = td.sf(-L[k], mb, T[k])
    sets["sbro_2014_2021"] = _hist_compare(s >= 2014, L, m, M, po, pk, pb)
    sets["cbs2025"] = _cbs2025(w)
    out["sets"] = sets
    return out


def _hist_compare(mask, L, m, M, po, pk, pb):
    y = (M > -L)
    off = po > 0.5
    c = {"C5a": pb > 0.5, "C6c": np.where(np.abs(m - L) >= 1, off, pk > 0.5),
         "C9": np.where([_straddle(a, b) for a, b in zip(L, m)], pk > 0.5, off)}
    res = {"games": int(mask.sum()), "official": [int((off == y)[mask].sum()), int(mask.sum())]}
    for k, v in c.items():
        dd = mask & (v != off)
        res[k] = {"differ": int(dd.sum()), "cand_wins": int((v == y)[dd].sum()),
                  "net": int((v == y)[dd].sum() - (off == y)[dd].sum())}
    return res


def _cbs2025(w):
    g = pl.read_csv(config.ROOT / "data/backtests/players2025_games.csv").filter(pl.col("half"))
    sched, _ = nflverse.pull("schedules", save=False)
    reg = sched.filter(pl.col("game_type") == "REG", pl.col("result").is_not_null(),
                       pl.col("spread_line").is_not_null(), pl.col("total_line").is_not_null())
    g = g.join(reg.select("game_id", pl.col("total_line").alias("T")), on="game_id")
    tr = reg.filter(pl.col("season") < 2025)
    c, M0, T0 = -tr["spread_line"].to_numpy(), tr["result"].to_numpy(), tr["total_line"].to_numpy()
    td = TotalDist("shifted_total").fit(c, M0, T0)
    kd = MarginDist(kind=final.SHADOW).fit(c, M0)
    L, m, M, T, Pv = (g[x].to_numpy().astype(float) for x in ("open", "close", "margin", "T", "line_v1"))
    po, pk = td.sf(-L, m, T), kd.sf(-L, m)
    pb = td.sf(-L, m + w * (Pv - m), T)
    return _hist_compare(np.ones(g.height, bool), L, m, M, po, pk, pb)


# ---------------------------------------------------------------- run

def run(out_path=None) -> dict:
    hist = history()
    rows = build()
    apply(rows, hist["w"])
    res = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(), "w": hist["w"], "history": hist,
           "results": evaluate(rows), "method_check": _method_check(rows)}
    keep = ("game_id", "week", "bucket", "home", "away", "L", "m", "T", "margin", "close", "p_off", "p_key",
            "p_v1", "P_v1", "p_v3", "P_v3", "flags", "market_src", "m_earlier", "m_c1", "m_c2", "m_c3", "k",
            "agree", "picks", "probs", "home_cov")
    res["games"] = [{k: r.get(k) for k in keep} for r in rows]
    p = out_path or config.ROOT / "data/backtests/variants2026.json"
    p.write_text(json.dumps(res, indent=1, default=str))
    return res


def _method_check(rows):
    lv = [r for r in rows if r["bucket"] == "live"]
    pin = [r for r in lv if r["market_src"] == "pinnacle"]
    med = [r for r in lv if r["market_src"] == "median"]
    pin_ok = sum(any(s["book"] == "pinnacle" and s["spread"] == r["m"] for s in r["snap"]) for r in pin)
    med_ok = sum(bool(r["snap"]) and statistics.median(s["spread"] for s in r["snap"]) == r["m"] for r in med)
    p_ok = sum(abs(r["p_calc"] - r["p_off"]) < 0.005 for r in rows)
    side_ok = sum((r["p_calc"] > 0.5) == r["off_home"] for r in rows)
    return {"live_pinnacle_in_snapshot": [pin_ok, len(pin)], "live_median_reproduced": [med_ok, len(med)],
            "p_off_reproduced_0.005": [p_ok, len(rows)], "official_side_reproduced": [side_ok, len(rows)],
            "snapshot_books_median": statistics.median(len(r["snap"]) for r in lv) if lv else 0,
            "live_with_earlier_line": sum(r["m_earlier"] is not None for r in lv)}


if __name__ == "__main__":
    r = run()
    print(json.dumps({k: r[k] for k in ("w", "method_check")}, default=str))
