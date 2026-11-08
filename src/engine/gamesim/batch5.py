"""Batch 5 models (nfl-betting-model docs/batch5_preregistration.md): bivariate touchdowns (S1), key-number margins (K1), Elo with a
market start (R1) and a ridge least-squares rating (R2)."""
from __future__ import annotations

import math

import numpy as np
import polars as pl

from . import elo as E, tdfg as T

M = np.arange(-60, 61)
KMAX = 40


# ---------------------------------------------------------------- S1 bivariate touchdowns
def pois(mu, n):
    k = np.arange(n + 1)
    mu = np.asarray(mu, float)[:, None]
    return np.exp(k * np.log(np.maximum(mu, 1e-300)) - mu - np.array([math.lgamma(i + 1) for i in k]))


def lam0(c0, level, lt_h, lt_a):
    return np.minimum(c0 * np.asarray(level, float), 0.95 * np.minimum(lt_h, lt_a))


def s1_margin(d, level, k, c0, kmax=10):
    """(G, 201) distribution of the home margin -100..100 under S1 (batch 3 constants k, shared touchdown rate c0*L)."""
    th, ta = T.rates(d, level, k["c_T"], k["b_T"])
    fh, fa = T.rates(d, level, k["c_F"], k["b_F"])
    l0 = lam0(c0, level, th, ta)
    tab = T.td_points_table(np.asarray(k["p"], float))
    p0 = pois(l0, kmax)
    xh, xa = pois(th - l0, T.NT), pois(ta - l0, T.NT)
    pf_h, pf_a = np.zeros((len(d), E.MAXPTS + 1)), np.zeros((len(d), E.MAXPTS + 1))
    pf_h[:, 0:3 * T.NF + 1:3] = pois(fh, T.NF)
    pf_a[:, 0:3 * T.NF + 1:3] = pois(fa, T.NF)
    ps = np.zeros(E.MAXPTS + 1)
    ps[0:2 * T.NS + 1:2] = pois([k["s"]], T.NS)[0]
    out = np.zeros((len(d), 2 * E.MAXPTS + 1))
    for i in range(len(d)):
        fsh = np.convolve(pf_h[i], ps)[: E.MAXPTS + 1]
        fsa = np.convolve(pf_a[i], ps)[: E.MAXPTS + 1]
        for s in range(kmax + 1):
            w = p0[i, s]
            if w < 1e-12:
                continue
            # touchdown points with s shared touchdowns added to each side
            rows = tab[s: s + T.NT + 1]
            rows = np.vstack([rows, np.zeros((T.NT + 1 - len(rows), E.MAXPTS + 1))]) if len(rows) < T.NT + 1 else rows
            ph = np.convolve(xh[i] @ rows, fsh)[: E.MAXPTS + 1]
            pa = np.convolve(xa[i] @ rows, fsa)[: E.MAXPTS + 1]
            md = np.convolve(ph, pa[::-1])  # index j -> margin j - MAXPTS
            out[i] += w * md
    return out


def s1_nll(c0, th_obs, ta_obs, level, lt_h, lt_a, kmax=10):
    l0 = lam0(c0, level, lt_h, lt_a)
    ll = 0.0
    for i in range(len(th_obs)):
        a, b = int(th_obs[i]), int(ta_obs[i])
        tot = 0.0
        for s in range(min(a, b, kmax) + 1):
            tot += (math.exp(-l0[i]) * l0[i] ** s / math.factorial(s)
                    * math.exp(-(lt_h[i] - l0[i])) * (lt_h[i] - l0[i]) ** (a - s) / math.factorial(a - s)
                    * math.exp(-(lt_a[i] - l0[i])) * (lt_a[i] - l0[i]) ** (b - s) / math.factorial(b - s))
        ll += math.log(max(tot, 1e-300))
    return -ll


def fit_c0(th_obs, ta_obs, level, lt_h, lt_a, hi=0.05):
    f = lambda c: s1_nll(c, th_obs, ta_obs, level, lt_h, lt_a)  # noqa: E731
    c = E._golden(f, 0.0, hi)
    return 0.0 if f(0.0) <= f(c) else c


# ---------------------------------------------------------------- K1 key-number margins
def k1_dist(mu, sigma, w):
    """(G, 121) P(margin = m) proportional to phi((m - mu)/sigma) * w_|m|; w has KMAX+1 entries, 1 beyond."""
    ww = np.ones(len(M))
    a = np.abs(M)
    ww[a <= KMAX] = np.asarray(w, float)[a[a <= KMAX]]
    z = (M[None, :] - np.asarray(mu, float)[:, None]) / sigma
    p = np.exp(-0.5 * z * z) * ww[None, :]
    return p / p.sum(1, keepdims=True)


