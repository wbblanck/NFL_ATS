"""ATS terminal data (engine.picks.terminal): exported margin distributions and calibration points."""
import numpy as np

from engine.models.margin_dist import MarginDist, TotalDist
from engine.picks import terminal as T


def _synthetic(n=4000, seed=7):
    rng = np.random.default_rng(seed)
    c = rng.choice([-10.5, -7, -3, -1, 2.5, 6.5], n)
    total = rng.uniform(38, 54, n)
    m = -c + rng.normal(0, 13, n) * (total / 46)
    return c, np.round(m), total


def test_pmf_sums_to_one_and_reproduces_cover_probs_total_model():
    c, m, tot = _synthetic()
    td = TotalDist("shifted_total").fit(c, m, tot)
    for mk, line, total in ((-3.0, -2.5, 44.5), (6.5, 7.5, 40.0), (-10.5, -9.5, 52.5)):
        d = T.margin_pmf(td, mk, total)
        assert abs(sum(d["p"]) + d["lo"] + d["hi"] - 1) < 1e-4
        assert len(d["p"]) == T.KMAX - T.KMIN + 1 and d["model"].startswith("TotalDist")
        assert abs(T.p_home_from(d, line) - td.cover_probs(mk, line, total)[0]) < 2e-5   # pmf rounded to 5 dp


def test_pmf_without_total_uses_margin_model():
    c, m, _ = _synthetic()
    md = MarginDist(kind="shifted").fit(c, m)
    d = T.margin_pmf(md, -3.0, None)
    assert d["model"].startswith("MarginDist") and d["total"] is None
    assert abs(T.p_home_from(d, -2.5) - md.cover_probs(-3.0, -2.5)[0]) < 2e-5


def test_check_dist_flags_a_mismatch():
    c, m, tot = _synthetic()
    td = TotalDist("shifted_total").fit(c, m, tot)
    d = {"g1": T.margin_pmf(td, -3.0, 44.5), "g2": T.margin_pmf(td, -3.0, 44.5)}
    p = td.cover_probs(-3.0, -2.5, 44.5)[0]
    rows = [{"game_id": "g1", "league_line": -2.5, "p_home": round(p, 4)},
            {"game_id": "g2", "league_line": -2.5, "p_home": round(p + 0.01, 4)},
            {"game_id": "g3", "league_line": -2.5, "p_home": 0.5}]                       # no distribution: skipped
    out = T.check_dist(d, rows)
    assert out["n"] == 2 and out["ok"] == 1 and out["bad"][0][0] == "g2"


def test_calibration_uses_the_picked_side(monkeypatch):
    preds = [{"game_id": "a", "pick": "home", "p_home_cover": "0.56", "p_away_cover": "0.44", "supersedes": ""},
             {"game_id": "b", "pick": "away", "p_home_cover": "0.47", "p_away_cover": "0.53", "supersedes": ""},
             {"game_id": "c", "pick": "home", "p_home_cover": "UNAVAILABLE", "p_away_cover": "", "supersedes": ""}]
    monkeypatch.setattr(T.store, "read_rows", lambda p: preds)
    graded = [{"game_id": "a", "result": "W", "week": "3"}, {"game_id": "b", "result": "L", "week": "4"},
              {"game_id": "c", "result": "W", "week": "4"}]
    assert T.calibration(graded) == [{"p": 0.56, "w": 1, "week": 3, "id": "a"}, {"p": 0.53, "w": 0, "week": 4, "id": "b"}]
