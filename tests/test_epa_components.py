import polars as pl

from engine.features import epa_components as E


def _pbp(rows):
    base = {"season_type": "REG", "week": 1, "interception": 0, "fumble_lost": 0, "penalty": 0, "penalty_team": None,
            "special_teams_play": 0, "pass": 0, "rush": 0, "play_type": "pass"}
    return pl.DataFrame([{**base, **r} for r in rows])


def test_components_are_split_and_signed():
    p = _pbp([
        {"game_id": "g", "posteam": "AAA", "defteam": "BBB", "epa": 1.0, "pass": 1},
        {"game_id": "g", "posteam": "AAA", "defteam": "BBB", "epa": -0.5, "rush": 1},
        {"game_id": "g", "posteam": "BBB", "defteam": "AAA", "epa": -3.0, "pass": 1, "interception": 1},
        {"game_id": "g", "posteam": "BBB", "defteam": "AAA", "epa": 2.0, "pass": 1, "penalty": 1, "penalty_team": "AAA"},
        {"game_id": "g", "posteam": "AAA", "defteam": "BBB", "epa": 0.4, "special_teams_play": 1},
        {"game_id": "h", "posteam": "AAA", "defteam": "CCC", "epa": 9.0, "pass": 1, "week": 2},   # after the cut
    ])
    t = E.compute(p, before_week=2)["teams"]
    assert t["AAA"]["pass_off"][0] == 1.0 and t["AAA"]["rush_off"][0] == -0.5
    assert t["AAA"]["turnovers"][0] == 3.0 and t["BBB"]["turnovers"][0] == -3.0      # takeaway / giveaway
    assert t["AAA"]["penalties"][0] == -2.0                                            # AAA penalized on BBB's play
    assert t["AAA"]["special_teams"][0] == 0.4 and t["BBB"]["special_teams"][0] == -0.4
    assert t["AAA"]["pass_off"][1] == 1 and t["AAA"]["games"] == 1                     # rank 1, week-2 game excluded
