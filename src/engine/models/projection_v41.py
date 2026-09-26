"""Projection v4.1: latent-factor joint score distribution (docs/projection_v41_preregistration.md).

Given latent factors, the four counts (TD_h, FG_h, TD_a, FG_a) are independent binomial (or Poisson) with
means mu * m. The multipliers m are mean-one lognormal factors:
  Z  game environment   TD exp(aZ)   FG exp(bZ)    (both teams)
  V  dominance          TD exp(+-eV) FG exp(+-fV)  (+ home, - away)
  W  finishing (per team) TD exp(cW) FG exp(-dW)
Integrated by Gauss-Hermite quadrature (5 nodes per factor). Fit by maximum likelihood on training seasons.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

from engine.models.projection import MAXP
from engine.picks.grading import validate_league_line

VERSION = "proj-latent-v41"
NODES = 5
KMAX = 15                      # counts above 15 carry negligible mass (15 TDs = 90+ points)
P_CAP = 0.95
_x, _w = np.polynomial.hermite_e.hermegauss(NODES)
GH_X, GH_W = _x, _w / _w.sum()
_LOGFACT = np.array([math.lgamma(k + 1) for k in range(200)])


@dataclass
class Params:
    a: float = 0.0
    b: float = 0.0
    c: float = 0.0
    d: float = 0.0
    e: float = 0.0
    f: float = 0.0
    n_td: int | None = None      # None = Poisson
    n_fg: int | None = None

    def to_json(self):
        return asdict(self)


def _logpmf(k: np.ndarray, lam: np.ndarray, n: int | None) -> tuple[np.ndarray, np.ndarray]:
    """log P(count = k) for mean lam; returns (logpmf, capped_flag)."""
    k = np.asarray(k, float)
    if n is None:
        lam = np.maximum(lam, 1e-12)
        return k * np.log(lam) - lam - _LOGFACT[k.astype(int)], np.zeros_like(lam, bool)
    p = lam / n
    capped = p > P_CAP
    p = np.clip(p, 1e-12, P_CAP)
    ki = k.astype(int)
    logc = _LOGFACT[n] - _LOGFACT[np.minimum(ki, n)] - _LOGFACT[np.maximum(n - ki, 0)]
    out = logc + k * np.log(p) + (n - k) * np.log1p(-p)
    return np.where(ki > n, -np.inf, out), capped


def _multipliers(p: Params):
    """Per quadrature node: TD/FG multipliers for home and away, shape (Z, V, W)."""
    z, v, w = np.meshgrid(GH_X, GH_X, GH_X, indexing="ij")
    ktd = math.exp((p.a ** 2 + p.e ** 2 + p.c ** 2) / 2)
    kfg = math.exp((p.b ** 2 + p.f ** 2 + p.d ** 2) / 2)
    return {"td_h": np.exp(p.a * z + p.e * v + p.c * w) / ktd, "fg_h": np.exp(p.b * z + p.f * v - p.d * w) / kfg,
            "td_a": np.exp(p.a * z - p.e * v + p.c * w) / ktd, "fg_a": np.exp(p.b * z - p.f * v - p.d * w) / kfg}


def loglik(p: Params, mu: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Total log-likelihood of observed counts y (G, 4: TD_h, FG_h, TD_a, FG_a) with means mu (G, 4).
    Returns (loglik, share of (game, node) cells where the binomial cap bound)."""
    m = _multipliers(p)
    ww = GH_W[None, None, None, :]
    capped = []

    def side(i_td, i_fg, mt, mf):
        lt, ct = _logpmf(y[:, i_td, None, None, None], mu[:, i_td, None, None, None] * mt[None], p.n_td)
        lf, cf = _logpmf(y[:, i_fg, None, None, None], mu[:, i_fg, None, None, None] * mf[None], p.n_fg)
        capped.append(ct.mean()); capped.append(cf.mean())
        return (np.exp(lt + lf) * ww).sum(-1)              # (G, Z, V)
    h = side(0, 1, m["td_h"], m["fg_h"])
    a = side(2, 3, m["td_a"], m["fg_a"])
    L = (h * a * GH_W[None, :, None] * GH_W[None, None, :]).sum((1, 2))
    return float(np.log(np.maximum(L, 1e-300)).sum()), float(np.mean(capped))


# ---------------------------------------------------------------- score pmfs

def _count_pmfs(lam: np.ndarray, n: int | None) -> np.ndarray:
    """pmf over 0..KMAX for each mean in lam (any shape) -> (..., KMAX+1), renormalised."""
    k = np.arange(KMAX + 1)
    lp, _ = _logpmf(k, lam[..., None], n)
    pm = np.exp(lp)
    return pm / pm.sum(-1, keepdims=True)


