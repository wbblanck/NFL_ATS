"""Phase 4: distribution of the final home margin given the market spread.

predicted margin = -c  (c = market home spread at lock, negative = home favored)
F(t | c) = P(margin > t | c);   P(home covers S) = F(-S | c)  for half-point S.

Estimators (docs/phase4_preregistration.md): normal, shifted empirical,
kernel-local empirical (unshifted; keeps key-number mass), and the kernel
version pooled with mirrored games.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from engine.picks.grading import validate_league_line

H_GRID = (0.5, 1.0, 1.5, 2.0, 3.0)
EPS = 1e-4


def _ncdf(x):
    return 0.5 * (1 + np.vectorize(math.erf)(np.asarray(x, float) / math.sqrt(2)))


@dataclass
class MarginDist:
    kind: str = "kernel"          # normal | shifted | kernel | kernel_sym | keynum
    h: float = 1.0
    c: np.ndarray = field(default_factory=lambda: np.zeros(0))
    m: np.ndarray = field(default_factory=lambda: np.zeros(0))
    sigma: float = 13.0

    def fit(self, close: np.ndarray, margin: np.ndarray) -> "MarginDist":
        c, m = np.asarray(close, float), np.asarray(margin, float)
        if self.kind == "kernel_sym":
            c, m = np.concatenate([c, -c]), np.concatenate([m, -m])
        self.c, self.m = c, m
        self.sigma = float(np.std(m + c))
        if self.kind == "keynum":
            self._fit_keys()
        return self

    KMAX = 20
    GRID = np.arange(-80, 81)

    def _base_pmf(self, c: np.ndarray) -> np.ndarray:
        """Discretized normal pmf over integer margins GRID, one row per c."""
        k = self.GRID[None, :]
        cc = np.asarray(c, float)[:, None]
        return _ncdf((k + 0.5 + cc) / self.sigma) - _ncdf((k - 0.5 + cc) / self.sigma)

    def _fit_keys(self) -> None:
        """w_|k| = observed count of |margin|=|k| / expected count under the base (training only)."""
        expected = np.zeros(self.KMAX + 1)
        for chunk in np.array_split(np.arange(self.c.size), max(1, self.c.size // 2000)):
            b = self._base_pmf(self.c[chunk]).sum(0)
            a = np.abs(self.GRID)
            for j in range(self.KMAX + 1):
                expected[j] += b[a == j].sum()
        am = np.abs(np.round(self.m)).astype(int)
        observed = np.array([(am == j).sum() for j in range(self.KMAX + 1)], float)
        self.w = np.where(expected > 0, observed / np.maximum(expected, 1e-12), 1.0)

    def pmf(self, c: np.ndarray) -> np.ndarray:
        """keynum: p(k | c) proportional to base(k | c) * w_|k|, renormalized."""
        b = self._base_pmf(c)
        a = np.abs(self.GRID)
        wk = np.ones(self.GRID.size)
        wk[a <= self.KMAX] = self.w[a[a <= self.KMAX]]
        p = b * wk[None, :]
        return p / p.sum(1, keepdims=True)

    def sf(self, t: np.ndarray, c: np.ndarray) -> np.ndarray:
        """P(margin > t | c), vectorized over paired arrays t, c."""
        t, c = np.atleast_1d(np.asarray(t, float)), np.atleast_1d(np.asarray(c, float))
        if self.kind == "normal":
            p = 1 - _ncdf((t + c) / self.sigma)
        elif self.kind == "keynum":
            pm = self.pmf(c)
            p = (pm * (self.GRID[None, :] > t[:, None])).sum(1)
        elif self.kind == "shifted":
            r = np.sort(self.m + self.c)
            p = 1 - np.searchsorted(r, t + c, side="right") / r.size
        else:
            w = np.exp(-0.5 * ((self.c[None, :] - c[:, None]) / self.h) ** 2)
            p = (w * (self.m[None, :] > t[:, None])).sum(1) / w.sum(1)
        return np.clip(p, EPS, 1 - EPS)

    def cover_probs(self, market_home_spread: float, league_line: float) -> tuple[float, float]:
        """(P(home covers), P(away covers)) against a half-point league line; sums to 1."""
        s = validate_league_line(league_line)
        ph = float(self.sf(np.array([-s]), np.array([market_home_spread]))[0])
        return ph, 1.0 - ph

    def median_margin(self, market_home_spread: float) -> float:
        grid = np.arange(-60, 61)
        sf = self.sf(grid - 0.5, np.full(grid.size, market_home_spread))  # P(margin >= g)
        return float(grid[np.argmax(sf < 0.5) - 1]) if (sf < 0.5).any() else float(grid[-1])

    def sensitivity(self, market_home_spread: float, league_line: float, span: float = 3.0) -> list[dict]:
        out = []
        for k in np.arange(-span, span + 0.001, 0.5):
            s = league_line + k
            if abs(abs(s) % 1 - 0.5) > 1e-9:
                continue
            ph, pa = self.cover_probs(market_home_spread, s)
            out.append({"line": s, "p_home": ph, "p_away": pa})
        return out


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(p, y) -> float:
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


def choose_h(train_c, train_m, train_season, kind="kernel") -> float:
    """Bandwidth by log loss of P(margin > -c_open-like thresholds) on the last 3 training
    seasons, fit on earlier ones. Threshold used: the game's own close (t = -c +/- 0.5 alternating),
    i.e. how well the tail around the spread is estimated. Uses training data only."""
    seasons = np.unique(train_season)
    val = np.isin(train_season, seasons[-3:])
    fit = ~val
    best, best_ll = H_GRID[0], np.inf
    t = -train_c[val] + np.where(np.arange(val.sum()) % 2 == 0, 0.5, -0.5)
    y = (train_m[val] > t).astype(float)
    for h in H_GRID:
        md = MarginDist(kind=kind, h=h).fit(train_c[fit], train_m[fit])
        ll = log_loss(md.sf(t, train_c[val]), y)
        if ll < best_ll - 1e-12:
            best, best_ll = h, ll
    return best


@dataclass
class TotalDist:
    """Margin distribution whose width depends on the market total T (docs/total_preregistration.md).
    s(T) = sigma * (alpha + beta*T) / mean|r|, fit by least squares of |r| on T (training only)."""
    kind: str = "shifted_total"   # shifted_total | normal_total
    alpha: float = 0.0
    beta: float = 0.0
    sigma: float = 13.0
    mean_abs: float = 10.0
    z: np.ndarray = field(default_factory=lambda: np.zeros(0))

    def scale(self, T):
        return self.sigma * (self.alpha + self.beta * np.asarray(T, float)) / self.mean_abs

    def fit(self, close, margin, total) -> "TotalDist":
        c, m, T = (np.asarray(x, float) for x in (close, margin, total))
        r = m + c
        a = np.abs(r)
        X = np.column_stack([np.ones_like(T), T])
        self.alpha, self.beta = np.linalg.lstsq(X, a, rcond=None)[0]
        self.sigma, self.mean_abs = float(np.std(r)), float(a.mean())
        self.z = np.sort(r / self.scale(T))
        return self

    def sf(self, t, c, T):
        t, c, T = (np.atleast_1d(np.asarray(x, float)) for x in (t, c, T))
        q = (t + c) / self.scale(T)
        if self.kind == "normal_total":
            p = 1 - _ncdf(q)
        else:
            p = 1 - np.searchsorted(self.z, q, side="right") / self.z.size
        return np.clip(p, EPS, 1 - EPS)

    def cover_probs(self, market_home_spread: float, league_line: float, total: float) -> tuple[float, float]:
        s = validate_league_line(league_line)
        ph = float(self.sf([-s], [market_home_spread], [total])[0])
        return ph, 1.0 - ph

    def median_margin(self, market_home_spread: float, total: float) -> float:
        return float(-market_home_spread + np.median(self.z) * self.scale(total))
