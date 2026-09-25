import pytest

from engine.picks.grading import (InvalidLeagueLine, Result, Side, favorite, from_nflverse_spread_line,
                                  grade, grade_league, is_half_point, pick_won, to_nflverse_spread_line,
                                  validate_league_line)


@pytest.mark.parametrize("s,ok", [(-3.5, True), (3.5, True), (0.5, True), (-10.5, True),
                                  (-3.0, False), (0.0, False), (7.0, False), (-2.25, False)])
def test_half_point(s, ok):
    assert is_half_point(s) is ok
    if ok:
        assert validate_league_line(s) == s
    else:
        with pytest.raises(InvalidLeagueLine):
            validate_league_line(s)


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), "3.5"])
def test_validate_rejects_non_numeric(bad):
    with pytest.raises(InvalidLeagueLine):
        validate_league_line(bad)


def test_home_favored_canonical():
    # Home -3.5: home must win by 4+.
    assert grade(24, 20, -3.5) is Result.HOME_COVER
    assert grade(23, 20, -3.5) is Result.AWAY_COVER
    assert grade(20, 24, -3.5) is Result.AWAY_COVER


def test_away_favored_canonical():
    # S = +6.5 -> away favored by 6.5; home covers if it loses by <= 6.
    assert grade(20, 26, 6.5) is Result.HOME_COVER
    assert grade(20, 27, 6.5) is Result.AWAY_COVER


def test_nflverse_sign_convention_roundtrip():
    # nflverse spread_line +3.5 = home favored by 3.5 -> canonical -3.5
    assert from_nflverse_spread_line(3.5) == -3.5
    assert to_nflverse_spread_line(-3.5) == 3.5
    s = from_nflverse_spread_line(3.5)
    # nflverse doc: result (home-away) > spread_line  <=> home covers
    for home, away in [(24, 20), (23, 20), (10, 30)]:
        nflverse_home_cover = (home - away) > 3.5
        assert (grade(home, away, s) is Result.HOME_COVER) == nflverse_home_cover


def test_push_only_possible_on_whole_numbers():
    assert grade(23, 20, -3.0) is Result.PUSH
    with pytest.raises(InvalidLeagueLine):
        grade_league(23, 20, -3.0)
    for margin in range(-40, 41):
        assert grade_league(margin if margin > 0 else 0, -margin if margin < 0 else 0, -2.5) is not Result.PUSH


def test_favorite_and_pick_won():
    assert favorite(-1.5) is Side.HOME and favorite(1.5) is Side.AWAY and favorite(0.0) is None
    assert pick_won(Side.HOME, Result.HOME_COVER) is True
    assert pick_won(Side.AWAY, Result.HOME_COVER) is False
    assert pick_won(Side.HOME, Result.PUSH) is None
