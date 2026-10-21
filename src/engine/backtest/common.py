"""Small helpers shared by the backtest reports: ATS records and Markdown tables."""
from __future__ import annotations

import math

import numpy as np
import polars as pl


def ats(p: np.ndarray, y: np.ndarray) -> dict:
    """Record of the pick 'home covers when p > 0.5' against outcomes y (1 = home covered)."""
    w = int(((p > 0.5) == (y == 1)).sum()); n = len(y); r = w / n
    return {"W": w, "L": n - w, "N": n, "win_rate": r, "se": math.sqrt(r * (1 - r) / n)}


def record(w, n) -> dict:
    """Record from w wins in n graded games; se is None when n is 0."""
    r = w / n if n else float("nan")
    return {"W": int(w), "L": int(n - w), "N": int(n), "win_rate": r, "se": math.sqrt(r * (1 - r) / n) if n else None}


def md_table(df: pl.DataFrame) -> str:
    """Markdown table; floats to 4 places."""
    cols = df.columns
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in df.to_dicts():
        out.append("| " + " | ".join(f"{v:.4f}" if isinstance(v, float) else str(v) for v in r.values()) + " |")
    return "\n".join(out)