def _lp(pm, m):
    idx = np.clip(np.asarray(m, int) + 60, 0, len(M) - 1)
    return np.log(np.maximum(pm[np.arange(len(idx)), idx], 1e-300))


def fit_k1(mu, m):
    ones = np.ones(KMAX + 1)
    sig = E._golden(lambda s: -_lp(k1_dist(mu, s, ones), m).sum(), 5.0, 25.0)
    base = k1_dist(mu, sig, ones)
    a = np.abs(np.asarray(m, int))
    w = np.array([np.mean(a == k) / max(base[:, np.abs(M) == k].sum(1).mean(), 1e-9) for k in range(KMAX + 1)])
    w = np.where(w > 0, w, 0.05)  # a margin never seen in the fit seasons keeps a small weight
    sig2 = E._golden(lambda s: -_lp(k1_dist(mu, s, w), m).sum(), 5.0, 25.0)
    return {"sigma0": sig, "sigma": sig2, "w": w.tolist()}


# ---------------------------------------------------------------- R1 Elo with a market start
def fair(d, level, b):
    mh, ma = E.means(d, level, b)
    return mh - ma


def run_market_start(games: pl.DataFrame, k, h, c, b, level: dict, close: dict) -> pl.DataFrame:
    """As elo.run, but before each season's first week every team in a week-1 game is moved so that Elo's week-1 fair
    margin equals the closing spread (nflverse sign); half the gap to each team, in Elo points by the local slope."""
    R: dict[str, float] = {}
    rows = []
    for season in sorted(games["season"].unique().to_list()):
        for t in list(R):
            R[t] += c * (E.MEAN - R[t])
        s = games.filter(pl.col("season") == season)
        weeks = sorted(s["week"].unique().to_list())
        for r in s.filter(pl.col("week") == weeks[0]).iter_rows(named=True):
            cl = close.get(r["game_id"])
            if cl is None or r["game_id"] not in level:
                continue
            ht, at = r["home_team"], r["away_team"]
            hh = 0.0 if r["neutral"] else h
            d = R.get(ht, E.START) - R.get(at, E.START) + hh
            lv = level[r["game_id"]]
            f0 = float(fair([d], [lv], b)[0])
            slope = float((fair([d + 1.0], [lv], b)[0] - fair([d - 1.0], [lv], b)[0]) / 2.0)
            x = (cl - f0) / slope / 2.0
            R[ht] = R.get(ht, E.START) + x
            R[at] = R.get(at, E.START) - x
        for week in weeks:
            upd = []
            for r in s.filter(pl.col("week") == week).iter_rows(named=True):
                ht, at = r["home_team"], r["away_team"]
                rh, ra = R.get(ht, E.START), R.get(at, E.START)
                hh = 0.0 if r["neutral"] else h
                rows.append({"game_id": r["game_id"], "d": rh - ra + hh})
                upd.append((ht, at, rh, ra, r["result"], hh))
            for ht, at, rh, ra, m, hh in upd:
                x = E.update(rh, ra, m, k, hh)
                R[ht], R[at] = rh + x, ra - x
    return pl.DataFrame(rows)


# ---------------------------------------------------------------- R2 ridge least-squares rating
def ridge_run(games: pl.DataFrame, h: float, lam: float, rho: float) -> pl.DataFrame:
    """games: season, week, game_id, home_team, away_team, result, neutral (regular season only). Each week's forecast
    uses ratings fit on that season's earlier games, shrunk toward rho times last season's end ratings."""
    teams = sorted(set(games["home_team"].to_list()) | set(games["away_team"].to_list()))
    ix = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    prev = np.zeros(n)
    rows = []
    for season in sorted(games["season"].unique().to_list()):
        s = games.filter(pl.col("season") == season).sort("week", "game_id")
        prior = rho * prev
        hi = s["home_team"].to_list()
        ai = s["away_team"].to_list()
        res = s["result"].to_numpy().astype(float)
        hv = np.where(s["neutral"].to_numpy(), 0.0, h)
        wk = s["week"].to_numpy()
        gid = s["game_id"].to_list()

        def solve(mask):
            A = np.zeros((int(mask.sum()), n))
            y = (res - hv)[mask]
            for r_, j in enumerate(np.where(mask)[0]):
                A[r_, ix[hi[j]]] += 1.0
                A[r_, ix[ai[j]]] -= 1.0
            return np.linalg.solve(A.T @ A + lam * np.eye(n), A.T @ y + lam * prior)
        for w in np.unique(wk):
            r = solve(wk < w)
            for j in np.where(wk == w)[0]:
                rows.append({"game_id": gid[j], "ridge": float(r[ix[hi[j]]] - r[ix[ai[j]]] + hv[j])})
        prev = solve(np.ones(len(wk), bool))
    return pl.DataFrame(rows)
