from engine.backtest.variants2026 import _straddle, binom_sf, holm


def test_binom_sf():
    assert binom_sf(0, 4) == 1.0
    assert abs(binom_sf(10, 10) - 1 / 1024) < 1e-12
    assert abs(binom_sf(9, 10) - 11 / 1024) < 1e-12


def test_holm_steps_down_and_stops():
    r = holm({"a": 0.001, "b": 0.02, "c": 0.04})
    assert r == {"a": True, "b": True, "c": True}
    r = holm({"a": 0.001, "b": 0.04, "c": 0.01})
    assert r == {"a": True, "c": True, "b": True}
    r = holm({"a": 0.03, "b": 0.001})
    assert r == {"b": True, "a": True}
    assert holm({"a": 0.03, "b": 0.03, "c": 0.03})["a"] is False


def test_straddle():
    assert _straddle(-2.5, -3.0)          # market reached 3
    assert _straddle(-3.5, -2.5)
    assert not _straddle(-3.5, -4.0)
    assert _straddle(6.5, 7.5)
    assert not _straddle(-1.5, -1.5)
