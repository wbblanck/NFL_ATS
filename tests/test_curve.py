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
    # backtest games never move the official line (owner rule 2026-11-26); tracked models still use them
    assert out["cum"]["official"] == [0, 0] and out["cum"]["hybrid"] == [-1, 0]
    assert out["cum"]["favorite"] == [1, 0] and out["cum"]["home"] == [1, 0]
    assert [g["kind"] for g in out["games"]] == ["backtest", "backtest"]
    assert out["band"][0] == 1.96 and "verdict" not in out and out["live_official_graded"] == 0


def test_live_games_use_each_models_graded_pick(monkeypatch):
    k = dt.datetime(2026, 9, 27, 17, tzinfo=dt.timezone.utc)
    sched = pl.DataFrame({"game_id": ["g1"], "season": [2026], "week": [4], "kickoff_utc": [k], "home_team": ["AAA"],
                          "away_team": ["BBB"], "home_score": [20], "away_score": [10], "result": [10]})
    monkeypatch.setattr(curve.league_lines, "load", lambda: [{"game_id": "g1", "spread": "-3.5"}])
    monkeypatch.setattr(curve.store, "read_rows", lambda p: [{"game_id": "g1", "pick_team": "AAA"}])
    monkeypatch.setattr(curve, "_backtest", lambda s: {})
    graded = [{"game_id": "g1", "hybrid": "BBB L", "shadow_pick": "AAA", "proj_proj-poisson-v1": "AAA W"}]
    out = curve.build(sched, 2026, graded)                           # home covered; v3 had no graded pick
    assert {k: v[0] for k, v in out["cum"].items()} == {"official": 1, "hybrid": -1, "v1": 1, "v3": 0, "keynum": 1,
                                                        "favorite": 1, "home": 1}
    assert "v3" not in out["games"][0]["d"] and out["games"][0]["kind"] == "live"


def test_week6_fill_marks_models_without_a_live_pick(monkeypatch):
    k = dt.datetime(2026, 10, 18, 17, tzinfo=dt.timezone.utc)
    sched = pl.DataFrame({"game_id": ["g1"], "season": [2026], "week": [6], "kickoff_utc": [k], "home_team": ["AAA"],
                          "away_team": ["BBB"], "home_score": [20], "away_score": [10], "result": [10]})
    monkeypatch.setattr(curve.league_lines, "load", lambda: [{"game_id": "g1", "spread": "-3.5"}])
    monkeypatch.setattr(curve.store, "read_rows", lambda p: [{"game_id": "g1", "pick_team": "BBB"}])
    monkeypatch.setattr(curve, "_backtest", lambda s: {})
    monkeypatch.setattr(curve, "fill", lambda s: {"g1": {"official": "AAA", "hybrid": "AAA", "v1": "AAA", "v3": "BBB",
                                                         "keynum": "AAA"}})
    graded = [{"game_id": "g1", "hybrid": "BBB L", "shadow_pick": "", "proj_proj-poisson-v1": ""}]
    out = curve.build(sched, 2026, graded)                           # home covered; the live picks keep their result
    g = out["games"][0]
    assert g["kind"] == "live" and sorted(g["bt"]) == ["keynum", "v1", "v3"]
    assert g["d"]["official"] == -1 and g["d"]["hybrid"] == -1
    assert g["d"]["keynum"] == 1 and g["d"]["v1"] == 1 and g["d"]["v3"] == -1


def test_verdict_counts_live_official_picks_only(monkeypatch):
    """A backtest game, a missed game and a week 6 fill must not enter the official series or the verdict."""
    k = dt.datetime(2026, 9, 6, 17, tzinfo=dt.timezone.utc)
    ids = ["bt1", "live1", "live2", "missed1"]
    sched = pl.DataFrame({"game_id": ids, "season": [2026] * 4, "week": [1, 4, 4, 5],
                          "kickoff_utc": [k + dt.timedelta(days=i * 7) for i in range(4)],
                          "home_team": ["AAA"] * 4, "away_team": ["BBB"] * 4,
                          "home_score": [20] * 4, "away_score": [10] * 4, "result": [10] * 4})
    monkeypatch.setattr(curve.league_lines, "load", lambda: [{"game_id": g, "spread": "-3.5"} for g in ids])
    monkeypatch.setattr(curve.store, "read_rows", lambda p: [{"game_id": "live1", "pick_team": "AAA"},
                                                              {"game_id": "live2", "pick_team": "BBB"}])
    monkeypatch.setattr(curve, "_backtest", lambda s: {"bt1": {"official": "AAA", "hybrid": "AAA"}})
    monkeypatch.setattr(curve, "fill", lambda s: {"missed1": {"official": "AAA", "hybrid": "AAA"}})
    graded = [{"game_id": "live1", "hybrid": "AAA W"}, {"game_id": "live2", "hybrid": "AAA W"}]
    out = curve.build(sched, 2026, graded)                           # home covers every game
    assert out["cum"]["official"] == [0, 1, 0, 0]                    # only live1 (W) and live2 (L) move it
    assert out["cum"]["hybrid"] == [1, 2, 3, 4]                      # tracked models may still use backtest/fill picks
    assert out["live_official_graded"] == 2
    assert "1-1 on 2 graded" in out["verdict"] and "+0 net wins" in out["verdict"]
    assert all("official" not in g.get("bt", []) for g in out["games"])
