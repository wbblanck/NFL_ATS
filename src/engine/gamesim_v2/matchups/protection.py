"""Pass protection versus pass rush (gamesim v2, sprint 1).

The pressure model is the one trained in `players.abilities`: logit P(pressure) = intercept + context + sum of on-field effects of
the five linemen, the pass-rushing DL and LB on the field, and the quarterback. Participation gives who was on the field, not who
blocked whom, so the effects are shared across the unit; there is no blocker-versus-rusher pairing and no stunt or slide logic yet.
Sign: positive effect on a lineman = more pressure allowed (worse protection); positive on a rusher = more pressure.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from ..players import abilities as A


@dataclass
class AbilityTable:
    """Model coefficients as of one (season, week): intercept, context terms, and per-player effect with standard error."""
    intercept: float
    ctx: dict
    eff: dict   # key "OL:uid" -> (beta, se)

    @classmethod
    def from_long(cls, df: pl.DataFrame):
        """df: rows (key, beta, se) for one (season, week), as written by walk_forward."""
        ctx, eff, b0 = {}, {}, 0.0
        for k, b, se in zip(df["key"], df["beta"], df["se"]):
            if k == "intercept":
                b0 = b
            elif ":" in k:
                eff[k] = (b, se)
            else:
                ctx[k] = b
        return cls(b0, ctx, eff)

    def draw(self, rng: np.random.Generator) -> dict:
        """One realization of every player's effect, drawn from N(beta, se^2): propagates ability uncertainty."""
        keys = list(self.eff)
        b = np.array([self.eff[k][0] for k in keys])
        se = np.array([self.eff[k][1] for k in keys])
        return dict(zip(keys, b + se * rng.standard_normal(len(keys))))


def context_logit(table: AbilityTable, kind: str, play: dict) -> float:
    cols, names = (A.pressure_context if kind == "pressure" else A.completion_context)(pl.DataFrame(play))
    return table.intercept + float(sum(table.ctx.get(n, 0.0) * c for n, c in zip(names, cols[0])))


def pressure_logit(table: AbilityTable, effects: dict, play: dict, lineup: dict, latent: float = 0.0) -> tuple[float, dict]:
    """lineup: {'OL': [uid..], 'DL': [...], 'LB': [...], 'QB': uid}. Returns (logit, contribution by unit)."""
    c = {"context": context_logit(table, "pressure", play)}
    c["OL"] = sum(effects.get("OL:" + u, 0.0) for u in lineup["OL"])
    c["rush"] = sum(effects.get("DL:" + u, 0.0) for u in lineup["DL"]) + sum(effects.get("LB:" + u, 0.0) for u in lineup["LB"])
    c["QB"] = effects.get("QB:" + lineup["QB"], 0.0)
    c["latent"] = latent
    return sum(c.values()), c


def simulate_protection(rng, table, effects, play, lineup, latent=0.0) -> dict:
    z, c = pressure_logit(table, effects, play, lineup, latent)
    p = 1 / (1 + np.exp(-z))
    return {"p_pressure": float(p), "pressure": bool(rng.random() < p), "logit_parts": c}