def _extras_matrix(p_xp: float, p_2: float) -> np.ndarray:
    """Row k: pmf of TD points (6k + extras) over 0..MAXP."""
    per = np.array([1 - p_xp - p_2, p_xp, p_2])
    out = np.zeros((KMAX + 1, MAXP + 1))
    ext = np.array([1.0])
    for k in range(KMAX + 1):
        if k:
            ext = np.convolve(ext, per)
        seg = ext[: max(0, MAXP + 1 - 6 * k)]
        out[k, 6 * k: 6 * k + seg.size] = seg
    return out


def _fg_matrix() -> np.ndarray:
    out = np.zeros((KMAX + 1, MAXP + 1))
    for f in range(KMAX + 1):
        if 3 * f <= MAXP:
            out[f, 3 * f] = 1.0
    return out


_FG = _fg_matrix()
_NFFT = 512


def _points(td_pm: np.ndarray, fg_pm: np.ndarray, ext: np.ndarray) -> np.ndarray:
    """Points pmf (..., MAXP+1) from TD and FG count pmfs (independent given the node)."""
    A, B = td_pm @ ext, fg_pm @ _FG
    c = np.fft.irfft(np.fft.rfft(A, _NFFT) * np.fft.rfft(B, _NFFT), _NFFT)[..., : MAXP + 1]
    c = np.clip(c, 0, None)
    return c / c.sum(-1, keepdims=True)


@dataclass
class LatentProjection:
    home_pts: np.ndarray
    away_pts: np.ndarray
    margin: np.ndarray

    @property
    def margin_pmf(self):
        return self.margin

    def mean_scores(self):
        x = np.arange(MAXP + 1)
        return float(self.home_pts @ x), float(self.away_pts @ x)

    def model_line(self):
        h, a = self.mean_scores()
        return -(h - a)

    def p_home_cover(self, league_line: float) -> float:
        s = validate_league_line(league_line)
        mg = np.arange(-MAXP, MAXP + 1)
        return float(self.margin[mg > -s].sum())

    def median_margin(self):
        mg = np.arange(-MAXP, MAXP + 1)
        return float(mg[np.searchsorted(np.cumsum(self.margin), 0.5)])


def project(mu: tuple[float, float, float, float], p_xp: float, p_2: float, p: Params) -> LatentProjection:
    """mu = (TD_h, FG_h, TD_a, FG_a) expected counts."""
    m = _multipliers(p)
    ext = _extras_matrix(p_xp, p_2)
    ph = _points(_count_pmfs(mu[0] * m["td_h"], p.n_td), _count_pmfs(mu[1] * m["fg_h"], p.n_fg), ext)  # (Z,V,W,P)
    pa = _points(_count_pmfs(mu[2] * m["td_a"], p.n_td), _count_pmfs(mu[3] * m["fg_a"], p.n_fg), ext)
    H = (ph * GH_W[None, None, :, None]).sum(2)            # (Z, V, P)
    A = (pa * GH_W[None, None, :, None]).sum(2)
    conv = np.fft.irfft(np.fft.rfft(H, _NFFT) * np.fft.rfft(A[..., ::-1], _NFFT), _NFFT)[..., : 2 * MAXP + 1]
    wzv = GH_W[:, None] * GH_W[None, :]
    margin = np.clip((conv * wzv[..., None]).sum((0, 1)), 0, None)
    home = (H * wzv[..., None]).sum((0, 1))
    away = (A * wzv[..., None]).sum((0, 1))
    return LatentProjection(home / home.sum(), away / away.sum(), margin / margin.sum())


# ---------------------------------------------------------------- fitting

def nelder_mead(f, x0, step=0.1, iters=400, tol=1e-7):
    n = len(x0)
    pts = [np.array(x0, float)] + [np.array(x0, float) + step * np.eye(n)[i] for i in range(n)]
    vals = [f(x) for x in pts]
    for _ in range(iters):
        order = np.argsort(vals)
        pts, vals = [pts[i] for i in order], [vals[i] for i in order]
        if abs(vals[-1] - vals[0]) < tol:
            break
        cen = np.mean(pts[:-1], axis=0)
        xr = cen + (cen - pts[-1]); fr = f(xr)
        if fr < vals[0]:
            xe = cen + 2 * (cen - pts[-1]); fe = f(xe)
            pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = xr, fr
        else:
            xc = cen + 0.5 * (pts[-1] - cen); fc = f(xc)
            if fc < vals[-1]:
                pts[-1], vals[-1] = xc, fc
            else:
                pts = [pts[0]] + [pts[0] + 0.5 * (x - pts[0]) for x in pts[1:]]
                vals = [vals[0]] + [f(x) for x in pts[1:]]
    i = int(np.argmin(vals))
    return pts[i], vals[i]


