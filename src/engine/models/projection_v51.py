"""Projection v5.1: drive simulator with finer end-game states and a game-environment factor
(docs/projection_v51_preregistration.md).

Differences from v5: 9 score buckets x 5 periods (first-half and fourth-quarter endings separated), a ridge
penalty on state dummies, duration pools that fall back to (outcome, period) when a cell has < 30 drives,
and a per-game environment factor Z ~ N(0,1) that shifts both teams' TD logits by a*Z and FG logits by b*Z.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from engine.models.projection import FRANCHISE, MAXP
from engine.models.projection_v5 import OUTCOMES, SIMS, SMOOTH_RANGE, SimProjection  # noqa: F401 (re-export)
from engine.picks.grading import validate_league_line  # noqa: F401

VERSION = "proj-sim-v51"
BUCKETS = ("le-17", "-16..-9", "-8..-4", "-3..-1", "0", "1..3", "4..8", "9..16", "ge17")
PERIODS = ("early", "h1_final2", "q4_gt5", "q4_5to2", "q4_final2")
N_CELLS = len(BUCKETS) * len(PERIODS)
BASE_CELL = BUCKETS.index("0") * len(PERIODS) + PERIODS.index("early")
OT_CELL = BUCKETS.index("0") * len(PERIODS) + PERIODS.index("q4_final2")
RIDGE = 2.0
MIN_POOL = 30


def bucket_index(diff) -> np.ndarray:
    d = np.asarray(diff)
    return np.select([d <= -17, d <= -9, d <= -4, d <= -1, d == 0, d <= 3, d <= 8, d <= 16], list(range(8)), 8)


def period_index(half, half_secs) -> np.ndarray:
    h, s = np.asarray(half), np.asarray(half_secs)
    return np.where(h == 1, np.where(s <= 120, 1, 0),
                    np.where(s <= 120, 4, np.where(s <= 300, 3, np.where(s <= 900, 2, 0))))


def cell_index(diff, half, half_secs) -> np.ndarray:
    return bucket_index(diff) * len(PERIODS) + period_index(half, half_secs)


def _dummies(cell: np.ndarray) -> np.ndarray:
    D = np.zeros((cell.size, N_CELLS))
    D[np.arange(cell.size), cell] = 1.0
    return np.delete(D, BASE_CELL, axis=1)


@dataclass
class DriveModel:
    coef: dict
    se: dict

    @staticmethod
    def _designs(lt, lf, cell):
        D = _dummies(cell)
        one = np.ones((cell.size, 1))
        return {"TD": np.hstack([one, lt[:, None], D]), "FG": np.hstack([one, lf[:, None], D]), "OPP_TD": np.hstack([one, D])}

    @classmethod
    def fit(cls, lt, lf, cell, outcome, ridge=RIDGE, iters=60) -> "DriveModel":
        X = cls._designs(np.asarray(lt, float), np.asarray(lf, float), np.asarray(cell))
        Y = {c: (np.asarray(outcome) == c).astype(float) for c in OUTCOMES}
        sizes = [X[c].shape[1] for c in OUTCOMES]
        off = np.cumsum([0] + sizes)
        pen = np.zeros(off[-1])
        for i, c in enumerate(OUTCOMES):
            first = 2 if c in ("TD", "FG") else 1            # intercept (and gamma) unpenalised
            pen[off[i] + first: off[i + 1]] = ridge
        b = np.zeros(off[-1])
        for _ in range(iters):
            eta = np.column_stack([X[c] @ b[off[i]:off[i + 1]] for i, c in enumerate(OUTCOMES)])
            ex = np.exp(eta)
            P = ex / (1 + ex.sum(1, keepdims=True))
            g = np.concatenate([X[c].T @ (Y[c] - P[:, i]) for i, c in enumerate(OUTCOMES)]) - pen * b
            H = np.zeros((off[-1], off[-1]))
            for i, ci in enumerate(OUTCOMES):
                for j, cj in enumerate(OUTCOMES):
                    w = P[:, i] * ((i == j) - P[:, j])
                    H[off[i]:off[i + 1], off[j]:off[j + 1]] = -(X[ci].T * w) @ X[cj]
            H -= np.diag(pen)
            step = np.linalg.solve(H, -g)
            b += step
            if np.max(np.abs(step)) < 1e-9:
                break
        se = np.sqrt(np.clip(np.diag(np.linalg.inv(-H)), 0, None))
        return cls({c: b[off[i]:off[i + 1]].tolist() for i, c in enumerate(OUTCOMES)},
                   {c: se[off[i]:off[i + 1]].tolist() for i, c in enumerate(OUTCOMES)})

    def eta_table(self, lt: float, lf: float) -> np.ndarray:
        """Linear predictors (N_CELLS, 3) for TD, FG, OPP_TD."""
        cells = np.arange(N_CELLS)
        X = self._designs(np.full(N_CELLS, lt), np.full(N_CELLS, lf), cells)
        return np.column_stack([X[c] @ np.array(self.coef[c]) for c in OUTCOMES])

    def cell_table(self, lt: float, lf: float) -> np.ndarray:
        ex = np.exp(self.eta_table(lt, lf))
        P = ex / (1 + ex.sum(1, keepdims=True))
        return np.c_[P, 1 - P.sum(1)]

    def to_json(self):
        return {"coef": self.coef, "se": self.se}

    @classmethod
    def from_json(cls, j):
        return cls(j["coef"], j["se"])


SIDE_GROUPS = 3          # trailing / tied / leading (offense perspective)
WINDOW, MIN_LOCAL = 15.0, 30


def _side(cell) -> np.ndarray:
    b = np.asarray(cell) // len(PERIODS)
    tied = BUCKETS.index("0")
    return np.where(b < tied, 0, np.where(b == tied, 1, 2))


@dataclass
class DurationPool:
    """Drive clock use drawn locally in the start clock: from training drives with the same outcome, the same
    side (trailing / tied / leading), the same half, and a start clock within +-15 s of the current half clock
    (widened until >= 30 drives), capped at the clock remaining. Clock use depends on exactly when a drive starts
    (hurry-up, kneel-downs, clock management), which cell-level pools miss (amendment in
    docs/projection_v51_preregistration.md)."""
    starts: list            # per (outcome, side, half): sorted start clocks
    durs: list              # matching durations

    @staticmethod
    def _k(o, side, half):
        return (np.asarray(o) * SIDE_GROUPS + np.asarray(side)) * 2 + (np.asarray(half) - 1)

    @classmethod
    def fit(cls, outcome, cell, dur, start_clock, half) -> "DurationPool":
        oi = np.array([OUTCOMES.index(o) if o in OUTCOMES else 3 for o in outcome])
        k = cls._k(oi, _side(cell), np.asarray(half))
        sc, dur = np.asarray(start_clock, float), np.asarray(dur, float)
        starts, durs = [], []
        for key in range(4 * SIDE_GROUPS * 2):
            m = k == key
            order = np.argsort(sc[m])
            starts.append(sc[m][order]); durs.append(dur[m][order])
        return cls(starts, durs)

    def draw(self, o, cell, u, clock, half):
        keys = self._k(o, _side(cell), half)
        out = np.empty(len(keys))
        for key in np.unique(keys):
            m = np.flatnonzero(keys == key)
            st, du = self.starts[key], self.durs[key]
            c = clock[m]
            w = np.full(m.size, WINDOW)
            lo = np.searchsorted(st, c - w); hi = np.searchsorted(st, c + w, side="right")
            for _ in range(8):                      # widen sparse windows
                small = (hi - lo) < MIN_LOCAL
                if not small.any():
                    break
                w[small] *= 2
                lo[small] = np.searchsorted(st, c[small] - w[small]); hi[small] = np.searchsorted(st, c[small] + w[small], side="right")
            j = lo + np.minimum((u[m] * (hi - lo)).astype(int), np.maximum(hi - lo - 1, 0))
            out[m] = du[np.minimum(j, len(du) - 1)]
        return np.minimum(out, clock)

    def to_json(self):
        return {"starts": [x.tolist() for x in self.starts], "durs": [x.tolist() for x in self.durs]}

    @classmethod
    def from_json(cls, j):
        return cls([np.array(x) for x in j["starts"]], [np.array(x) for x in j["durs"]])


@dataclass
class SimResult:
    margin: np.ndarray
    counts: np.ndarray
    home_pts: np.ndarray
    away_pts: np.ndarray
    drives_by_half: np.ndarray


def simulate(mu_h: dict, mu_a: dict, p_xp: float, p_2: float, model: DriveModel, pool: DurationPool,
             env: tuple[float, float] = (0.0, 0.0), sims: int = SIMS, seed: int = 0) -> SimResult:
    rng = np.random.default_rng(seed)
    eta = np.stack([model.eta_table(np.log(mu_h["td"]), np.log(mu_h["fg"])),
                    model.eta_table(np.log(mu_a["td"]), np.log(mu_a["fg"]))])      # (2, N_CELLS, 3)
    z = rng.standard_normal(sims)
    shift = np.stack([env[0] * z, env[1] * z, np.zeros(sims)], 1)                # (S, 3)
    pts = np.zeros((sims, 2), int)
    cnt = np.zeros((sims, 4), int)
    ndr = np.zeros((sims, 2), int)
    per_count = np.zeros(len(PERIODS), int)            # regulation drives started in each period (diagnostic)
    first = rng.integers(0, 2, sims)

    def extra(n):
        u = rng.random(n)
        return np.where(u < p_2, 2, np.where(u < p_2 + p_xp, 1, 0))

    def drive(idx, poss, half, clock, cell_override=None):
        off = poss[idx]
        diff = pts[idx, off] - pts[idx, 1 - off]
        cell = cell_index(diff, half[idx], clock[idx]) if cell_override is None else np.full(idx.size, cell_override)
        e = np.exp(eta[off, cell] + shift[idx])
        P = e / (1 + e.sum(1, keepdims=True))
        c = np.cumsum(P, 1)
        u = rng.random(idx.size)
        o = np.minimum((u[:, None] > c).sum(1), 3)
        dur = pool.draw(o, cell, rng.random(idx.size), clock[idx], half[idx])
        td, fg, otd = o == 0, o == 1, o == 2
        scorer = np.where(otd, 1 - off, off)
        add = np.zeros(idx.size, int)
        add[td | otd] = 6 + extra(int((td | otd).sum()))
        add[fg] = 3
        np.add.at(pts, (idx, scorer), add)
        np.add.at(cnt, (idx[td | otd], 2 * scorer[td | otd]), 1)
        np.add.at(cnt, (idx[fg], 2 * scorer[fg] + 1), 1)
        return o, dur, scorer

    poss, half = first.copy(), np.ones(sims, int)
    clock = np.full(sims, 1800.0)
    active = np.ones(sims, bool)
    while active.any():
        idx = np.flatnonzero(active)
        np.add.at(ndr, (idx, half[idx] - 1), 1)
        np.add.at(per_count, period_index(half[idx], clock[idx]), 1)
        o, dur, scorer = drive(idx, poss, half, clock)
        poss[idx] = np.where(o == 3, 1 - poss[idx], 1 - scorer)
        clock[idx] -= dur
        over = idx[clock[idx] <= 0]
        h1, h2 = over[half[over] == 1], over[half[over] == 2]      # split before switching halves
        active[h2] = False
        half[h1], clock[h1], poss[h1] = 2, 1800.0, 1 - first[h1]

    tied = np.flatnonzero(pts[:, 0] == pts[:, 1])
    if tied.size:
        poss[tied] = rng.integers(0, 2, tied.size)
        clock[tied], half[tied] = 600.0, 2
        n_poss = np.zeros(sims, int)
        live = np.zeros(sims, bool); live[tied] = True
        guaranteed = np.zeros(sims, bool)
        while live.any():
            idx = np.flatnonzero(live)
            o, dur, scorer = drive(idx, poss, half, clock, cell_override=OT_CELL)
            n_poss[idx] += 1
            clock[idx] -= dur
            first_pos = n_poss[idx] == 1
            end = (o == 0) | (o == 2)
            end |= (o == 1) & ~first_pos & ~guaranteed[idx]
            guaranteed[idx[(o == 1) & first_pos]] = True
            g = guaranteed[idx] & ~first_pos
            end |= g & (o == 3)
            guaranteed[idx[g]] = False
            end |= clock[idx] <= 0
            poss[idx] = np.where(o == 3, 1 - poss[idx], 1 - scorer)
            live[idx[end]] = False
    out = SimResult(pts[:, 0] - pts[:, 1], cnt, pts[:, 0], pts[:, 1], ndr)
    out.period_drives = per_count / sims
    return out


def margin_pmf(res) -> np.ndarray:
    m = np.clip(res.margin, -MAXP, MAXP) + MAXP
    c = np.bincount(m, minlength=2 * MAXP + 1).astype(float)
    grid = np.arange(-MAXP, MAXP + 1)
    floor = (np.abs(grid) <= SMOOTH_RANGE).astype(float)
    c += floor / floor.sum()
    return c / c.sum()


def drive_training_table(drive_rows: pl.DataFrame, mu: pl.DataFrame) -> pl.DataFrame:
    d = drive_rows.filter(pl.col("half").is_in(["Half1", "Half2"]), pl.col("hs0").is_not_null()) \
        .sort("game_id", "fixed_drive") \
        .with_columns(pl.col("hs0").shift(-1).over("game_id", "half").alias("next0")) \
        .filter(pl.col("diff").is_not_null(), pl.col("res").is_not_null()) \
        .with_columns(pl.col("posteam").replace(FRANCHISE).alias("team"),
                      pl.when(pl.col("half") == "Half1").then(1).otherwise(2).alias("h"),
                      (pl.col("hs0") - pl.col("next0").fill_null(0)).alias("dur"),
                      pl.when(pl.col("res") == "Touchdown").then(pl.lit("TD"))
                      .when(pl.col("res") == "Field goal").then(pl.lit("FG"))
                      .when(pl.col("res") == "Opp touchdown").then(pl.lit("OPP_TD"))
                      .otherwise(pl.lit("NONE")).alias("outcome"))
    d = d.join(mu, on=["game_id", "team"], how="inner")
    return d.with_columns(pl.Series("cell", cell_index(d["diff"].to_numpy(), d["h"].to_numpy(), d["hs0"].to_numpy())),
                          ((pl.col("dur") >= 0) & (pl.col("dur") <= pl.col("hs0"))).alias("dur_ok"))
