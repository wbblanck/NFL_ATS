import datetime as dt
import json

from engine.data import market, store
from tests.conftest import FIX

EVENTS = json.loads((FIX / "parlay_nfl_spreads_trimmed.json").read_text())
UTC = dt.timezone.utc


def test_kickoff_and_lock_times(week3_schedule):
    g = week3_schedule.filter(week3_schedule["game_id"] == "2026_03_ATL_GB").row(0, named=True)
    # 20:15 ET on 2026-09-24 is EDT (UTC-4) -> 00:15 UTC next day; matches Parlay commence_time.
    assert g["kickoff_utc"] == dt.datetime(2026, 9, 25, 0, 15, tzinfo=UTC)
    assert g["kickoff_utc"] - g["lock_utc"] == dt.timedelta(minutes=15)
    assert EVENTS[0]["commence_time"] == "2026-09-25T00:15:00Z"


def test_parse_home_perspective():
    rows = market.parse_events(EVENTS)
    gb = [r for r in rows if r["home_team"] == "GB"]
    assert gb and all(r["home_spread"] < 0 for r in gb)      # GB favored in every book
    assert {r["book"] for r in gb} >= {"fanduel", "betrivers"}


def test_capture_respects_lock_window(tmp_root, week3_schedule):
    lock = dt.datetime(2026, 9, 25, 0, 0, tzinfo=UTC)
    far = market.capture(week3_schedule, now=lock - dt.timedelta(hours=5), window_minutes=90, events=EVENTS)
    assert far == []
    near = market.capture(week3_schedule, now=lock - dt.timedelta(minutes=30), window_minutes=90, events=EVENTS)
    assert near and {r["game_id"] for r in near} == {"2026_03_ATL_GB"}
    assert all(r["minutes_to_lock"] == 30.0 for r in near)


def test_market_at_lock_has_no_lookahead(tmp_root, week3_schedule):
    lock = dt.datetime(2026, 9, 25, 0, 0, tzinfo=UTC)
    market.capture(week3_schedule, now=lock - dt.timedelta(minutes=60), events=EVENTS)
    later = json.loads(json.dumps(EVENTS))
    for b in later[0]["bookmakers"]:
        for o in b["markets"][0]["outcomes"]:
            o["point"] = -99.5 if o["name"] == later[0]["home_team"] else 99.5
    market.capture(week3_schedule, now=lock + dt.timedelta(minutes=10), events=later)
    caps = store.read_rows(tmp_root / "data" / "lines" / "market_captures.csv")
    m = market.market_at_lock(caps, "2026_03_ATL_GB", as_of=lock)
    assert m["median"] is not None and m["median"] > -20      # post-lock -99.5 never used
    assert dt.datetime.fromisoformat(m["captured_at"]) <= lock
    m2 = market.market_at_lock(caps, "2026_03_ATL_GB", as_of=lock + dt.timedelta(hours=1))
    assert m2["median"] == -99.5
