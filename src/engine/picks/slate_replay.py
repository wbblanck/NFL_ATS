"""'The week in 20 seconds': every official pick of the latest fully played week with its cover margin through the
game (play-by-play, same numbers as the loss review), so the dashboard can replay the whole slate on one clock.
Descriptive only. Real time is approximated as kickoff + 3 hours per game, because play-by-play gives game minutes
and not the stoppages; the page says so."""
from __future__ import annotations

import polars as pl

from engine.data import nflverse
from engine.picks.loss_review import _cov


def latest_complete_week(sched: pl.DataFrame, season: int) -> int | None:
    wk = sched.filter(pl.col("season") == season, pl.col("game_type") == "REG")
    done = [w for w in sorted(set(wk["week"].to_list()))
            if wk.filter(pl.col("week") == w)["home_score"].null_count() == 0]
    return int(done[-1]) if done else None


def build(graded: list[dict], sched: pl.DataFrame, paths: dict[str, dict], season: int) -> dict:
    if "kickoff_utc" not in sched.columns:
        sched = nflverse.with_kickoff(sched)
    week = latest_complete_week(sched, season)
    if week is None:
        return {}
    sc = {r["game_id"]: r for r in sched.filter(pl.col("season") == season, pl.col("week") == week).iter_rows(named=True)}
    games = []
    for r in graded:
        g = sc.get(r["game_id"])
        path = paths.get(r["game_id"])
        if g is None or path is None or int(r["season"]) != season or int(r["week"]) != week:
            continue
        ph = r["pick"] == g["home_team"]
        ln = float(r["league_line"])
        flow = [[t, _cov(h - a, ph, ln)] for t, h, a in path["pts"]]
        flow.append([path["end"], flow[-1][1]])
        games.append({"id": r["game_id"], "away": g["away_team"], "home": g["home_team"], "pick": r["pick"],
                      "line": ln if ph else -ln, "ko": g["kickoff_utc"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "flow": flow, "fin": flow[-1][1], "res": r["result"]})
    games.sort(key=lambda x: (x["ko"], x["id"]))
    return {"week": week, "n_games": len(sc), "games": games} if games else {}
