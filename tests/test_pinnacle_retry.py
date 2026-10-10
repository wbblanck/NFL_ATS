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
