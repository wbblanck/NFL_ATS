"""Expected lineups from a pregame snapshot (gamesim v2). Availability is sampled from `p_active` (strategy stream), then each
unit is filled by snap share when active: 5 OL, 4 DL, 3 LB, 4 DB, 1 QB, and the receiver set (3 WR, 1 TE, 1 RB)."""
from __future__ import annotations

import numpy as np
import polars as pl

UNITS_OFF = {"QB": 1, "OL": 5, "WR": 3, "TE": 1, "RB": 1}
UNITS_DEF = {"DL": 4, "LB": 3, "DB": 4}


def sample_lineup(rng: np.random.Generator, snap: pl.DataFrame, team: str, offense: bool, available: dict | None = None) -> dict:
    x = snap.filter(pl.col("team") == team, pl.col("pos_grp").is_not_null())
    col = "off_share_active" if offense else "def_share_active"
    units = UNITS_OFF if offense else UNITS_DEF
    uid, grp, share, pa = x["uid"].to_list(), x["pos_grp"].to_list(), x[col].to_list(), x["p_active"].to_list()
    active = [rng.random() < p for p in pa] if available is None else [u in available for u in uid]
    out = {}
    for g, n in units.items():
        cand = sorted(((s, u) for u, gg, s, a in zip(uid, grp, share, active) if gg == g and a and s > 0), reverse=True)
        out[g] = [u for _, u in cand[:n]]
    return out