def fit(mu: np.ndarray, y: np.ndarray, n_td_grid, n_fg_grid, log=None) -> dict:
    """Maximum likelihood over the loadings for each (n_TD, n_FG) pair; best pair wins."""
    best, table = None, []
    for ntd in n_td_grid:
        for nfg in n_fg_grid:
            def nll(x):
                return -loglik(Params(*x, n_td=ntd, n_fg=nfg), mu, y)[0]
            x, v = nelder_mead(nll, [0.1, -0.1, 0.1, 0.1, 0.1, 0.1], step=0.15, iters=600)
            x, v = nelder_mead(nll, x, step=0.03, iters=600)            # restart to polish
            table.append({"n_td": ntd, "n_fg": nfg, "loglik": -v, "params": x.tolist()})
            if log:
                log(f"n_td={ntd} n_fg={nfg} loglik {-v:.2f} params {np.round(x, 3).tolist()}")
    # The surface has a flat ridge (finishing vs dominance loadings trade off; (e, f) -> (-e, -f) is an exact
    # symmetry). Polish the three best pairs longer, from the found point and its mirror image.
    for row in sorted(table, key=lambda r: -r["loglik"])[:3]:
        def nll(x, ntd=row["n_td"], nfg=row["n_fg"]):
            return -loglik(Params(*x, n_td=ntd, n_fg=nfg), mu, y)[0]
        x0 = np.array(row["params"])
        for start in (x0, x0 * np.array([1, 1, 1, 1, -1, -1])):
            x, v = nelder_mead(nll, start, step=0.02, iters=3000, tol=1e-10)
            if -v > row["loglik"]:
                row["loglik"], row["params"] = -v, x.tolist()
        if log:
            log(f"polished n_td={row['n_td']} n_fg={row['n_fg']} loglik {row['loglik']:.3f}")
    best = max(table, key=lambda r: r["loglik"])
    p = Params(*best["params"], n_td=best["n_td"], n_fg=best["n_fg"])
    return {"params": p, "table": table, "se": _se(p, mu, y), "cap_share": loglik(p, mu, y)[1]}


def _se(p: Params, mu, y, h=1e-3) -> list[float]:
    x0 = np.array([p.a, p.b, p.c, p.d, p.e, p.f])

    def nll(x):
        return -loglik(Params(*x, n_td=p.n_td, n_fg=p.n_fg), mu, y)[0]
    k = len(x0)
    H = np.zeros((k, k))
    f0 = nll(x0)
    for i in range(k):
        for j in range(i, k):
            ei, ej = np.eye(k)[i] * h, np.eye(k)[j] * h
            if i == j:
                H[i, i] = (nll(x0 + ei) - 2 * f0 + nll(x0 - ei)) / h ** 2
            else:
                H[i, j] = H[j, i] = (nll(x0 + ei + ej) - nll(x0 + ei - ej) - nll(x0 - ei + ej) + nll(x0 - ei - ej)) / (4 * h * h)
    try:
        return np.sqrt(np.clip(np.diag(np.linalg.inv(H)), 0, None)).tolist()
    except np.linalg.LinAlgError:
        return [float("nan")] * k


def simulate(p: Params, mu: np.ndarray, draws: int, seed: int) -> np.ndarray:
    """Counts (draws, G, 4) from the fitted model at means mu."""
    rng = np.random.default_rng(seed)
    G = mu.shape[0]
    z, v = rng.standard_normal((draws, G)), rng.standard_normal((draws, G))
    wh, wa = rng.standard_normal((draws, G)), rng.standard_normal((draws, G))
    ktd = math.exp((p.a ** 2 + p.e ** 2 + p.c ** 2) / 2)
    kfg = math.exp((p.b ** 2 + p.f ** 2 + p.d ** 2) / 2)
    lam = np.stack([mu[:, 0] * np.exp(p.a * z + p.e * v + p.c * wh) / ktd, mu[:, 1] * np.exp(p.b * z + p.f * v - p.d * wh) / kfg,
                    mu[:, 2] * np.exp(p.a * z - p.e * v + p.c * wa) / ktd, mu[:, 3] * np.exp(p.b * z - p.f * v - p.d * wa) / kfg], -1)
    out = np.empty_like(lam)
    for i, n in ((0, p.n_td), (1, p.n_fg), (2, p.n_td), (3, p.n_fg)):
        out[..., i] = rng.poisson(lam[..., i]) if n is None else rng.binomial(n, np.clip(lam[..., i] / n, 0, P_CAP))
    return out
