from engine.backtest import tracked_family as T


def test_exact_tail():
    assert T.exact_upper_tail(0, 5) == 1.0 and T.exact_upper_tail(5, 5) == 1 / 32
    assert abs(T.exact_upper_tail(60, 100) - 0.02844) < 1e-4
    assert T.exact_upper_tail(0, 0) == 1.0


def test_holm_step_down_stops_at_first_failure():
    h = T.holm({"a": 0.01, "b": 0.02, "c": 0.04, "d": 0.5})
    assert h["a"]["pass"] and h["a"]["threshold"] == 0.0125
    assert not h["b"]["pass"] and h["b"]["threshold"] == 0.05 / 3      # 0.02 > 0.0167
    assert not h["c"]["pass"]                                         # an earlier failure stops the step-down
    assert T.holm({"x": 0.001})["x"]["pass"]


def _row(pick, v1=None, hy=None, kn=None, kres=""):
    r = {"pick": pick, "shadow_pick": kn or "", "shadow_result": kres}
    if v1:
        r["proj_proj-poisson-v1"] = v1
    if hy:
        r["hybrid"] = hy
    return r


def test_differing_games_only():
    rows = [_row("A", v1="B W"), _row("A", v1="B L"), _row("A", v1="A W"), _row("C", kn="D", kres="W"), _row("E")]
    assert T.differing(rows, "proj-poisson-v1") == (1, 1)             # same-pick game and missing pick are ignored
    assert T.differing(rows, "keynum") == (1, 0)
    assert T.differing(rows, "hybrid") == (0, 0)


def test_minimum_differing_games_blocks_a_pass():
    rows = [_row("A", v1="B W") for _ in range(30)]
    out = T.evaluate(rows)
    assert out["proj-poisson-v1"]["p"] < 1e-6 and not out["proj-poisson-v1"]["passes"] and not out["proj-poisson-v1"]["enough"]
    rows = [_row("A", v1="B W") for _ in range(100)]
    assert T.evaluate(rows)["proj-poisson-v1"]["passes"]
