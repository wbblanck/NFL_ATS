"""Phase 5 calibration: Platt, isotonic (PAV), Platt + key-number term.
All fits are chronological: callers pass only past predictions. numpy only."""
from __future__ import annotations

import numpy as np

EPS = 1e-4
KEYS = (-7.0, -3.0, 3.0, 7.0)
ECE_EDGES = np.array([0.40, 0.42, 0.44, 0.46, 0.48, 0.50, 0.52, 0.54, 0.56, 0.58, 0.60])  # 12 buckets


def logit(p):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def expit(z):
    return 1 / (1 + np.exp(-np.asarray(z, float)))


def key_feature(league_line, close):
    """Signed count of key margins between the home threshold t=-S and the market centre m=-c."""
    t, m = -np.asarray(league_line, float), -np.asarray(close, float)
    k = np.zeros_like(t)
    for K in KEYS:
        k += ((t < K) & (K <= m)).astype(float) - ((m <= K) & (K < t)).astype(float)
    return k


def fit_logistic(X, y, iters=100, ridge=1e-6):
    X = np.column_stack([np.ones(len(y)), X])
    b = np.zeros(X.shape[1])
    for _ in range(iters):
        p = expit(X @ b)
        H = X.T @ (X * (p * (1 - p))[:, None]) + ridge * np.eye(X.shape[1])
        step = np.linalg.solve(H, X.T @ (y - p) - ridge * b)
        b += step
        if np.max(np.abs(step)) < 1e-10:
            break
    return b


def platt(p_tr, y_tr, extra_tr=None):
    X = logit(p_tr)[:, None] if extra_tr is None else np.column_stack([logit(p_tr), extra_tr])
    b = fit_logistic(X, y_tr)

    def apply(p, extra=None):
        Z = logit(p)[:, None] if extra is None else np.column_stack([logit(p), extra])
        return expit(b[0] + Z @ b[1:])
    apply.coef = b
    return apply


def isotonic(p_tr, y_tr, lo=0.01, hi=0.99):
    """Pool-adjacent-violators; prediction = step function, flat outside the training range."""
    o = np.argsort(p_tr)
    x, y = np.asarray(p_tr, float)[o], np.asarray(y_tr, float)[o]
    blocks = [[yi, 1.0, xi, xi] for xi, yi in zip(x, y)]  # mean, weight, xmin, xmax
    out = []
    for b in blocks:
        out.append(b)
        while len(out) > 1 and out[-2][0] > out[-1][0]:
            m2, w2, a2, _ = out.pop(-2)
            m1, w1, _, z1 = out.pop(-1)
            out.append([(m1 * w1 + m2 * w2) / (w1 + w2), w1 + w2, a2, z1])
    xs = np.array([b[3] for b in out])
    vals = np.clip(np.array([b[0] for b in out]), lo, hi)

    def apply(p, extra=None):
        i = np.searchsorted(xs, np.asarray(p, float), side="left")
        return vals[np.clip(i, 0, len(vals) - 1)]
    return apply


def log_loss(p, y):
    p = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(p, y):
    return float(np.mean((p - y) ** 2))


def reliability(p, y):
    b = np.digitize(p, ECE_EDGES)   # 0..11
    rows = []
    for k in range(len(ECE_EDGES) + 1):
        mask = b == k
        lo = "<0.40" if k == 0 else f"{ECE_EDGES[k-1]:.2f}"
        hi = "" if k == 0 else ("+" if k == len(ECE_EDGES) else f"–{ECE_EDGES[k]:.2f}")
        n = int(mask.sum())
        rows.append({"bucket": lo + hi, "n": n,
                     "mean_p": float(p[mask].mean()) if n else float("nan"),
                     "hit_rate": float(y[mask].mean()) if n else float("nan")})
    return rows


def ece(p, y):
    rows = reliability(p, y)
    n = sum(r["n"] for r in rows)
    return float(sum(r["n"] * abs(r["mean_p"] - r["hit_rate"]) for r in rows if r["n"]) / n)
