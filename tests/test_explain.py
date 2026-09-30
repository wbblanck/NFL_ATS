import math
from types import SimpleNamespace

import numpy as np
import pytest

from engine.picks import explain

TEAMS = ["AAA", "BBB", "CCC"]
N = len(TEAMS)


def _rt(off_a=0.15, def_b=0.10):
    """td/fg coefficient vectors: [intercept, home, off x N, def x N]."""
    td, fg = np.zeros(2 + 2 * N), np.zeros(2 + 2 * N)
    td[0], fg[0] = math.log(2.0), math.log(1.6)
    td[1], fg[1] = 0.08, 0.03
    td[2], fg[2] = off_a, 0.05                    # AAA offense
    td[2 + N + 1], fg[2 + N + 1] = def_b, -0.04    # BBB defense (positive = lets more through in the model's sign)
    return SimpleNamespace(teams=TEAMS, td=td, fg=fg, p_xp=0.94, p_2=0.05)


def _expected(rt, team, opp, home):
    i, j = TEAMS.index(team), TEAMS.index(opp)
    per_td = 6 + rt.p_xp + 2 * rt.p_2
    tot = 0.0
    for b, k in ((rt.td, per_td), (rt.fg, 3.0)):
        tot += k * math.exp(b[0] + b[1] * home + b[2 + i] - b[2 + N + j])
    return tot


def _model():
    feats = [f for _, _, fs in explain.GROUPS for f in fs]
    beta = {f: {"td": 0.02 * (k + 1) * (-1) ** k, "fg": 0.01 * (k + 1)} for k, f in enumerate(feats)}
    beta["intercept"] = {"td": -0.03, "fg": 0.02}
    return {"beta": beta, "features": feats}


def _feat(**kw):
    base = {f: 0.0 for _, _, fs in explain.GROUPS for f in fs}
    base.update(qb_delta=0.1, ol=0.2, skill=0.1, opp_dl=0.05, rest_diff=3, short_week=0, off_bye=1, tz_shift=2,
                division=1, dome=0, starter_name="Pat Q. Back")
    return {**base, **kw}


def _sum(t):
    return t["baseline"] + sum(i["pts"] for i in t["items"])


def test_team_only_pieces_add_up_to_the_formula_projection():
    rt = _rt()
    for team, opp, home in (("AAA", "BBB", 1), ("BBB", "AAA", 0)):
        t = explain.team(rt, team, opp, home)
        assert t["total"] == pytest.approx(_expected(rt, team, opp, home), abs=0.006)
        assert _sum(t) == pytest.approx(t["total"], abs=0.02)
        assert [i["key"] for i in t["items"]] == (["off", "def", "home"] if home else ["off", "def"])


def test_league_average_team_has_zero_effects_and_baseline_equals_total():
    rt = _rt(0, 0)
    rt.td[1] = rt.fg[1] = 0
    rt.fg[2] = rt.fg[2 + N + 1] = 0
    t = explain.team(rt, "AAA", "BBB", 1)
    assert t["total"] == pytest.approx(t["baseline"], abs=0.006)
    assert all(abs(i["pts"]) < 0.006 for i in t["items"])


def test_v3_pieces_add_up_and_are_signed_by_direction():
    rt, m = _rt(), _model()
    t = explain.team(rt, "AAA", "BBB", 1, _feat(), m)
    assert _sum(t) == pytest.approx(t["total"], abs=0.03)
    assert {i["key"] for i in t["items"]} >= {"off", "def", "home", "qb", "own_inj", "opp_inj", "sched", "other"}
    assert next(i for i in t["items"] if i["key"] == "off")["pts"] > 0        # positive offense rating adds points


def test_shown_score_rescales_the_pieces_so_they_sum_to_it():
    rt, m = _rt(), _model()
    raw = explain.team(rt, "AAA", "BBB", 1, _feat(), m)
    t = explain.team(rt, "AAA", "BBB", 1, _feat(), m, shown=round(raw["total"], 1) + 0.04)
    assert t["total"] == pytest.approx(round(raw["total"], 1) + 0.04)
    assert _sum(t) == pytest.approx(t["total"], abs=0.03)


def test_notes_carry_the_facts_behind_each_adjustment():
    t = explain.team(_rt(), "AAA", "BBB", 1, _feat(qb1_out=1), _model())
    n = {i["key"]: i["note"] for i in t["items"]}
    assert "Pat Q. Back" in n["qb"] and "+0.100" in n["qb"] and "QB1 listed out" in n["qb"]
    assert "line 0.20" in n["own_inj"] and "DL 0.05" in n["opp_inj"]
    assert "+3 days of rest" in n["sched"] and "coming off a bye" in n["sched"] and "2 time zones" in n["sched"]
    assert "Division game" in n["other"] and "open air" in n["other"]


def test_game_uses_v3_only_when_both_feature_rows_exist():
    rt, m = _rt(), _model()
    g = explain.game(rt, "AAA", "BBB", _feat(), _feat(), m, shown=(24.0, 20.0))
    assert g["model"] == "proj-players-v3" and g["home"]["total"] == 24.0 and g["away"]["total"] == 20.0
    g1 = explain.game(rt, "AAA", "BBB", _feat(), None, m)
    assert g1["model"] == "proj-poisson-v1" and {i["key"] for i in g1["home"]["items"]} == {"off", "def", "home"}
