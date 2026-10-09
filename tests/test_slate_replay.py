import datetime as dt

import polars as pl

from engine.picks import slate_replay as SR


def _sched(week4_done=True):
    k = lambda d, h: dt.datetime(2026, 10, d, h, tzinfo=dt.timezone.utc)
    return pl.DataFrame({
        "season": [2026] * 3, "game_type": ["REG"] * 3, "week": [4, 4, 5],
        "game_id": ["a", "b", "c"], "home_team": ["AAA", "CCC", "EEE"], "away_team": ["BBB", "DDD", "FFF"],
        "kickoff_utc": [k(4, 17), k(4, 20), k(11, 17)],
        "home_score": [20, 10 if week4_done else None, None], "away_score": [10, 17 if week4_done else None, None]})


def test_latest_complete_week_ignores_weeks_still_in_progress():
    assert SR.latest_complete_week(_sched(), 2026) == 4
    assert SR.latest_complete_week(_sched(week4_done=False), 2026) is None


def test_build_uses_the_pick_side_cover_margin_and_orders_by_kickoff():
    paths = {"a": {"pts": [[0.0, 0, 0], [20.0, 7, 0], [50.0, 20, 10]], "end": 60.0, "to": []},
             "b": {"pts": [[0.0, 0, 0], [30.0, 0, 7], [55.0, 10, 17]], "end": 60.0, "to": []}}
    graded = [{"game_id": "b", "season": 2026, "week": 4, "pick": "DDD", "league_line": -1.5, "result": "W"},
              {"game_id": "a", "season": 2026, "week": 4, "pick": "AAA", "league_line": -3.5, "result": "W"}]
    out = SR.build(graded, _sched(), paths, 2026)
    assert out["week"] == 4 and [g["id"] for g in out["games"]] == ["a", "b"]
    a, b = out["games"]
    assert a["line"] == -3.5 and a["fin"] == 6.5 and a["flow"][-1] == [60.0, 6.5]      # home pick covers by 6.5
    assert b["pick"] == "DDD" and b["line"] == 1.5 and b["fin"] == 8.5                 # away pick at +1.5 wins by 7: covers by 8.5
