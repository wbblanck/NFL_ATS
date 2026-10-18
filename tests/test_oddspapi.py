"""OddsPapi client helpers (engine.data.oddspapi), on synthetic responses shaped like kmodel's MLB ones."""
import pytest

from engine.data import oddspapi


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


class _Session:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, dict(params)))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv(oddspapi.KEY_ENV, "SECRETKEY123")
    monkeypatch.setattr(oddspapi.time, "sleep", lambda s: None)


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv(oddspapi.KEY_ENV)
    with pytest.raises(oddspapi.MissingKey):
        oddspapi.call("sports", session=_Session())


def test_call_retries_429_then_succeeds():
    s = _Session(_Resp(429, None), _Resp(200, [{"sportId": 1}]))
    assert oddspapi.call("sports", session=s) == (200, [{"sportId": 1}])
    assert len(s.calls) == 2
    assert s.calls[0][1]["apiKey"] == "SECRETKEY123"


def test_call_does_not_retry_403():
    s = _Session(_Resp(403, {"error": "x"}), _Resp(200, []))
    assert oddspapi.call("sports", session=s) == (403, None)
    assert len(s.calls) == 1


def test_network_error_message_is_scrubbed(capsys):
    s = _Session(*[RuntimeError("GET ...?apiKey=SECRETKEY123 failed")] * 3)
    assert oddspapi.call("sports", session=s) == (None, None)
    err = capsys.readouterr().err
    assert "SECRETKEY123" not in err and "***" in err


def test_request_count_keeps_only_counts():
    acct = {"email": "someone@example.com", "subscriptions": [{"request_count": 26, "request_limit": 250}]}
    assert oddspapi.request_count(session=_Session(_Resp(200, acct))) == (26, 250)
    assert oddspapi.request_count(session=_Session(_Resp(500, None), _Resp(500, None), _Resp(500, None))) == (None, None)


def test_items_of_and_last_quote():
    assert oddspapi.items_of([1, 2]) == [1, 2]
    assert oddspapi.items_of({"data": [3]}) == [3]
    assert oddspapi.items_of({"a": 1}) == [{"a": 1}]
    assert oddspapi.items_of(None) == []
    assert oddspapi.last_quote([{"p": 1}, {"p": 2}]) == {"p": 2}
    assert oddspapi.last_quote([]) is None


def test_find_ids_and_market_types():
    sports = [{"sportId": 13, "sportName": "Baseball"}, {"sportId": 99, "sportName": "American Football"}]
    assert oddspapi.find_ids(sports, "sportName", "sportId", "american") == [(99, "American Football")]
    mk = [{"marketType": "spreads"}, {"marketType": "spreads"}, {"marketType": "totals"}]
    assert oddspapi.market_types(mk) == {"spreads": 2, "totals": 1}


def test_book_markets_player_nested_and_flat():
    f = {"bookmakerOdds": {"pinnacle": {"markets": {
        "m1": {"outcomes": {"o1": {"players": {"0": {"priceAmerican": "-110", "active": True}}},
                            "o2": {"players": {"0": [{"priceAmerican": "-105"}, {"priceAmerican": "-108"}]}}}},
        "m2": {"outcomes": {"o3": {"priceAmerican": "+100"}}},
        "m3": {"outcomes": {}}}}}}
    out = oddspapi.book_markets(f, "pinnacle")
    assert out == {"m1": {"o1": {"priceAmerican": "-110", "active": True}, "o2": {"priceAmerican": "-108"}},
                   "m2": {"o3": {"priceAmerican": "+100"}}}
    assert oddspapi.book_markets(f, "fanduel") == {}


# --- NFL spread helpers ---
import datetime as dt

SMAP = {"m3": (-3.0, "h3", "a3"), "m35": (-3.5, "h35", "a35"), "m7": (-7.0, "h7", "a7")}
T = lambda s: dt.datetime.fromisoformat(s + "+00:00")


def _snap(ts, price, active=True):
    return {"createdAt": ts, "price": price, "active": active}


def _hist(**mk):
    return {"markets": {mid: {"outcomes": {o: {"players": {"0": snaps}} for o, snaps in outs.items()}}
                        for mid, outs in mk.items()}}


def test_main_spread_at_picks_most_balanced_line_as_of_t():
    h = _hist(m3={"h3": [_snap("2026-10-01T10:00:00Z", 1.70), _snap("2026-10-04T16:00:00Z", 1.95)],
                  "a3": [_snap("2026-10-01T10:00:00Z", 2.20), _snap("2026-10-04T16:00:00Z", 1.91)]},
              m35={"h35": [_snap("2026-10-01T10:00:00Z", 2.10)], "a35": [_snap("2026-10-01T10:00:00Z", 1.77)]},
              m7={"h7": [_snap("2026-10-01T10:00:00Z", 1.93)], "a7": [_snap("2026-10-01T10:00:00Z", 1.93, False)]})
    early = oddspapi.main_spread_at(h, SMAP, T("2026-10-02T00:00:00"))
    assert early["home_spread"] == -3.5 and early["n_lines"] == 2          # -7 is inactive on one side
    late = oddspapi.main_spread_at(h, SMAP, T("2026-10-04T17:00:00"))
    assert late["home_spread"] == -3.0 and late["home_price_decimal"] == 1.95
    assert late["first_seen"].startswith("2026-10-01T10:00")
    assert oddspapi.main_spread_at(h, SMAP, T("2026-09-30T00:00:00")) is None   # nothing posted yet


def test_main_spread_at_ignores_snapshots_after_t_and_high_hold():
    h = _hist(m3={"h3": [_snap("2026-10-01T10:00:00Z", 1.50)], "a3": [_snap("2026-10-01T10:00:00Z", 1.50)]})
    assert oddspapi.main_spread_at(h, SMAP, T("2026-10-02T00:00:00")) is None   # hold 33%
    h = _hist(m3={"h3": [_snap("2026-10-05T10:00:00Z", 1.91)], "a3": [_snap("2026-10-05T10:00:00Z", 1.91)]})
    assert oddspapi.main_spread_at(h, SMAP, T("2026-10-02T00:00:00")) is None


def test_main_spread_live_prefers_the_flagged_main_line():
    q = lambda p, main=False, active=True: {"price": p, "active": active, "mainLine": main,
                                            "changedAt": "2026-10-18T21:00:00Z", "limit": 5000.0}
    f = {"bookmakerOdds": {"pinnacle": {"markets": {
        "m3": {"outcomes": {"h3": {"players": {"0": q(1.92)}}, "a3": {"players": {"0": q(1.94)}}}},
        "m35": {"outcomes": {"h35": {"players": {"0": q(2.05, True)}}, "a35": {"players": {"0": q(1.83, True)}}}}}}}}
    r = oddspapi.main_spread_live(f, "pinnacle", SMAP)
    assert r["home_spread"] == -3.5 and r["main_flag"] and r["n_lines"] == 2 and r["limit"] == 5000.0
    f["bookmakerOdds"]["pinnacle"]["markets"]["m35"]["outcomes"]["h35"]["players"]["0"]["mainLine"] = False
    f["bookmakerOdds"]["pinnacle"]["markets"]["m35"]["outcomes"]["a35"]["players"]["0"]["mainLine"] = False
    assert oddspapi.main_spread_live(f, "pinnacle", SMAP)["home_spread"] == -3.0   # no flag: most balanced
