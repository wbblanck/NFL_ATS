"""Hypothetical reconstruction of missed picks (engine.picks.hypothetical): pure parts, on synthetic data."""
import datetime as dt

import numpy as np

from engine.models.margin_dist import TotalDist
from engine.picks import hypothetical as H

UTC = dt.timezone.utc
K = dt.datetime(2026, 10, 11, 17, 0, tzinfo=UTC)
SMAP = {"m": (-3.5, "h", "a")}


def _g(**kw):
    g = {"season": 2026, "week": 5, "game_id": "2026_05_AAA_BBB", "home_team": "BBB", "away_team": "AAA",
         "kickoff_utc": K, "home_score": 24, "away_score": 17, "total_line": 44.5, "result": 7}
    g.update(kw)
    return g


def _hist(home_price, away_price, at="2026-10-11T15:00:00Z", active=True):
    snap = lambda p: [{"createdAt": at, "price": p, "active": active}]
    return {"markets": {"m": {"outcomes": {"h": {"players": {"0": snap(home_price)}}, "a": {"players": {"0": snap(away_price)}}}}}}


def _td():
    rng = np.random.default_rng(3)
    c = rng.choice([-7.0, -3.5, 2.5, 6.5], 3000)
    T = rng.uniform(38, 54, 3000)
    return TotalDist("shifted_total").fit(c, np.round(-c + rng.normal(0, 13, 3000)), T)


def test_groups_split_by_what_the_pick_file_holds():
    s = [_g(game_id="a"), _g(game_id="b"), _g(game_id="c"), _g(game_id="d", result=None), _g(game_id="e", week=2)]
    p = {"b": {"market_at_lock": "UNAVAILABLE"}, "c": {"market_at_lock": "-3.5", "feature_version": "market:pinnacle"}}
    out = H.groups(s, p)
    assert [g["game_id"] for g in out["no_row"]] == ["a"] and [g["game_id"] for g in out["no_market"]] == ["b"]
    assert [g["game_id"] for g in out["check"]] == ["c"]            # unplayed and pre-live games are skipped


def test_reconstruct_picks_the_side_the_model_prefers_and_grades_it():
    td = _td()
    # Pinnacle home -3.5 against a pool line of home -1.5: market moved toward the home team, so home covers more often
    r = H.reconstruct(_g(), "no_row", _hist(1.95, 1.95), SMAP, -1.5, td, None)
    assert r["status"] == "ok" and r["pinnacle_home_spread"] == -3.5 and r["pick_team"] == "BBB"
    assert r["result"] == "W" and r["final_score"] == "17-24"      # 24-17: home -1.5 covers
    assert "HYPOTHETICAL" in r["flags"] and float(r["p_home_cover"]) > 0.5


def test_reconstruct_check_group_compares_with_the_recorded_pick():
    td = _td()
    pred = {"market_at_lock": "-3.5", "pick_team": "BBB"}
    r = H.reconstruct(_g(), "check", _hist(1.95, 1.95), SMAP, -1.5, td, None, pred=pred)
    assert r["same_line"] == 1 and r["same_pick"] == 1
    r = H.reconstruct(_g(), "check", _hist(1.95, 1.95), SMAP, -1.5, td, None, pred={"market_at_lock": "-3.0", "pick_team": "AAA"})
    assert r["same_line"] == 0 and r["same_pick"] == 0


def test_no_snapshot_before_the_cutoff_or_no_pool_line_gives_no_pick():
    td = _td()
    late = _hist(1.95, 1.95, at="2026-10-11T16:59:00Z")             # after kickoff - 20 min (16:40)
    assert H.reconstruct(_g(), "no_row", late, SMAP, -1.5, td, None)["status"].startswith("no active Pinnacle")
    assert H.reconstruct(_g(), "no_row", None, SMAP, -1.5, td, None)["status"] == "no history returned"
    assert H.reconstruct(_g(), "no_row", _hist(1.95, 1.95), SMAP, None, td, None)["status"].startswith("no pool line")
    assert H.reconstruct(_g(), "no_row", _hist(1.95, 1.95, active=False), SMAP, -1.5, td, None)["pick_team"] == ""


def test_no_market_group_does_not_compare_with_a_missing_recorded_line():
    td = _td()
    pred = {"market_at_lock": "", "pick_team": "AAA"}               # recorded with no market (UNAVAILABLE or blank)
    r = H.reconstruct(_g(), "no_market", _hist(1.95, 1.95), SMAP, -1.5, td, None, pred=pred)
    assert r["status"] == "ok" and r["same_line"] == "" and r["recorded_pick"] == "AAA"
