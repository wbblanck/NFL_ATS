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


def test_alternate_spreads_keep_main_line():
    ev = [{"id": "x", "commence_time": "2026-09-27T17:00:00Z", "home_team": "Buffalo Bills",
           "away_team": "Los Angeles Chargers", "bookmakers": [{"key": "betrivers", "markets": [{
               "key": "spreads", "outcomes": [
                   {"name": "Buffalo Bills", "point": -5.5, "price": 1.55},
                   {"name": "Los Angeles Chargers", "point": 5.5, "price": 2.45},
                   {"name": "Buffalo Bills", "point": -7.0, "price": 1.89},
                   {"name": "Los Angeles Chargers", "point": 7.0, "price": 1.93}]}]}]}]
    rows = market.parse_events(ev)
    assert len(rows) == 1 and rows[0]["home_spread"] == -7.0


def test_historical_snapshot_archived_at_snapshot_time(tmp_root, week3_schedule):
    """Backfilled Tuesday snapshots keep the time the prices describe, are marked 'hist-', and are usable by
    market_at_lock only from that time on (no look-ahead)."""
    ts = "2026-09-24T20:00:00Z"                      # after every book update in the fixture (latest 19:42:52Z)
    rows = market.capture_historical(week3_schedule, ts, events=EVENTS, snapshot_ts=ts)
    assert rows and all(r["capture_id"] == "hist-20260924T200000Z" for r in rows)
    assert all(r["captured_at"].startswith("2026-09-24T20:00:00") for r in rows)
    assert all(r["reason"].startswith("historical snapshot, retrieved") for r in rows)
    from engine import config
    caps = store.read_rows(config.path("lines") / "market_captures.csv")
    before = market.market_at_lock(caps, "2026_03_ATL_GB", dt.datetime(2026, 9, 24, 19, 59, tzinfo=UTC))
    after = market.market_at_lock(caps, "2026_03_ATL_GB", dt.datetime(2026, 9, 24, 20, 1, tzinfo=UTC))
    assert before["median"] is None and after["median"] is not None


def test_historical_response_shapes():
    ev = [{"id": "x"}]
    assert market.unwrap_historical(ev, "2026-09-28T12:00:00Z") == ("2026-09-28T12:00:00Z", ev)     # Parlay: bare list
    assert market.unwrap_historical({"timestamp": "2026-09-28T11:55:00Z", "data": ev}, "t") == ("2026-09-28T11:55:00Z", ev)
    import pytest
    with pytest.raises(ValueError):
        market.unwrap_historical({"detail": {"error": "HISTORICAL_LIMIT"}}, "t")


def test_historical_rejects_updates_after_the_snapshot(tmp_root, week3_schedule):
    """A 'historical' response carrying later prices must not be archived as that moment."""
    import pytest
    with pytest.raises(ValueError, match="not a snapshot"):
        market.capture_historical(week3_schedule, "2026-09-22T16:00:00Z", events=EVENTS, snapshot_ts="2026-09-22T16:00:00Z")
    ts = dt.datetime(2026, 9, 24, 19, 30, tzinfo=UTC)           # between the fixture's first and last updates
    kept_ev, kept, dropped = market.only_before(EVENTS, ts)
    assert kept > 0 and dropped > 0
    for e in kept_ev:
        for b in e["bookmakers"]:
            assert dt.datetime.fromisoformat(b["last_update"].replace("Z", "+00:00")) <= ts + dt.timedelta(minutes=2)
    rows = market.capture_historical(week3_schedule, "2026-09-24T19:30:00Z", events=EVENTS,
                                     snapshot_ts="2026-09-24T19:30:00Z")
    assert rows and "dropped for updates after the snapshot" in rows[0]["reason"]
