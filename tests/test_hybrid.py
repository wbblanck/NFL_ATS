from engine.picks import hybrid


def test_market_pick_on_big_moves_and_v1_on_small_ones():
    assert hybrid.pick("BUF", "1.0", "MIA") == ("BUF", "market")
    assert hybrid.pick("BUF", -1.5, "MIA") == ("BUF", "market")
    assert hybrid.pick("BUF", 0.5, "MIA") == ("MIA", "v1")
    assert hybrid.pick("BUF", "0.0", "MIA") == ("MIA", "v1")
    assert hybrid.pick("BUF", -0.5, "BUF") == ("BUF", "v1")


def test_missing_inputs_fall_back_to_the_live_pick():
    assert hybrid.pick("BUF", "UNAVAILABLE", "MIA") == ("BUF", "market")
    assert hybrid.pick("BUF", None, "MIA") == ("BUF", "market")
    assert hybrid.pick("BUF", 0.0, "") == ("BUF", "market")
    assert hybrid.pick("BUF", 0.0, None) == ("BUF", "market")
