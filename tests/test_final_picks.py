import datetime as dt
import json

import polars as pl

from engine.data import store
from engine.picks import final
from tests.conftest import FIX

EVENTS = json.loads((FIX / "parlay_nfl_spreads_trimmed.json").read_text())   # ATL@GB, GB -4.5..-5.5
UTC = dt.timezone.utc
LOCK = dt.datetime(2026, 9, 25, 0, 0, tzinfo=UTC)   # ATL@GB kickoff 00:15Z


def _league(tmp_root, rows):
    p = tmp_root / "data" / "lines" / "league_lines.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("game_id,season,week,home_team,away_team,spread,favorite,source,recorded_at\n" + rows)


def test_decide_rules():
    assert final.decide(-6.5, -5.0, None)["pick"] == "away"          # market moved toward away
    assert final.decide(-4.5, -7.5, None)["pick"] == "home"
    d = final.decide(-2.5, -2.5, None)
    assert d["pick"] == "away" and d["pick_rule"] == "no_move_fallback_away"
    m = final.decide(None, -5.0, -6.5)
    assert m["data_status"] == "incomplete" and "LINE_FROM_CBS_ODDS_PAGE_OPEN" in m["flags"]
    n = final.decide(None, None, None)
    assert n["pick"] == "away" and n["missing_input"] == "league_line;market_at_lock"


def test_lock_run_writes_before_lock_once(tmp_root, week3_schedule):
    _league(tmp_root, "2026_03_ATL_GB,2026,3,GB,ATL,-6.5,GB,test,x\n")
    now = LOCK - dt.timedelta(minutes=20)
    out = final.run(week3_schedule, now=now, window_minutes=25, events=EVENTS)
    assert [r["game_id"] for r in out] == ["2026_03_ATL_GB"]
    r = out[0]
    # lock-time test: prediction written before kickoff - lock_buffer
    assert dt.datetime.fromisoformat(r["created_at"]) < dt.datetime.fromisoformat(r["lock_utc"])
    assert r["market_at_lock"] > r["league_line"]          # market -5ish vs league -6.5 -> moved to ATL
    assert r["pick_team"] == "ATL" and r["data_status"] == "complete"
    # second run in the same window: immutable, nothing new
    assert final.run(week3_schedule, now=now + dt.timedelta(minutes=5), events=EVENTS) == []
    assert len(store.read_rows(final.predictions_path())) == 1
    assert (tmp_root / "data" / "predictions" / "slate_2026_w03.md").exists()


def test_games_outside_window_untouched(tmp_root, week3_schedule):
    _league(tmp_root, "")
    out = final.run(week3_schedule, now=LOCK - dt.timedelta(hours=3), window_minutes=25, events=EVENTS)
    assert out == []


def test_manual_fallback_after_lock_is_flagged(tmp_root, week3_schedule):
    _league(tmp_root, "")
    out = final.run(week3_schedule, now=LOCK + dt.timedelta(minutes=5), events=EVENTS, game_id="2026_03_ATL_GB")
    assert len(out) == 1 and "LATE_AFTER_LOCK" in out[0]["flags"]
    assert out[0]["data_status"] == "incomplete"            # no league line recorded
