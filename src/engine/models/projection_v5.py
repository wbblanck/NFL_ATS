"""Projection v5: drive-by-drive game simulator (docs/projection_v5_preregistration.md).

Each drive's outcome (TD / FG / opponent TD / nothing) comes from a multinomial logit on the offense's
expected TD and FG counts for the game (v3 means with fixes 1-2, so the starting QB, injuries, rest and
travel are inside) and the game state: score bucket x period. Drive clock use is drawn from empirical
training durations in the same (outcome, state) cell. Games are simulated 20,000 times with common
random numbers; the margin pmf is the smoothed histogram.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from engine.models.projection import MAXP, PmfProjection

VERSION = "proj-sim-v5"
OUTCOMES = ("TD", "FG", "OPP_TD")                     # baseline: nothing
BUCKETS = ("trail9", "trail1_8", "tied", "lead1_8", "lead9")
PERIODS = ("early", "late", "final2")
N_CELLS = len(BUCKETS) * len(PERIODS)
BASE_CELL = BUCKETS.index("tied") * len(PERIODS) + PERIODS.index("early")
SIMS = 20_000
SMOOTH_RANGE = 60


def bucket_index(diff: np.ndarray) -> np.ndarray:
    d = np.asarray(diff)
    return np.select([d <= -9, d <= -1, d == 0, d <= 8], [0, 1, 2, 3], 4)


def period_index(half: np.ndarray, half_secs: np.ndarray) -> np.ndarray:
    """0 early (Q1-Q3 excl. last 2:00 of Q2), 1 late (Q4 > 2:00), 2 final two minutes of either half."""
    h, s = np.asarray(half), np.asarray(half_secs)
    return np.where(s <= 120, 2, np.where((h == 2) & (s <= 900), 1, 0))


def cell_index(diff, half, half_secs) -> np.ndarray:
    return bucket_index(diff) * len(PERIODS) + period_index(half, half_secs)


def _dummies(cell: np.ndarray) -> np.ndarray:
    D = np.zeros((cell.size, N_CELLS))
    D[np.arange(cell.size), cell] = 1.0
    return np.delete(D, BASE_CELL, axis=1)


# ---------------------------------------------------------------- outcome model

@dataclass
class DriveModel:
    """Multinomial logit. coef[c] for c in OUTCOMES; TD/FG designs: [1, log mu, 14 dummies]; OPP_TD: [1, 14]."""
    coef: dict
    se: dict

    @staticmethod
    def _designs(log_mu_td, log_mu_fg, cell):
        D = _dummies(cell)
        one = np.ones((cell.size, 1))
        return {"TD": np.hstack([one, log_mu_td[:, None], D]), "FG": np.hstack([one, log_mu_fg[:, None], D]),
                "OPP_TD": np.hstack([one, D])}

    @classmethod
    def fit(cls, log_mu_td, log_mu_fg, cell, outcome, iters=50) -> "DriveModel":
        X = cls._designs(np.asarray(log_mu_td, float), np.asarray(log_mu_fg, float), np.asarray(cell))
        Y = {c: (np.asarray(outcome) == c).astype(float) for c in OUTCOMES}
        sizes = [X[c].shape[1] for c in OUTCOMES]
        off = np.cumsum([0] + sizes)
        b = np.zeros(off[-1])
        for _ in range(iters):
            eta = np.column_stack([X[c] @ b[off[i]:off[i + 1]] for i, c in enumerate(OUTCOMES)])
            m = np.max(np.c_[eta, np.zeros(len(eta))], 1, keepdims=True)
            ex = np.exp(eta - m)
            P = ex / (np.exp(-m) + ex.sum(1, keepdims=True))
            g = np.concatenate([X[c].T @ (Y[c] - P[:, i]) for i, c in enumerate(OUTCOMES)])
            H = np.zeros((off[-1], off[-1]))
            for i, ci in enumerate(OUTCOMES):
                for j, cj in enumerate(OUTCOMES):
                    w = P[:, i] * ((i == j) - P[:, j])
                    H[off[i]:off[i + 1], off[j]:off[j + 1]] = -(X[ci].T * w) @ X[cj]
            step = np.linalg.solve(H - 1e-9 * np.eye(len(b)), -g)
            b += step
            if np.max(np.abs(step)) < 1e-9:
                break
        cov = np.linalg.inv(-H)
        se = np.sqrt(np.clip(np.diag(cov), 0, None))
        return cls({c: b[off[i]:off[i + 1]].tolist() for i, c in enumerate(OUTCOMES)},
                   {c: se[off[i]:off[i + 1]].tolist() for i, c in enumerate(OUTCOMES)})

    def cell_table(self, log_mu_td: float, log_mu_fg: float) -> np.ndarray:
        """P(outcome) for every state cell: (N_CELLS, 4) columns TD, FG, OPP_TD, NONE."""
        cells = np.arange(N_CELLS)
        X = self._designs(np.full(N_CELLS, log_mu_td), np.full(N_CELLS, log_mu_fg), cells)
        eta = np.column_stack([X[c] @ np.array(self.coef[c]) for c in OUTCOMES])
        ex = np.exp(eta)
        P = ex / (1 + ex.sum(1, keepdims=True))
        return np.c_[P, 1 - P.sum(1)]

    def to_json(self):
        return {"coef": self.coef, "se": self.se}

    @classmethod
    def from_json(cls, j):
        return cls(j["coef"], j["se"])


# ---------------------------------------------------------------- durations

@dataclass
class DurationPool:
    """Empirical drive durations (seconds) per (outcome, cell): padded matrix + lengths."""
    mat: np.ndarray       # (4 * N_CELLS, maxlen)
    n: np.ndarray         # (4 * N_CELLS,)

    @classmethod
    def fit(cls, outcome, cell, dur) -> "DurationPool":
        oi = np.array([OUTCOMES.index(o) if o in OUTCOMES else 3 for o in outcome])
        key = oi * N_CELLS + np.asarray(cell)
        dur = np.asarray(dur, float)
        groups = [dur[key == k] for k in range(4 * N_CELLS)]
        # an empty cell falls back to the same outcome's pool across all cells
        by_out = [dur[oi == o] for o in range(4)]
        groups = [g if g.size else by_out[k // N_CELLS] for k, g in enumerate(groups)]
        L = max(g.size for g in groups)
        mat = np.zeros((len(groups), L))
        for k, g in enumerate(groups):
            mat[k, :g.size] = g
        return cls(mat, np.array([g.size for g in groups]))

    def draw(self, outcome_idx, cell, u) -> np.ndarray:
        k = outcome_idx * N_CELLS + cell
        idx = np.minimum((u * self.n[k]).astype(int), self.n[k] - 1)
        return self.mat[k, idx]

    def to_json(self):
        return {"groups": [self.mat[k, :n].tolist() for k, n in enumerate(self.n)]}

    @classmethod
    def from_json(cls, j):
        gs = [np.array(g) for g in j["groups"]]
        L = max(g.size for g in gs)
        mat = np.zeros((len(gs), L))
        for k, g in enumerate(gs):
            mat[k, :g.size] = g
        return cls(mat, np.array([g.size for g in gs]))


# ---------------------------------------------------------------- simulation

@dataclass
class SimResult:
    margin: np.ndarray      # (S,) home - away
    drives: np.ndarray      # (S, 2) regulation drives by home / away
    cell_counts: np.ndarray  # (N_CELLS,) regulation drives started in each state cell
    counts: np.ndarray      # (S, 4) TD_h, FG_h, TD_a, FG_a (opponent TDs credited to the scoring team)
    home_pts: np.ndarray
    away_pts: np.ndarray


def simulate(mu_h: dict, mu_a: dict, p_xp: float, p_2: float, model: DriveModel, pool: DurationPool,
             sims: int = SIMS, seed: int = 0) -> SimResult:
    rng = np.random.default_rng(seed)
    tab = [model.cell_table(np.log(mu_h["td"]), np.log(mu_h["fg"])),
           model.cell_table(np.log(mu_a["td"]), np.log(mu_a["fg"]))]
    cum = [np.cumsum(t, 1) for t in tab]
    pts = np.zeros((sims, 2), int)
    cnt = np.zeros((sims, 4), int)
    ndr = np.zeros((sims, 2), int)
    ndr_half = np.zeros((sims, 2), int)             # regulation drives by half (both teams)
    cells_seen = np.zeros(N_CELLS, int)
    first = rng.integers(0, 2, sims)                 # 0 = home receives the opening kickoff

    def extra(n):
        u = rng.random(n)
        return np.where(u < p_2, 2, np.where(u < p_2 + p_xp, 1, 0))

    def drive(idx, poss, half, clock, cell_override=None):
        """One drive for the sims in idx; returns outcome index (0 TD, 1 FG, 2 OPP_TD, 3 none) and duration."""
        off = poss[idx]
        diff = pts[idx, off] - pts[idx, 1 - off]
        cell = cell_index(diff, half[idx], clock[idx]) if cell_override is None else np.full(idx.size, cell_override)
        u = rng.random(idx.size)
        c = np.where(off[:, None] == 0, cum[0][cell], cum[1][cell])
        o = (u[:, None] > c).sum(1)
        o = np.minimum(o, 3)
        dur = pool.draw(o, cell, rng.random(idx.size))
        td, fg, otd = o == 0, o == 1, o == 2
        scorer = np.where(otd, 1 - off, off)
        add = np.zeros(idx.size, int)
        add[td | otd] = 6 + extra(int((td | otd).sum()))
        add[fg] = 3
        np.add.at(pts, (idx, scorer), add)
        np.add.at(cnt, (idx[td | otd], 2 * scorer[td | otd]), 1)
        np.add.at(cnt, (idx[fg], 2 * scorer[fg] + 1), 1)
        return o, dur, scorer

    # regulation: two halves of 1,800 s
    poss = first.copy()
    half = np.ones(sims, int)
    clock = np.full(sims, 1800.0)
    active = np.ones(sims, bool)
    while active.any():
        idx = np.flatnonzero(active)
        np.add.at(ndr, (idx, poss[idx]), 1)
        np.add.at(ndr_half, (idx, half[idx] - 1), 1)
        off_ = poss[idx]
        np.add.at(cells_seen, cell_index(pts[idx, off_] - pts[idx, 1 - off_], half[idx], clock[idx]), 1)
        o, dur, scorer = drive(idx, poss, half, clock)
        # after a score the non-scoring team receives; after no score possession changes
        poss[idx] = np.where(o == 3, 1 - poss[idx], 1 - scorer)
        clock[idx] -= dur
        over = idx[clock[idx] <= 0]
        h1 = over[half[over] == 1]
        half[h1], clock[h1], poss[h1] = 2, 1800.0, 1 - first[h1]
        active[over[half[over] == 2]] = False
        active[h1] = True

    # overtime (2017+ regular-season rules, 600 s): a first-possession TD wins; a first-possession FG gives
    # the other team one possession (TD wins, FG continues, nothing loses); then the next score wins.
    tied = np.flatnonzero(pts[:, 0] == pts[:, 1])
    if tied.size:
        ot_cell = BUCKETS.index("tied") * len(PERIODS) + PERIODS.index("final2")
        poss[tied] = rng.integers(0, 2, tied.size)
        clock[tied], half[tied] = 600.0, 2
        n_poss = np.zeros(sims, int)
        live = np.zeros(sims, bool); live[tied] = True
        guaranteed = np.zeros(sims, bool)
        while live.any():
            idx = np.flatnonzero(live)
            before = pts[idx].copy()
            o, dur, scorer = drive(idx, poss, half, clock, cell_override=ot_cell)
            n_poss[idx] += 1
            clock[idx] -= dur
            first_pos = n_poss[idx] == 1
            end = (o == 0) | (o == 2)                                  # any TD ends it
            end |= (o == 1) & ~first_pos & ~guaranteed[idx]            # sudden-death FG
            # first-possession FG: opponent is guaranteed a possession
            guaranteed[idx[(o == 1) & first_pos]] = True
            # the guaranteed possession: FG ties it and play continues; nothing ends it
            g = guaranteed[idx] & ~first_pos
            end |= g & (o == 3)
            guaranteed[idx[g]] = False
            end |= clock[idx] <= 0
            poss[idx] = np.where(o == 3, 1 - poss[idx], 1 - scorer)
            live[idx[end]] = False
            del before
    out = SimResult(pts[:, 0] - pts[:, 1], ndr, cells_seen, cnt, pts[:, 0], pts[:, 1])
    out.drives_by_half = ndr_half
    return out


def margin_pmf(res: SimResult) -> np.ndarray:
    """Smoothed pmf over -MAXP..MAXP: (counts + 1/121 on each of -60..60) / (S + 1)."""
    m = np.clip(res.margin, -MAXP, MAXP) + MAXP
    c = np.bincount(m, minlength=2 * MAXP + 1).astype(float)
    grid = np.arange(-MAXP, MAXP + 1)
    floor = (np.abs(grid) <= SMOOTH_RANGE).astype(float)
    c += floor / floor.sum()
    return c / c.sum()


@dataclass
class SimProjection(PmfProjection):
    res: SimResult

    @property
    def margin_pmf(self):
        return margin_pmf(self.res)

    def mean_scores(self):
        return float(self.res.home_pts.mean()), float(self.res.away_pts.mean())

    def median_margin(self):
        return float(np.median(self.res.margin))


# ---------------------------------------------------------------- training table

def drive_training_table(drive_rows: pl.DataFrame, mu: pl.DataFrame) -> pl.DataFrame:
    """Join drives to the offense's expected counts; add state cell, outcome and clean duration.
    mu: game_id, team, mu_td, mu_fg (team = offense)."""
    from engine.models.projection import FRANCHISE
    # Duration is start-to-start: from this drive's first snap to the next drive's first snap in the same half
    # (the half's end for its last drive). This includes the last play and the time between drives; per half it
    # sums to 1,800 s. First-to-last-snap would miss about 7 s a drive and simulate too many drives.
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
