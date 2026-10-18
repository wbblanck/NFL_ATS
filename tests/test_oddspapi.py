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
