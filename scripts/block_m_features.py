"""Block M (market microstructure) features for the disagreement-model plan (docs/disagreement_model_preregistration.md).

Derived read-only from data/lines/market_captures.csv, which the capture jobs already append to every few hours with every
book's spread. Per game, using only captures before the lock (kickoff - 15 min), which includes the capture each pick used:
  pin_open      first Pinnacle spread captured (home spread; a proxy for the open: the earliest capture we hold)
  pin_last      last Pinnacle spread before the pick time
  pin_move      pin_last - pin_open (negative = moved toward home)
  pin_span_h    hours between those two captures (a move over a short span is not an open-to-lock move)
  gap_last      Pinnacle minus the median of the other books at the last capture where Pinnacle is present
  n_books_last  books in that capture
NOT captured, so block M cannot include it yet: the total's open-to-lock move (totals are fetched only at pick time).

    python scripts/block_m_features.py [--out /tmp/block_m.csv]
"""
import argparse
import sys

import pandas as pd

sys.path.insert(0, "src")


def build(caps: pd.DataFrame) -> pd.DataFrame:
    caps = caps[caps.status == "ok"].copy()
    caps["t"] = pd.to_datetime(caps.captured_at, utc=True, format="ISO8601")
    caps["ko"] = pd.to_datetime(caps.kickoff_utc, utc=True, format="ISO8601")
    caps = caps[caps.t <= caps.ko - pd.Timedelta(minutes=15)]   # before the lock; includes the capture the pick used
    rows = []
    for gid, g in caps.groupby("game_id"):
        pin = g[g.book == "pinnacle"].sort_values("t")
        if pin.empty:
            continue
        first, last = pin.iloc[0], pin.iloc[-1]
        cap = g[g.capture_id == last.capture_id]
        others = cap[cap.book != "pinnacle"].home_spread
        rows.append({"game_id": gid, "week": int(last.week), "pin_open": first.home_spread, "pin_last": last.home_spread,
                     "pin_move": last.home_spread - first.home_spread,
                     "pin_span_h": (last.t - first.t).total_seconds() / 3600,
                     "gap_last": last.home_spread - others.median() if len(others) else float("nan"),
                     "n_books_last": len(cap), "n_pin_captures": len(pin)})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    a = ap.parse_args()
    caps = pd.read_csv("data/lines/market_captures.csv")
    f = build(caps)
    games = caps.game_id.nunique()
    print(f"games with any capture: {games}; with a Pinnacle capture before the lock: {len(f)}")
    if len(f):
        print(f"Pinnacle span at least 24h: {(f.pin_span_h >= 24).sum()}; at least 2 Pinnacle captures: {(f.n_pin_captures >= 2).sum()}; "
              f"nonzero move: {(f.pin_move != 0).sum()}; median books at last capture: {f.n_books_last.median():.0f}")
        print(f.groupby("week").agg(games=("game_id", "size"), span_ge_24h=("pin_span_h", lambda s: int((s >= 24).sum())),
                                    mean_abs_move=("pin_move", lambda s: s.abs().mean())).round(2).to_string())
    if a.out:
        f.to_csv(a.out, index=False)
