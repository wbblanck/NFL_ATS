from engine.picks import season


def test_live_rows_counted_per_model_and_week(monkeypatch):
    monkeypatch.setattr(season, "backtest_rows", lambda s: [
        {"week": 1, "covered": "BUF", "official": "BUF", "keynum": "HOU", "v1": "BUF", "v3": None, "hybrid": "BUF"}])
    monkeypatch.setattr(season, "fill_rows", lambda s: {})
    graded = [{"season": "2026", "week": "3", "result": "W", "shadow_result": "L", "proj_proj-poisson-v1": "NYJ W",
               "proj_proj-players-v3": "", "hybrid": "DET L"}]
    t = season.build(graded, 2026)
    assert [(w["week"], w["kind"]) for w in t] == [(1, "backtest"), (3, "live")]
    assert t[0]["rec"] == {"official": [1, 0], "keynum": [0, 1], "v3": [0, 0], "v1": [1, 0], "hybrid": [1, 0]}
    assert t[1]["rec"] == {"official": [1, 0], "keynum": [0, 1], "v3": [0, 0], "v1": [1, 0], "hybrid": [0, 1]}


def test_week6_fill_only_for_models_without_a_live_pick(monkeypatch):
    monkeypatch.setattr(season, "backtest_rows", lambda s: [])
    monkeypatch.setattr(season, "fill_rows", lambda s: {
        "g1": {"game_id": "g1", "week": 6, "covered": "NO", "official": "NO", "hybrid": "NO", "v1": "NYG", "v3": "NYG",
               "keynum": "NO"},
        "g2": {"game_id": "g2", "week": 6, "covered": "ARI", "official": "ARI", "hybrid": "ARI", "v1": "ARI", "v3": "LA",
               "keynum": "ARI"}})
    # g1 was picked live (official and hybrid graded, no market so no key-number, v1 or v3); g2 had no pick row
    graded = [{"game_id": "g1", "season": "2026", "week": "6", "result": "W", "shadow_result": "",
               "proj_proj-poisson-v1": "", "proj_proj-players-v3": "", "hybrid": "NO W"}]
    t = season.build(graded, 2026)
    assert [(w["week"], w["kind"]) for w in t] == [(6, "backtest"), (6, "fill"), (6, "live")]
    assert t[0]["rec"] == {"official": [1, 0], "keynum": [1, 0], "v3": [0, 1], "v1": [1, 0], "hybrid": [1, 0]}
    assert t[1]["rec"] == {"official": [0, 0], "keynum": [1, 0], "v3": [0, 1], "v1": [0, 1], "hybrid": [0, 0]}
    assert t[2]["rec"] == {"official": [1, 0], "keynum": [0, 0], "v3": [0, 0], "v1": [0, 0], "hybrid": [1, 0]}
