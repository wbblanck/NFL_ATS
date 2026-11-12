"""On-field EPA ratings for the full-game development test (docs/gamesim_v2/PREREGISTRATION_full_game_dev.md).

One column per player on the field, by side and position group (offense QB, RB, WR, TE, OL; defense DL, LB, DB), outcome EPA of the play,
pre-snap context only. Used for dropbacks and designed runs alike. Fitting reuses the Gaussian ridge of `abilities_v2`.
"""
from __future__ import annotations

import numpy as np
import polars as pl
import scipy.sparse as sp

from . import abilities as A

OFF = ("QB", "RB", "WR", "TE", "OL")
DEF = ("DL", "LB", "DB")
GROUPS = [f"O_{g}" for g in OFF] + [f"D_{g}" for g in DEF]
LAM = {g: 100.0 for g in GROUPS}


def presnap_context(d: pl.DataFrame) -> tuple[np.ndarray, list]:
    cols, names = [], []
    dn = d["down"].fill_null(1).to_numpy()
    for v in (2, 3, 4):
        cols.append((dn == v).astype(float)); names.append(f"down={v}")
    tg = np.digitize(d["ydstogo"].fill_null(10).to_numpy(), [4, 7, 11])
    for v, nm in ((1, "togo4-6"), (2, "togo7-10"), (3, "togo11+")):
        cols.append((tg == v).astype(float)); names.append(nm)
    yl = d["yardline_100"].fill_null(50).to_numpy()
    for m, nm in ((yl <= 10, "yl<=10"), ((yl > 10) & (yl <= 20), "yl11-20"), (yl > 50, "yl>50")):
        cols.append(m.astype(float)); names.append(nm)
    cols.append(d["shotgun"].fill_null(0).to_numpy().astype(float)); names.append("shotgun")
    cols.append(d["no_huddle"].fill_null(0).to_numpy().astype(float)); names.append("no_huddle")
    sd = d["score_differential"].fill_null(0).to_numpy()
    for m, nm in ((sd <= -14, "down14+"), ((sd >= -13) & (sd <= -4), "down4-13"), ((sd >= 4) & (sd <= 13), "up4-13"), (sd >= 14, "up14+")):
        cols.append(m.astype(float)); names.append(nm)
    return np.column_stack(cols), names


def build_design_full(d: pl.DataFrame, pos: dict, player_effects: bool = True) -> tuple[A.Design, dict]:
    ctx, ctx_names = presnap_context(d)
    season = d["season"].to_list()
    offp, defp = d["offense_players"].to_list(), d["defense_players"].to_list()
    rows, keys = [], []
    missing = {"offense_slots": 0, "defense_slots": 0, "offense_unknown_pos": 0, "defense_unknown_pos": 0}
    if player_effects:
        for i in range(d.height):
            s = season[i]
            for side, plist, groups in (("O", offp[i], OFF), ("D", defp[i], DEF)):
                for p in (plist or "").split(";"):
                    if not p:
                        continue
                    missing["offense_slots" if side == "O" else "defense_slots"] += 1
                    g = pos.get((s, p))
                    if g in groups:
                        rows.append(i); keys.append(f"{side}_{g}:{p}")
                    else:
                        missing["offense_unknown_pos" if side == "O" else "defense_unknown_pos"] += 1
    uk = sorted(set(keys))
    index = {k: j for j, k in enumerate(uk)}
    P = sp.csr_matrix((np.ones(len(rows)), (np.array(rows, dtype=np.int64), np.array([index[k] for k in keys], dtype=np.int64))),
                      shape=(d.height, len(uk)))
    X = sp.hstack([sp.csr_matrix(ctx), P]).tocsr()
    names = list(ctx_names) + uk
    group = np.array(["ctx"] * len(ctx_names) + [k.split(":")[0] for k in uk])
    lam = np.array([1e-3 if g == "ctx" else LAM[g] for g in group])
    return A.Design(X, names, group, lam, ctx_names), missing
