import datetime as dt

from engine.backtest import cbs_lines as CL


def test_match_rules():
    assert CL.match(-7.5, -7.5) == "exact"
    assert CL.match(-7.0, -7.5) == "hook_fav"     # home favorite must now win by 8
    assert CL.match(-7.0, -6.5) == "hook_dog"
    assert CL.match(3.0, 3.5) == "hook_fav"       # away favorite by 3 -> by 3.5
    assert CL.match(3.0, 2.5) == "hook_dog"
    assert CL.match(0.0, -0.5) == "hook_pk"
    assert CL.match(-6.5, -7.5) is None and CL.match(-7.0, -8.5) is None


def test_q1_candidates_rank_exact_source_first():
    ll = {"g1": -7.5, "g2": 2.5}
    t = "2026-09-29T16:00:00+00:00"
    market = [{"status": "ok", "game_id": "g1", "captured_at": t, "book": "a", "home_spread": "-7.5"},
              {"status": "ok", "game_id": "g2", "captured_at": t, "book": "a", "home_spread": "2.5"},
              {"status": "ok", "game_id": "g1", "captured_at": t, "book": "b", "home_spread": "-6.5"},
              {"status": "ok", "game_id": "g2", "captured_at": t, "book": "b", "home_spread": "3.5"}]
    win = (dt.datetime(2026, 9, 29, 12, tzinfo=dt.timezone.utc), dt.datetime(2026, 9, 29, 21, tzinfo=dt.timezone.utc))
    top = CL.q1_candidates(ll, market, [], win)["candidates"][0]
    assert top["source"] == "book:a" and top["rate"] == 1.0
