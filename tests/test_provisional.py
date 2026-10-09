import datetime as dt

from engine.picks import provisional as pv

NOW = dt.datetime(2026, 10, 7, 16, 0, tzinfo=dt.timezone.utc)


def _row(gid, pick, market, status="provisional", line=-3.5, drift=0.5):
    return {"game_id": gid, "home": "AAA", "away": "BBB", "pick": pick, "market": market, "status": status,
            "league_line": line, "drift": drift, "p_home": 0.55, "p_away": 0.45}


def test_record_logs_only_changes_and_only_real_provisional_rows(tmp_path):
    p = tmp_path / "log.csv"
    rows = [_row("g1", "AAA", -3.0), _row("g2", "BBB", 2.5, status="final"), _row("g3", "AAA", -3.0, line=None),
            _row("g4", "AAA", -3.0, drift="")]
    assert pv.record(rows, NOW, p) == 1                                  # final, no pool line and no drift are skipped
    assert pv.record(rows, NOW, p) == 0                                  # nothing changed
    rows[0] = _row("g1", "BBB", -3.0)                                     # the pick flipped
    assert pv.record(rows, NOW, p) == 1
    assert [r["pick"] for r in pv.load(p)] == ["AAA", "BBB"]


def test_flips_compare_the_first_logged_pick_with_the_current_one(tmp_path):
    p = tmp_path / "log.csv"
    pv.record([_row("g1", "AAA", -3.0)], NOW, p)
    pv.record([_row("g1", "BBB", -3.5)], NOW + dt.timedelta(hours=2), p)
    log = pv.load(p)
    assert pv.flips([_row("g1", "BBB", -3.5, status="final")], log) == {
        "g1": {"was": "AAA", "at": NOW.isoformat(timespec="seconds"), "mk": "-3.0", "n": 1}}
    assert pv.flips([_row("g1", "AAA", -3.0)], log) == {}                  # back where it started: no flip
    assert pv.flips([_row("g9", "AAA", -3.0)], log) == {}                  # never logged
