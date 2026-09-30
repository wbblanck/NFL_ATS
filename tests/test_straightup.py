from engine.picks import straightup as SU


def test_table_counts_each_picker_and_expected_wins():
    rs = [{"game_id": "a", "week": 1, "kind": "backtest", "winner": "BUF", "p_market_pick": 0.6, "market": "BUF", "v1": "HOU", "v3": None},
          {"game_id": "b", "week": 1, "kind": "backtest", "winner": "NE", "p_market_pick": 0.7, "market": "SEA", "v1": "NE", "v3": "NE"},
          {"game_id": "c", "week": 3, "kind": "live", "winner": "DEN", "p_market_pick": 0.55, "market": "LA", "v1": "DEN", "v3": "LA"},
          {"game_id": "d", "week": 3, "kind": "backtest", "winner": "ATL", "p_market_pick": 0.64, "market": "GB", "v1": "ATL", "v3": "ATL"}]
    t = SU.table(rs)
    assert [(w["week"], w["kind"]) for w in t] == [(1, "backtest"), (3, "mixed")]
    assert t[0]["rec"] == {"market": [1, 1], "v3": [1, 0], "v1": [1, 1]}
    assert abs(t[0]["expected"] - 1.3) < 1e-9
    assert t[1]["rec"] == {"market": [0, 2], "v3": [1, 1], "v1": [2, 0]}
