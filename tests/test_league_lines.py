import shutil

import pytest

from engine.data import league_lines
from engine.picks.grading import InvalidLeagueLine
from tests.conftest import REPO


def test_recorded_league_lines_are_valid(tmp_root):
    (tmp_root / "data" / "lines").mkdir(parents=True)
    shutil.copy(REPO / "data" / "lines" / "league_lines.csv", tmp_root / "data" / "lines")
    rows = league_lines.load()
    assert {r["game_id"] for r in rows} >= {"2026_03_ATL_GB", "2026_03_LAC_BUF"}


def test_whole_number_league_line_rejected(tmp_root):
    p = tmp_root / "data" / "lines" / "league_lines.csv"
    p.parent.mkdir(parents=True)
    p.write_text(",".join(league_lines.FIELDS) + "\n2026_03_NE_JAX,2026,3,JAX,NE,-3.0,JAX,test,x\n")
    with pytest.raises(InvalidLeagueLine):
        league_lines.load()


def test_check_against_schedule_and_missing(week3_schedule):
    rows = [{"game_id": "2026_03_ATL_GB", "home_team": "GB", "away_team": "ATL"},
            {"game_id": "2026_03_KC_MIA", "home_team": "KC", "away_team": "MIA"},
            {"game_id": "2026_03_XXX_YYY", "home_team": "YYY", "away_team": "XXX"}]
    probs = league_lines.check_against_schedule(rows, week3_schedule)
    assert any("KC_MIA" in p and "home/away" in p for p in probs)
    assert any("XXX_YYY" in p for p in probs)
    miss = league_lines.missing_games(rows, week3_schedule, 2026, 3)
    assert "2026_03_NE_JAX" in miss and "2026_03_ATL_GB" not in miss
