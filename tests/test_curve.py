import datetime as dt

import polars as pl

from engine.picks import curve


def test_cumulative_and_band(monkeypatch):
    k = dt.datetime(2026, 9, 6, 17, tzinfo=dt.timezone.utc)
    sched = pl.DataFrame({"game_id": ["g1", "g2"], "season": [2026, 2026], "week": [1, 1],
                          "kickoff_utc": [k, k + dt.timedelta(hours=1)], "home_team": ["AAA", "CCC"],
                          "away_team": ["BBB", "DDD"], "home_score": [20, 10], "away_score": [10, 17], "result": [10, -7]})
    monkeypatch.setattr(curve.league_lines, "load", lambda: [
        {"game_id": "g1", "spread": "-3.5"}, {"game_id": "g2", "spread": "-1.5"}])
    monkeypatch.setattr(curve.store, "read_rows", lambda p: [])
    monkeypatch.setattr(curve, "_backtest", lambda s: {"g1": {"official": "AAA", "hybrid": "BBB"},
                                                          "g2": {"official": "CCC", "hybrid": "DDD"}})
    out = curve.build(sched, 2026, [])
    # g1: AAA -3.5 won by 10: home covers; g2: CCC -1.5 lost by 7: away covers
    assert out["cum"]["official"] == [1, 0] and out["cum"]["hybrid"] == [-1, 0]
    assert out["cum"]["favorite"] == [1, 0] and out["cum"]["home"] == [1, 0]
    assert [g["kind"] for g in out["games"]] == ["backtest", "backtest"]
    assert out["band"][0] == 1.96 and "Inside the luck band" in out["verdict"]
