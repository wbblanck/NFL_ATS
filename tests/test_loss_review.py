import polars as pl

from engine.picks import loss_review as LR


def _pbp():
    # g1: AAA (home, -3.5 on the pool line) leads 10-0, BBB scores late: AAA covering by 6.5 with 5:00 left,
    # final 10-7 home by 3 -> AAA misses by 0.5. A BBB kickoff-return fumble counts as BBB's turnover.
    rows = [  # game_id, play_id, qtr, qsr, home, away, int, fum_lost, fumbled_team, posteam
        ("g1", 1, 1, 900, 0, 0, 0, 0, None, "AAA"),
        ("g1", 2, 1, 600, 7, 0, 0, 0, None, "AAA"),
        ("g1", 3, 2, 300, 7, 0, 0, 1, "BBB", "BBB"),
        ("g1", 4, 3, 100, 10, 0, 1, 0, None, "AAA"),
        ("g1", 5, 4, 30, 10, 7, 0, 0, None, "BBB"),
        ("g1", 6, 4, 0, 10, 7, 0, 0, None, "AAA"),
        # g2: a win for the pick: CCC (away, +2.5) down 0-7 with 5:00 left, wins 10-7 -> a late swing our way
        ("g2", 1, 1, 900, 0, 0, 0, 0, None, "DDD"),
        ("g2", 2, 2, 400, 7, 0, 0, 0, None, "DDD"),
        ("g2", 3, 4, 200, 7, 3, 0, 0, None, "CCC"),
        ("g2", 4, 4, 20, 7, 10, 0, 0, None, "CCC"),
    ]
    cols = ["game_id", "play_id", "qtr", "quarter_seconds_remaining", "total_home_score", "total_away_score",
            "interception", "fumble_lost", "fumbled_1_team", "posteam"]
    return pl.DataFrame(rows, schema=cols, orient="row")


def test_paths_scores_turnovers_and_elapsed():
    p = LR.game_paths(_pbp())["g1"]
    assert p["pts"] == [[0.0, 0, 0], [5.0, 7, 0], [43.33, 10, 0], [59.5, 10, 7]]
    assert p["to"] == [[25.0, "BBB"], [43.33, "AAA"]] and p["end"] == 60.0
    assert LR._elapsed(5, 300) == 65.0


def test_loss_tags_and_late_swings_both_ways():
    sched = pl.DataFrame({"game_id": ["g1", "g2"], "home_team": ["AAA", "DDD"], "away_team": ["BBB", "CCC"],
                          "home_score": [10, 7], "away_score": [7, 10]})
    preds = [{"game_id": "g1", "pick": "home", "drift": "-1.0", "p_home_cover": "0.55", "p_away_cover": "0.45"},
             {"game_id": "g2", "pick": "away", "drift": "0", "p_home_cover": "0.48", "p_away_cover": "0.52"}]
    graded = [{"game_id": "g1", "week": 4, "pick": "AAA", "league_line": -3.5, "result": "L", "hybrid": "BBB W",
               "shadow_result": "L"},
              {"game_id": "g2", "week": 4, "pick": "CCC", "league_line": -2.5, "result": "W"}]
    out = LR.build(graded, preds, sched, LR.game_paths(_pbp()))
    [x] = out["losses"]
    assert x["cov5"] == 6.5 and x["fin"] == -0.5 and x["line"] == -3.5 and x["to"] == [1, 1]
    assert x["tags"] == ["late", "hook"] and x["p"] == 0.55 and x["others"]["hybrid"] == "W"
    assert x["flow"][-1] == [60.0, -0.5, 7, 10]
    assert out["summary"]["late"] == 1 and out["summary"]["won_late"] == 1 and out["summary"]["fg"] == 1


def test_missing_play_by_play_still_lists_the_loss():
    sched = pl.DataFrame({"game_id": ["g1"], "home_team": ["AAA"], "away_team": ["BBB"], "home_score": [10],
                          "away_score": [30]})
    out = LR.build([{"game_id": "g1", "week": 5, "pick": "AAA", "league_line": -3.5, "result": "L"}],
                   [{"game_id": "g1", "pick": "home", "drift": ""}], sched, {})
    [x] = out["losses"]
    assert x["flow"] is None and x["cov5"] is None and x["tags"] == ["far"]
