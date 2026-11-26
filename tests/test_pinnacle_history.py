import datetime as dt
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "oph", Path(__file__).resolve().parents[1] / "scripts" / "fetch" / "oddspapi_pinnacle_history.py")
oph = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oph)

KO = dt.datetime(2026, 11, 22, 18, 0, tzinfo=dt.timezone.utc)


def snap(hours_before, price=1.95):
    t = (KO - dt.timedelta(hours=hours_before)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"createdAt": t, "price": price, "active": True}


def hist():
    # line -3.5 from 100 h out, line -4.5 from 5 h out
    def mk(snaps_h, snaps_a):
        return {"outcomes": {"1": {"players": {"0": snaps_h}}, "2": {"players": {"0": snaps_a}}}}
    return {"bookmakers": {"pinnacle": {"markets": {
        "m35": mk([snap(100), snap(5, 2.5)], [snap(100), snap(5, 1.6)]),
        "m45": mk([snap(5)], [snap(5)])}}}}


def test_game_row_offsets_and_open():
    smap = {"m35": (-3.5, "1", "2"), "m45": (-4.5, "1", "2")}
    f = {"fixtureId": "f1", "startTime": KO.strftime("%Y-%m-%dT%H:%M:%SZ")}
    r = oph.game_row(f, "SF", "SEA", hist(), smap)
    assert r["h168_spread"] == ""                  # nothing existed 168 h out
    assert r["h48_spread"] == -3.5 and r["h24_spread"] == -3.5
    assert r["lock_spread"] == -4.5                # the balanced line at lock
    assert r["open_spread"] == -3.5 and r["span_h"] == 100.0


def test_game_row_no_history():
    f = {"fixtureId": "f2", "startTime": KO.strftime("%Y-%m-%dT%H:%M:%SZ")}
    r = oph.game_row(f, "SF", "SEA", {}, {})
    assert r["lock_spread"] == "" and r["first_seen_utc"] == "" and r["span_h"] == ""
