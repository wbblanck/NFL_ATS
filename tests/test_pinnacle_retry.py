"""One Pinnacle retry before a pick falls back to the median (engine.picks.final.retry_missing_pinnacle)."""
import polars as pl

from engine.picks import final


def _row(gid, book, spread=-3.0, status="ok"):
    return {"game_id": gid, "book": book, "home_spread": spread, "status": status}


def _due(*gids):
    return pl.DataFrame({"game_id": list(gids)})


def test_no_retry_when_pinnacle_is_present():
    calls, slept = [], []
    caps = [_row("g1", "pinnacle"), _row("g1", "draftkings")]
    out = final.retry_missing_pinnacle(caps, _due("g1"), capture_fn=lambda *a, **k: calls.append(1) or [],
                                       sleep_fn=slept.append)
    assert out == caps
    assert calls == [] and slept == []


def test_retry_takes_the_retry_rows_when_pinnacle_appears():
    caps = [_row("g1", "draftkings"), _row("g1", "fanduel")]
    slept = []

    def fake_capture(due, now=None, events=None, all_games=False):
        assert list(due["game_id"]) == ["g1"] and all_games
        return [_row("g1", "pinnacle", -3.5), _row("g1", "draftkings", -3.5)]

    out = final.retry_missing_pinnacle(caps, _due("g1"), capture_fn=fake_capture, sleep_fn=slept.append, wait_s=60)
    assert slept == [60]
    assert len(out) == 2                      # the retry's rows only: the first capture's rows are not mixed in
    assert {r["book"] for r in out} == {"pinnacle", "draftkings"}
    assert all(r["home_spread"] == -3.5 for r in out)


def test_fallback_rows_kept_when_retry_still_has_no_pinnacle():
    caps = [_row("g1", "draftkings"), _row("g2", "pinnacle")]
    out = final.retry_missing_pinnacle(caps, _due("g1", "g2"),
                                       capture_fn=lambda due, **k: [_row("g1", "draftkings", -2.0)],
                                       sleep_fn=lambda s: None)
    assert out == caps                        # g1 keeps its first capture; g2 was never retried


def test_failed_retry_keeps_the_first_capture():
    caps = [_row("g1", "draftkings")]

    def broken_capture(due, **k):
        raise RuntimeError("network down")

    out = final.retry_missing_pinnacle(caps, _due("g1"), capture_fn=broken_capture, sleep_fn=lambda s: None)
    assert out == caps                        # a raised error never reaches the pick


def test_oddspapi_fallback_adds_pinnacle_only_for_games_missing_it(monkeypatch):
    import datetime as dt
    written = []
    monkeypatch.setattr(final.store, "append_rows", lambda p, f, rows: written.extend(rows))
    caps = [_row("g1", "pinnacle"), _row("g2", "draftkings")]
    seen = []

    def rows_fn(games, now):
        seen.extend(g["game_id"] for g in games)
        return [{**_row("g2", "pinnacle", -2.5), "reason": "oddspapi"}]
    out = final.oddspapi_pinnacle_fallback(caps, _due("g1", "g2"), dt.datetime(2026, 10, 18, 23, 55, tzinfo=dt.timezone.utc), rows_fn=rows_fn)
    assert seen == ["g2"]
    assert len(out) == 3 and written == out[2:]
    assert final.market.consensus([r for r in out if r["game_id"] == "g2"], "pinnacle")["reference"] == -2.5


def test_oddspapi_fallback_failure_leaves_capture_unchanged(monkeypatch):
    import datetime as dt
    monkeypatch.setattr(final.store, "append_rows", lambda *a: (_ for _ in ()).throw(AssertionError("no write")))
    caps = [_row("g2", "draftkings")]

    def boom(games, now):
        raise RuntimeError("HTTP 503")
    assert final.oddspapi_pinnacle_fallback(caps, _due("g2"), dt.datetime.now(dt.timezone.utc), rows_fn=boom) == caps
    assert final.oddspapi_pinnacle_fallback([_row("g2", "pinnacle")], _due("g2"), dt.datetime.now(dt.timezone.utc),
                                            rows_fn=boom) == [_row("g2", "pinnacle")]   # not called when present


def test_oddspapi_fallback_has_no_end_date_unless_one_is_set(monkeypatch):
    import datetime as dt
    assert final.ODDSPAPI_FALLBACK_UNTIL is None                       # owner decision 2026-10-19: stays on
    caps = [_row("g2", "draftkings")]
    called = []
    monkeypatch.setattr(final.store, "append_rows", lambda *a: None)
    later = dt.datetime(2027, 1, 1, tzinfo=dt.timezone.utc)
    final.oddspapi_pinnacle_fallback(caps, _due("g2"), later, rows_fn=lambda g, n: called.append(1) or [])
    assert called == [1]
    monkeypatch.setattr(final, "ODDSPAPI_FALLBACK_UNTIL", later)    # an end date, when set, still switches it off
    out = final.oddspapi_pinnacle_fallback(caps, _due("g2"), later, rows_fn=lambda g, n: called.append(1) or [])
    assert out == caps and called == [1]
