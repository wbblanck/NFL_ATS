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
