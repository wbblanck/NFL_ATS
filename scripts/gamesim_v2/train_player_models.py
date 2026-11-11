"""Gamesim v2, sprint 1: tune (dev) and validate the on-field pressure and completion models.

  dev       grid over ridge strength and decay half-life, evaluated on the 2020 season only (development season).
  validate  frozen config from data/gamesim_v2/manifests/g2_frozen_config.json, evaluated on 2021 (validation).
Seasons 2022-2025 are the locked holdout (the span of the G1 confirmation): this script never loads them.
Usage: python scripts/gamesim_v2/train_player_models.py dev|validate"""
from __future__ import annotations

import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np
import polars as pl

from engine.gamesim_v2.validation import play_validation as V

ROOT = Path(__file__).resolve().parents[2]
FEAT = ROOT / "data/gamesim_v2/features"
MAN = ROOT / "data/gamesim_v2/manifests"
DEV, VALID, FIT_SEASONS = [2020], [2021], [2018, 2019, 2020, 2021]
START = {"pressure": 2018, "completion": 2016}   # pressure labels change definition between 2017 and 2018 (see DATA_AUDIT)


def population(kind: str):
    d = pl.read_parquet(FEAT / "dropbacks.parquet").filter(pl.col("has_part"), pl.col("season") <= 2021)
    pos = {(s, g): p for s, g, p in pl.read_parquet(FEAT / "position_lookup.parquet").iter_rows()}
    if kind == "pressure":
        d = d.filter(pl.col("season") >= START[kind])
        y = (d["was_pressure"].fill_null(False) | d["sack"]).to_numpy().astype(float)
    else:
        d = d.filter(pl.col("attempt"), ~pl.col("sack"), ~pl.col("scramble"))
        y = d["complete"].to_numpy().astype(float)
    return d, pos, y


def lam_for(kind, player, team):
    g = ["OL", "DL", "LB", "QB"] if kind == "pressure" else ["R", "DB", "LB", "QB"]
    return {**{k: player for k in g}, "OT": team, "DT": team}


def _ll(p, v):
    yy = p["y"].to_numpy()
    return float(V.logloss(yy, p[v].to_numpy()).mean())


def dev():
    """Each variant is fit only over the parameters it uses: ctx none, team (half-life, team ridge), player (half-life, player ridge).
    The combined 'both' variant is not tuned on dev; it uses the chosen pair and is reported at validation."""
    out = {}
    for kind in ("pressure", "completion"):
        d, pos, y = population(kind)
        designs = V.make_designs(d, pos, kind)
        rows = []
        for hl in (365.0, 730.0, 1460.0):
            def run(v, lp, lt):
                t = time.time()
                p, _ = V.walk_forward(d, pos, kind, y, lam_for(kind, lp, lt), hl, DEV, START[kind], variants=(v,), record_abilities=None,
                                      designs={v: designs[v]})
                r = {"half_life": hl, "variant": v, "lam_player": lp if v == "player" else None, "lam_team": lt if v == "team" else None,
                     "n": p.height, "logloss": _ll(p, v)}
                rows.append(r)
                print(kind, r, round(time.time() - t), "s", flush=True)
            run("ctx", 0, 0)
            for lt in (30.0, 100.0, 300.0, 1000.0):
                run("team", 0, lt)
            for lp in (30.0, 100.0, 300.0, 1000.0):
                run("player", lp, 0)
        out[kind] = rows
    MAN.mkdir(parents=True, exist_ok=True)
    (MAN / "dev_grid_2020.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    {"dev": dev}[sys.argv[1]]()
