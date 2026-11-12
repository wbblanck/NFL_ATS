"""Derive each game's Tuesday line from ESPN's timestamped spread history (2018-2022).

Input: data/raw/espn_history/{games,spread_movements}_2018_2022.csv
Output: data/raw/espn_history/tuesday_lines_2018_2022.csv

For each game, "Tuesday" is the last Tuesday on or before the kickoff date (US Eastern).
The line in effect at a time T is the last movement at or before T. We report it at
08:00, 12:00 and 23:59 ET, plus the first and last line in the history.
Home spread sign: negative = home favored. Research only.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "raw" / "espn_history"
ET = "America/New_York"


def main() -> None:
    g = pd.read_csv(D / "games_2018_2022.csv")
    m = pd.read_csv(D / "spread_movements_2018_2022.csv")
    m["t"] = pd.to_datetime(m["line_date_utc"], utc=True)
    m = m.dropna(subset=["home_spread"]).sort_values(["game_id", "t"])
    g["kick"] = pd.to_datetime(g["gameday"] + " " + g["gametime"]).dt.tz_localize(ET)
    back = (g["kick"].dt.dayofweek - 1) % 7
    g["tue"] = g["kick"].dt.normalize() - pd.to_timedelta(back, unit="D")
    rows = []
    for gid, mv in m.groupby("game_id"):
        gr = g[g.game_id == gid].iloc[0]
        rec = {"game_id": gid, "season": gr.season, "week": gr.week,
               "kickoff_et": gr.kick.isoformat(), "n_moves": len(mv),
               "first_line": mv.home_spread.iloc[0], "first_at": mv.t.iloc[0].isoformat(),
               "last_line": mv[mv.t < gr.kick].home_spread.iloc[-1] if (mv.t < gr.kick).any() else None,
               "nflverse_close": -gr.spread_line}
        for label, hh, mm in (("tue_0800", 8, 0), ("tue_1200", 12, 0), ("tue_2359", 23, 59)):
            cut = gr.tue + pd.Timedelta(hours=hh, minutes=mm)
            before = mv[mv.t <= cut]
            rec[label] = before.home_spread.iloc[-1] if len(before) else None
            rec[label + "_age_h"] = round((cut - before.t.iloc[-1]).total_seconds() / 3600, 1) if len(before) else None
        rows.append(rec)
    out = pd.DataFrame(rows).sort_values(["season", "week", "game_id"])
    out.to_csv(D / "tuesday_lines_2018_2022.csv", index=False)
    print(out.groupby("season").agg(games=("game_id", "size"),
                                    tue_noon=("tue_1200", "count")).to_string())


if __name__ == "__main__":
    main()
