import datetime as dt

from engine.picks import game_detail as G

UTC = dt.timezone.utc
KO = dt.datetime(2026, 9, 27, 17, 0, tzinfo=UTC)                    # Sun 1:00 PM ET


def _cap(t, book, spread, gid="g1", price="1.91", upd=None):
    return {"game_id": gid, "captured_at": t.isoformat(), "book": book, "home_spread": str(spread),
            "home_price_decimal": price, "book_last_update": (upd or t).strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "ok"}


def _row(**kw):
    base = {"game_id": "g1", "away": "AAA", "home": "BBB", "kickoff_utc": KO.isoformat(), "league_line": -3.5,
            "market": -3.0, "drift": 0.5, "p_home": 0.47, "p_away": 0.53, "pick": "AAA", "pick_p": 0.53,
            "status": "final", "market_time": (KO - dt.timedelta(minutes=20)).isoformat(),
            "proj_home": 24.0, "proj_away": 20.0, "proj_pick": "BBB", "proj_version": "proj-players-v3",
            "home_score": None, "away_score": None}
    return {**base, **kw}


def _caps():
    tue = dt.datetime(2026, 9, 22, 16, 0, tzinfo=UTC)               # Tue 12:00 ET
    sat = dt.datetime(2026, 9, 26, 15, 0, tzinfo=UTC)
    lock = KO - dt.timedelta(minutes=20)
    after = KO + dt.timedelta(minutes=30)
    caps = []
    for t, lines in ((tue, {"fanduel": -3.5, "draftkings": -3.0, "betmgm": -5.0}),
                     (sat, {"fanduel": -3.5, "draftkings": -3.5, "betmgm": -3.5}),
                     (lock, {"fanduel": -3.0, "draftkings": -3.0, "betmgm": -3.5}),
                     (after, {"fanduel": 9.0, "draftkings": 9.0, "betmgm": 9.0})):   # in-game: must be dropped
        caps += [_cap(t, b, v) for b, v in lines.items()]
    caps.append({**_cap(lock, "ghost", ""), "home_spread": ""})     # blank spread ignored
    caps.append({**_cap(lock, "err", -3.0), "status": "error"})     # failed rows ignored
    caps.append(_cap(lock, "other", -3.0, gid="g2"))                # another game
    return caps


def test_history_drops_after_kickoff_and_bad_rows_and_aligns_books():
    h = G.history(_caps(), "g1", KO)
    assert len(h["t"]) == 3 and set(h["b"]) == {"fanduel", "draftkings", "betmgm"}
    assert h["b"]["fanduel"] == [-3.5, -3.5, -3.0] and h["b"]["betmgm"] == [-5.0, -3.5, -3.5]


def test_lock_books_use_the_pick_capture_with_prices_and_median():
    d = G.build([_row()], _caps(), [], [])["g1"]
    assert d["lock"]["i"] == 2 and d["lock"]["n"] == 3 and d["lock"]["median"] == -3.0
    assert [b["book"] for b in d["lock"]["books"]] == ["betmgm", "draftkings", "fanduel"]     # most home-favored first
    assert d["lock"]["books"][0]["price"] == "−110" and d["lock"]["at"] == "12:40 PM"


def test_provisional_uses_latest_capture():
    d = G.build([_row(status="provisional", market_time=None)], _caps(), [], [])["g1"]
    assert d["lock"]["i"] == 2


def test_tuesday_match_flags_same_hook_and_off():
    win = (dt.datetime(2026, 9, 22, 12, 0, tzinfo=UTC), dt.datetime(2026, 9, 22, 21, 0, tzinfo=UTC))
    d = G.build([_row()], _caps(), [], [], windows={"g1": win})["g1"]
    tue = d["tue"]["books"]
    assert tue["fanduel"]["m"] == "same" and tue["draftkings"]["m"] == "hook" and tue["betmgm"]["m"] == "off"
    assert d["tue"]["at"].endswith("Tue")


def test_tuesday_match_none_without_a_capture_in_the_window():
    win = (dt.datetime(2026, 9, 29, 12, 0, tzinfo=UTC), dt.datetime(2026, 9, 29, 21, 0, tzinfo=UTC))
    assert G.build([_row()], _caps(), [], [], windows={"g1": win})["g1"]["tue"] is None
    assert G.build([_row()], _caps(), [], [])["g1"]["tue"] is None


def test_why_explains_move_probability_projection_and_result():
    r = _row(home_score=24, away_score=16)
    w = G.build([r], _caps(), [{"game_id": "g1", "market_total": "43.5"}], [])["g1"]["why"]
    assert "moved ½ pt toward AAA" in w[0] and "BBB −3.5" in w[0] and "about 51% historically" in w[0]
    assert "53.0%" in w[1] and "(43.5)" in w[1]
    assert "disagrees with the pick" in w[2]
    assert w[3].startswith("Final AAA 16 – BBB 24") and "BBB covered the pool line by 4½ pts" in w[3]


def test_why_no_move_and_strong_move_wording():
    assert "did not move" in G.why(_row(drift=0.0, market=-3.5), None, None)[0]
    s = G.why(_row(drift=-1.5, market=-5.0), None, None)[0]
    assert "1½ pts toward BBB" in s and "57% historically; 52% in the 2025 holdout" in s


def test_inputs_block_maps_starter_names_and_skips_provisional():
    import json
    info = {"home": {"starter": "id1", "qb_delta": -0.09}, "away": {"starter": "id2", "qb_delta": 0.01}, "flags": []}
    proj = {"game_id": "g1", "created_at": "2026-09-27T16:40:00+00:00", "model_version": "proj-players-v3",
            "inputs": json.dumps(info)}
    d = G.build([_row()], _caps(), [], [proj], names={"id1": "Case Keenum"})["g1"]
    assert d["inputs"]["home"]["starter_name"] == "Case Keenum" and d["inputs"]["away"]["starter_name"] == "id2"
    assert G.build([_row()], _caps(), [], [])["g1"]["inputs"] is None


def test_why_wording_for_a_pick_that_has_not_locked():
    w = G.why(_row(status="provisional"), None, None)[0]
    assert w.endswith("Sides that the market moves toward have covered about 51% historically.")
    assert "−3.0 now." in w and "at the pick" not in w


def test_market_source_pinnacle_pick_median_pick_and_provisional():
    lock = KO - dt.timedelta(minutes=20)
    caps = _caps() + [_cap(lock, "pinnacle", -2.5)]
    pin = {"game_id": "g1", "feature_version": "market:pinnacle"}
    d = G.build([_row()], caps, [pin], [])["g1"]
    assert d["src"] == "pinnacle" and d["lock"]["ref"] == -2.5 and d["lock"]["input"] == -2.5
    old = {"game_id": "g1", "feature_version": ""}                  # picked before the switch: the median was used
    d = G.build([_row()], caps, [old], [])["g1"]
    assert d["src"] == "median" and d["lock"]["input"] == d["lock"]["median"]
    d = G.build([_row(status="provisional", market_time=None)], _caps(), [], [])["g1"]
    assert d["src"] == "median" and d["lock"]["ref"] is None          # no Pinnacle line: the preview uses the median
