"""OddsLink Pinnacle backup (engine.data.oddslink), on the 2026-10-18 probe response."""
import datetime as dt
import json
from pathlib import Path

import polars as pl

from engine.data import oddslink
from engine.picks import final

EV = json.loads((Path(__file__).parent / "fixtures" / "oddslink_pinnacle_20261018.json").read_text())
UTC = dt.timezone.utc


def _g(gid, home, away, k):
    return {"game_id": gid, "season": 2026, "week": 7, "home_team": home, "away_team": away,
            "kickoff_utc": k, "lock_utc": k - dt.timedelta(minutes=15)}


def test_real_response_gives_home_lines():
    games = [_g("MNF", "SF", "WAS", dt.datetime(2026, 10, 20, 0, 15, tzinfo=UTC)),
             _g("SNF", "GB", "DAL", dt.datetime(2026, 10, 19, 0, 20, tzinfo=UTC)),
             _g("OTHER", "CHI", "NE", dt.datetime(2026, 10, 23, 0, 15, tzinfo=UTC))]
    rows = {r["game_id"]: r for r in oddslink.pinnacle_capture_rows(games, dt.datetime(2026, 10, 18, 23, 55, tzinfo=UTC), events=EV)}
    assert set(rows) == {"MNF", "SNF"}                     # NE @ CHI was not in the Pinnacle-only response
    assert rows["MNF"]["home_spread"] == -7.5 and rows["SNF"]["home_spread"] == 1.0
    assert all(r["book"] == "pinnacle" and r["reason"] == "oddslink" for r in rows.values())


def test_most_balanced_line_and_period_markets_ignored():
    e = {"home_team": "Green Bay Packers", "away_team": "Dallas Cowboys", "bookmakers": [{"key": "pinnacle", "markets": [
        {"key": "spreads", "outcomes": [
            {"name": "Dallas Cowboys", "point": 7.5, "price": 1.25, "main": True},
            {"name": "Green Bay Packers", "point": -7.5, "price": 3.80, "main": True},
            {"name": "Dallas Cowboys", "point": -1.0, "price": 1.98},
            {"name": "Green Bay Packers", "point": 1.0, "price": 1.93}]},
        {"key": "spreads", "period": "1h", "outcomes": [
            {"name": "Dallas Cowboys", "point": 0.5, "price": 1.95},
            {"name": "Green Bay Packers", "point": -0.5, "price": 1.95}]}]}]}
    assert oddslink.home_main_spread(e)["home_spread"] == 1.0


def _row(gid, book, spread=-3.0, reason=""):
    return {"game_id": gid, "book": book, "home_spread": spread, "status": "ok", "reason": reason}


def test_chain_oddslink_only_fills_what_oddspapi_left(monkeypatch):
    monkeypatch.setattr(final.store, "append_rows", lambda *a: None)
    now = dt.datetime(2026, 10, 18, 23, 55, tzinfo=UTC)
    due = pl.DataFrame({"game_id": ["g1", "g2"]})
    caps = final.oddspapi_pinnacle_fallback([], due, now, rows_fn=lambda g, t: [_row("g1", "pinnacle", -1.0, "oddspapi")])
    asked = []
    caps = final.oddslink_pinnacle_fallback(caps, due, now,
                                            rows_fn=lambda g, t: asked.extend(x["game_id"] for x in g) or [_row("g2", "pinnacle", 2.5, "oddslink")])
    assert asked == ["g2"]
    assert {(r["game_id"], r["reason"]) for r in caps} == {("g1", "oddspapi"), ("g2", "oddslink")}


def test_oddslink_failure_or_expiry_changes_nothing(monkeypatch):
    monkeypatch.setattr(final.store, "append_rows", lambda *a: (_ for _ in ()).throw(AssertionError("no write")))
    due = pl.DataFrame({"game_id": ["g2"]})
    caps = [_row("g2", "draftkings")]

    def boom(g, t):
        raise RuntimeError("OddsLink HTTP 503")
    assert final.oddslink_pinnacle_fallback(caps, due, dt.datetime(2026, 10, 18, 23, 55, tzinfo=UTC), rows_fn=boom) == caps
    assert final.oddslink_pinnacle_fallback(caps, due, final.ODDSPAPI_FALLBACK_UNTIL, rows_fn=boom) == caps


def test_missing_key_raises_without_a_request(monkeypatch):
    monkeypatch.delenv(oddslink.KEY_ENV, raising=False)
    try:
        oddslink.fetch_pinnacle_spreads(session=object())
        assert False
    except oddslink.MissingKey:
        pass
