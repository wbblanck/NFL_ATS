"""Independent random streams (spec 9.2): one generator per mechanism, all spawned from a single seed, so a change in how many
numbers one module draws never shifts another module's draws."""
from __future__ import annotations

import numpy as np

STREAMS = ("ability", "strategy", "matchup", "outcome", "latent")


def streams(seed: int, play: int = 0) -> dict:
    """Streams for one play. Keyed by (seed, play index), so how many numbers one play draws never shifts the next play's draws
    (a single running generator per mechanism would couple them through conditional consumption, e.g. target choice only on throws)."""
    ss = np.random.SeedSequence([seed, play])
    return {name: np.random.default_rng(child) for name, child in zip(STREAMS, ss.spawn(len(STREAMS)))}
