"""Score the pre-registered pool-line rule (docs/pool_line_rule_preregistration.md).

Usage: python scripts/research/pool_line_rule.py --weeks 11-18   (confirmation, scored once at the end)
       python scripts/research/pool_line_rule.py --weeks 4-10    (development sample, reproduces 88/100)

Research only. Reads data/lines/market_captures.csv and the checked league lines; writes nothing.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from engine.data import league_lines  # noqa: E402

ET = "America/New_York"
LIGHT, HEAVY = 1.915, 1.905  # decimal price bands around -110 (1.909)


def juice_round(spread: float, price: float) -> float:
    """Whole-number home spread -> the half point the home price leans to; NaN if even."""
    if spread * 2 % 2 != 0:
        return spread
    if price < HEAVY:
        return spread - 0.5
    if price > LIGHT:
        return spread + 0.5
    return math.nan


def snapshots(season: int, weeks: range) -> pd.DataFrame:
    m = pd.read_csv(ROOT / "data" / "lines" / "market_captures.csv")
    m = m[(m.status == "ok") & m.home_spread.notna() & m.home_price_decimal.notna()
          & (m.season == season) & m.week.isin(list(weeks))].copy()
    m["t"] = pd.to_datetime(m.captured_at, utc=True).dt.tz_convert(ET)
    ko = pd.to_datetime(m.kickoff_utc, utc=True).dt.tz_convert(ET)
    tue = ko.dt.normalize() - pd.to_timedelta((ko.dt.dayofweek - 1) % 7, unit="D")
    m["start"], m["end"] = tue + pd.Timedelta(hours=8), tue + pd.Timedelta(hours=16)
    m = m[(m.t >= m.start) & (m.t < m.end) & (m.t < ko)]
    f = m.sort_values("t").groupby(["game_id", "book"]).first().reset_index()
    f["jr"] = [juice_round(s, p) for s, p in zip(f.home_spread, f.home_price_decimal)]
    return f


def wilson_low(k: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return math.nan
    p = k / n
    return (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", default="11-18")
    ap.add_argument("--season", type=int, default=2026)
    a = ap.parse_args()
    lo, hi = (int(x) for x in a.weeks.split("-"))
    weeks = range(lo, hi + 1)
    pool = {g: float(r["spread"]) for g, r in league_lines.load_checked().valid.items()
            if int(r["season"]) == a.season and int(r["week"]) in weeks}
    f = snapshots(a.season, weeks)
    rows = []
    for gid, p in sorted(pool.items()):
        g = f[f.game_id == gid]
        dk = g[g.book == "draftkings"]
        primary = dk.jr.iloc[0] if len(dk) else math.nan
        raw_dk = dk.home_spread.iloc[0] if len(dk) else math.nan
        mode = g.jr.dropna().mode()
        secondary = mode.iloc[0] if len(mode) == 1 else math.nan
        dk_dir = None
        if len(dk) and dk.home_spread.iloc[0] * 2 % 2 == 0 and abs(p - dk.home_spread.iloc[0]) == 0.5 \
                and not math.isnan(primary):
            dk_dir = bool(primary == p)
        rows.append({"game_id": gid, "pool": p, "P1": primary, "P2": secondary, "raw_dk": raw_dk,
                     "dk_dir_ok": dk_dir})
    r = pd.DataFrame(rows)
    n = len(r)
    print(f"Season {a.season} weeks {lo}-{hi}: {n} games with a usable pool line")
    if n == 0:
        return 0
    for col, name in (("P1", "P1 DraftKings, juice-rounded (primary)"),
                      ("P2", "P2 most common juice-rounded line, all books"),
                      ("raw_dk", "Baseline: raw DraftKings line")):
        k = int((r[col] == r.pool).sum())
        none = int(r[col].isna().sum())
        print(f"  {name}: exact {k}/{n} ({k / n:.0%}), no prediction {none}, "
              f"Wilson 95% low {wilson_low(k, n):.0%}")
    d = r.dk_dir_ok.dropna().astype(bool)
    if len(d):
        k = int(d.sum())
        pval = sum(math.comb(len(d), i) for i in range(k, len(d) + 1)) / 2 ** len(d)
        print(f"  Juice direction (DK whole number, pool on adjacent half, price leans): "
              f"{k}/{len(d)} correct, one-sided binomial p = {pval:.4f}")
    k1 = int((r.P1 == r.pool).sum())
    verdict = "CONFIRMED" if n >= 80 and k1 / n >= 0.80 and wilson_low(k1, n) >= 0.70 else "NOT CONFIRMED"
    print(f"Verdict (needs >= 80 games, P1 >= 80% exact, Wilson low >= 70%): {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
