import datetime as dt
import json

from engine.picks import dashboard as D

UTC = dt.timezone.utc


def _k(day, h, m=0):                      # an Eastern (EDT, UTC-4) wall-clock kickoff, as UTC
    return dt.datetime(2026, 9, day, h, m, tzinfo=dt.timezone(dt.timedelta(hours=-4))).astimezone(UTC)


def test_slots_group_by_day_and_gap_with_readable_labels():
    ko = {"thu": _k(24, 20, 15), "s1": _k(27, 13), "s2": _k(27, 13), "s3": _k(27, 16, 5), "s4": _k(27, 16, 25),
          "snf": _k(27, 20, 20), "mnf": _k(28, 20, 15)}
    idx, meta = D.slots_for(ko)
    assert [m["day"] for m in meta] == ["Thursday", "Sunday", "Sunday", "Sunday", "Monday"]
    assert [m["times"] for m in meta] == ["8:15 PM", "1:00 PM", "4:05 & 4:25 PM", "8:20 PM", "8:15 PM"]
    assert idx["s1"] == idx["s2"] and idx["s3"] == idx["s4"] and idx["s2"] != idx["s3"]


def test_slot_label_spans_meridiem():
    _, meta = D.slots_for({"a": _k(27, 11, 30), "b": _k(27, 13)})
    assert meta[0]["times"] == "11:30 AM & 1:00 PM"


def test_signal_buckets():
    assert D._signal(0)[0] == "flat" and D._signal("0.5")[0] == "lean" and D._signal(-1)[0] == "strong"
    assert D._signal(None)[0] == "none" and D._signal("UNAVAILABLE")[0] == "none"


def _row(gid, ko, status, **kw):
    base = {"game_id": gid, "away": "AAA", "home": "BBB", "kickoff_utc": ko.isoformat(), "league_line": -3.5,
            "market": -3.0, "drift": 0.5, "p_home": 0.47, "p_away": 0.53, "pick": "AAA", "status": status,
            "market_books": 15, "market_time": (ko - dt.timedelta(minutes=20)).isoformat(),
            "proj_home": 24.0, "proj_away": 20.0, "proj_pick": "BBB", "proj_version": "proj-players-v3",
            "proj_flags": "", "home_score": None, "away_score": None}
    return {**base, **kw}


def _payload(html):
    start = html.index("const D=") + len("const D=")
    return json.JSONDecoder().raw_decode(html[start:])[0]


def test_render_merges_results_locks_and_next_pick():
    now = dt.datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    rows = [_row("g1", _k(27, 13), "final", home_score=24, away_score=16),
            _row("g2", _k(27, 20, 20), "provisional", market_time=(now - dt.timedelta(minutes=5)).isoformat())]
    results = {"g1": {"result": "L", "proj_proj-players-v3": "BBB W"}}
    live = {"W": 0, "L": 1, "N": 1, "claim_at": 256, "projection_models": {
        "proj-poisson-v1": {"W": 1, "L": 0}, "proj-players-v3": {"W": 1, "L": 0}}}
    html = D.render(rows, 2026, 3, live, now, results)
    d = _payload(html)
    assert "__DATA__" not in html and d["record"] == "0-1" and d["graded"] == 1 and d["claim_at"] == 256
    g1, g2 = d["games"]
    assert g1["res"] == "L" and g1["pres"] == "W" and g1["lead"] == 20 and g1["at"] == "12:40 PM"
    assert g1["hs"] == 24 and g1["as"] == 16
    assert g2["res"] is None and g2["pick_at"] == "8:00 PM"
    assert d["next_lock"] == {"at": "8:00 PM", "game": "AAA @ BBB"}
    assert [m["label"] for m in d["models"]] == ["Official pick", "Team-only projection", "Player projection"]
    assert d["games"][0]["slot"] != d["games"][1]["slot"]


def test_render_without_results_or_projection_models_still_works():
    now = dt.datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    d = _payload(D.render([_row("g1", _k(27, 13), "provisional")], 2026, 3, {"N": 0, "W": 0, "L": 0}, now))
    assert d["record"] == "0-0" and d["models"] == [{"label": "Official pick", "W": 0, "L": 0}]
    assert d["games"][0]["res"] is None and d["games"][0]["pres"] is None
