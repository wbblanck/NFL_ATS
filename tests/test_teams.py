import pytest

from engine.teams import CANONICAL, CURRENT, FULL_NAMES, UnknownTeam, to_canonical

# Codes observed in nflverse schedules 1999-2026 (nflreadpy.load_schedules, 2026-09-24).
NFLVERSE_SCHEDULE_CODES = ['ARI', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE', 'DAL', 'DEN', 'DET', 'GB',
                           'HOU', 'IND', 'JAX', 'KC', 'LA', 'LAC', 'LV', 'MIA', 'MIN', 'NE', 'NO', 'NYG', 'NYJ',
                           'OAK', 'PHI', 'PIT', 'SD', 'SEA', 'SF', 'STL', 'TB', 'TEN', 'WAS']


def test_canonical_matches_nflverse():
    assert CANONICAL == frozenset(NFLVERSE_SCHEDULE_CODES)
    assert len(CURRENT) == 32
    for c in NFLVERSE_SCHEDULE_CODES:
        assert to_canonical(c) == c


def test_observed_aliases():
    assert to_canonical("JAC") == "JAX"   # CBS data-game-abbrev
    assert to_canonical("LAR") == "LA"    # nflreadpy load_teams
    assert to_canonical(" gb ") == "GB"


def test_full_names_cover_all_current_teams():
    assert {v for v in FULL_NAMES.values()} >= set(CURRENT)
    assert to_canonical("Green Bay Packers") == "GB"
    assert to_canonical("Los Angeles Rams") == "LA"


@pytest.mark.parametrize("bad", ["XXX", "", "Green Bay", None])
def test_unknown_raises(bad):
    with pytest.raises(UnknownTeam):
        to_canonical(bad)


def test_live_nflverse_codes_if_available():
    """Validates the mapping against the live nflverse schedule when network is available."""
    nfl = pytest.importorskip("nflreadpy")
    try:
        s = nfl.load_schedules()
    except Exception as e:  # offline
        pytest.skip(f"nflverse unavailable: {e}")
    codes = set(s["home_team"].to_list()) | set(s["away_team"].to_list())
    assert codes <= CANONICAL
