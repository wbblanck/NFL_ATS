"""Receiver versus coverage, as a completion model (gamesim v2, sprint 1).

logit P(complete) = intercept + context (air-yards bucket, pressure, down, distance, shotgun) + targeted receiver + quarterback
+ sum of effects of the defensive backs and linebackers on the field. Participation says who was on the field, not who covered the
target, so defender effects are shared across the secondary. There is no separation, route or assignment layer: no public data
has per-play separation, and `route` lists receivers' routes without the defender. Sign: positive on a receiver or QB = more
completions; positive on a defender = more completions allowed.
"""
from __future__ import annotations

import numpy as np

from .protection import AbilityTable, context_logit


def completion_logit(table: AbilityTable, effects: dict, play: dict, target: str | None, qb: str, defenders: dict, latent=0.0):
    c = {"context": context_logit(table, "completion", play)}
    c["receiver"] = effects.get("R:" + target, 0.0) if target else 0.0
    c["QB"] = effects.get("QB:" + qb, 0.0)
    c["coverage"] = sum(effects.get("DB:" + u, 0.0) for u in defenders["DB"]) + sum(effects.get("LB:" + u, 0.0) for u in defenders["LB"])
    c["latent"] = latent
    return sum(c.values()), c


def simulate_catch(rng, table, effects, play, target, qb, defenders, latent=0.0) -> dict:
    z, c = completion_logit(table, effects, play, target, qb, defenders, latent)
    p = 1 / (1 + np.exp(-z))
    return {"p_complete": float(p), "complete": bool(rng.random() < p), "logit_parts": c}
