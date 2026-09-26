import numpy as np
import polars as pl
import pytest

from engine.models import projection_v4 as V4


def _dd():
    t = pl.DataFrame({"n_h": [11, 12, 12, 13, 10], "n_a": [11, 12, 11, 13, 10]})
    return V4.DriveDist.fit(t)


def test_drive_model_keeps_expected_scores_and_is_a_distribution():
    dd = _dd()
    pr = V4.project({"td": 2.5, "fg": 1.7}, {"td": 2.0, "fg": 1.5}, 0.92, 0.03, dd)
    h, a = pr.mean_scores()
    extra = 0.92 + 2 * 0.03
    assert h == pytest.approx(6 * 2.5 + extra * 2.5 + 3 * 1.7, abs=0.05)
    assert a == pytest.approx(6 * 2.0 + extra * 2.0 + 3 * 1.5, abs=0.05)
    assert pr.margin_pmf.sum() == pytest.approx(1.0)
    mg = np.arange(-V4.MAXP, V4.MAXP + 1)
    assert pr.margin_pmf @ mg == pytest.approx(h - a, abs=0.05)
    assert pr.p_home_cover(-3.5) + pr.p_home_cover(3.5) > 0      # half-point lines accepted


def test_drive_model_is_narrower_than_independent_poisson():
    from engine.models import projection as P
    dd = _dd()
    v4 = V4.project({"td": 2.4, "fg": 1.7}, {"td": 2.4, "fg": 1.7}, 0.92, 0.03, dd)
    v1 = P.Projection(P.points_pmf(2.4, 1.7, 0.92, 0.03), P.points_pmf(2.4, 1.7, 0.92, 0.03))
    mg = np.arange(-V4.MAXP, V4.MAXP + 1)
    sd = lambda p: float(np.sqrt(p @ mg ** 2 - (p @ mg) ** 2))   # noqa: E731
    assert sd(v4.margin_pmf) < sd(v1.margin_pmf)


def test_team_games_pbp_tds_and_neutral_home():
    sched = pl.DataFrame({"game_id": ["g1", "g2"], "season": [2024, 2024], "week": [1, 2], "gameday": ["2024-09-08"] * 2,
                          "game_type": ["REG", "REG"], "home_team": ["JAX", "SD"], "away_team": ["NE", "KC"],
                          "home_score": [21, 10], "away_score": [7, 3], "location": ["Neutral", "Home"]})
    ts = pl.DataFrame({"season": [2024] * 4, "week": [1, 1, 2, 2], "team": ["JAX", "NE", "LAC", "KC"],
                       "season_type": ["REG"] * 4, "fg_made": [0, 0, 1, 1], "pat_made": [3, 1, 1, 0],
                       "def_safeties": [0, 0, 0, 0]})
    td = pl.DataFrame({"game_id": ["g1", "g1", "g2"], "td_team": ["JAX", "NE", "LAC"], "td_pbp": [3, 1, 1]})
    g = {(r["game_id"], r["team"]): r for r in V4.team_games(ts, sched, td).iter_rows(named=True)}
    assert g[("g1", "JAX")]["home"] == 0 and g[("g1", "NE")]["home"] == 0      # neutral: no home team
    assert g[("g2", "LAC")]["home"] == 1 and g[("g2", "LAC")]["td"] == 1       # SD mapped to LAC
    assert g[("g2", "KC")]["td"] == 0                                           # no TD rows -> 0
    old = {(r["game_id"], r["team"]): r for r in V4.team_games(ts, sched, td, neutral_fix=False).iter_rows(named=True)}
    assert old[("g1", "JAX")]["home"] == 1


def test_drive_dist_roundtrip():
    dd = _dd()
    back = V4.DriveDist.from_json(dd.to_json())
    assert np.array_equal(back.pairs, dd.pairs) and np.allclose(back.probs, dd.probs)
