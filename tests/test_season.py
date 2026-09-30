from engine.picks import season


def test_live_rows_counted_per_model_and_week(monkeypatch):
    monkeypatch.setattr(season, "backtest_rows", lambda s: [
        {"week": 1, "covered": "BUF", "official": "BUF", "keynum": "HOU", "v1": "BUF", "v3": None, "hybrid": "BUF"}])
    graded = [{"season": "2026", "week": "3", "result": "W", "shadow_result": "L", "proj_proj-poisson-v1": "NYJ W",
               "proj_proj-players-v3": "", "hybrid": "DET L"}]
    t = season.build(graded, 2026)
    assert [(w["week"], w["kind"]) for w in t] == [(1, "backtest"), (3, "live")]
    assert t[0]["rec"] == {"official": [1, 0], "keynum": [0, 1], "v3": [0, 0], "v1": [1, 0], "hybrid": [1, 0]}
    assert t[1]["rec"] == {"official": [1, 0], "keynum": [0, 1], "v3": [0, 0], "v1": [1, 0], "hybrid": [0, 1]}
