import datetime as dt
import json

import polars as pl

from engine.data import store
from engine.picks import final
from tests.conftest import FIX

EVENTS = json.loads((FIX / "parlay_nfl_spreads_trimmed.json").read_text())   # ATL@GB, GB -4.5..-5.5
TOTALS = json.loads((FIX / "parlay_nfl_totals_trimmed.json").read_text())
UTC = dt.timezone.utc
LOCK = dt.datetime(2026, 9, 25, 0, 0, tzinfo=UTC)   # ATL@GB kickoff 00:15Z


def _league(tmp_root, rows):
    p = tmp_root / "data" / "lines" / "league_lines.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("game_id,season,week,home_team,away_team,spread,favorite,source,recorded_at\n" + rows)


def test_decide_rules():
    assert final.decide(-6.5, -5.0, None)["pick"] == "away"          # market moved toward away
    assert final.decide(-4.5, -7.5, None)["pick"] == "home"
    d = final.decide(-2.5, -2.5, None)
    assert d["pick"] == "away" and d["pick_rule"] == "no_move_fallback_away"
    m = final.decide(None, -5.0, -6.5)
    assert m["data_status"] == "incomplete" and "LINE_FROM_CBS_ODDS_PAGE_OPEN" in m["flags"]
    n = final.decide(None, None, None)
    assert n["pick"] == "away" and n["missing_input"] == "league_line;market_at_lock"


def test_lock_run_writes_before_lock_once(tmp_root, week3_schedule):
    _league(tmp_root, "2026_03_ATL_GB,2026,3,GB,ATL,-6.5,GB,test,x\n")
    now = LOCK - dt.timedelta(minutes=20)
    out = final.run(week3_schedule, now=now, window_minutes=25, events=EVENTS)
    assert [r["game_id"] for r in out] == ["2026_03_ATL_GB"]
    r = out[0]
    # lock-time test: prediction written before kickoff - lock_buffer
    assert dt.datetime.fromisoformat(r["created_at"]) < dt.datetime.fromisoformat(r["lock_utc"])
    assert r["market_at_lock"] > r["league_line"]          # market -5ish vs league -6.5 -> moved to ATL
    assert r["pick_team"] == "ATL" and r["data_status"] == "complete"
    # second run in the same window: immutable, nothing new
    assert final.run(week3_schedule, now=now + dt.timedelta(minutes=5), events=EVENTS) == []
    assert len(store.read_rows(final.predictions_path())) == 1
    assert (tmp_root / "data" / "predictions" / "slate_2026_w03.md").exists()


def test_games_outside_window_untouched(tmp_root, week3_schedule):
    _league(tmp_root, "")
    out = final.run(week3_schedule, now=LOCK - dt.timedelta(hours=3), window_minutes=25, events=EVENTS)
    assert out == []


def test_manual_fallback_after_lock_is_flagged(tmp_root, week3_schedule):
    _league(tmp_root, "")
    out = final.run(week3_schedule, now=LOCK + dt.timedelta(minutes=5), events=EVENTS, game_id="2026_03_ATL_GB")
    assert len(out) == 1 and "LATE_AFTER_LOCK" in out[0]["flags"]
    assert out[0]["data_status"] == "incomplete"            # no league line recorded


def _with_history(sched):
    """Append 2000 synthetic past games: margin = -close + noise, so P(cover) is sensible."""
    import numpy as np
    rng = np.random.default_rng(1)
    n = 2000
    close = rng.choice(np.arange(-10, 10.5, 0.5), n)
    hist = pl.DataFrame({
        "game_id": [f"h{i}" for i in range(n)], "away_team": ["X"] * n, "home_team": ["Y"] * n,
        "gameday": ["2020-01-01"] * n, "gametime": ["13:00"] * n, "season": [2020] * n, "week": [1] * n,
        "game_type": ["REG"] * n,
        "kickoff_utc": [dt.datetime(2020, 1, 1, tzinfo=UTC)] * n, "lock_utc": [dt.datetime(2020, 1, 1, tzinfo=UTC)] * n,
        "result": np.round(-close + rng.normal(0, 13, n)).astype(int), "spread_line": -close,
        "total_line": rng.choice(np.arange(37, 55, 0.5), n),
    }).with_columns(pl.col("kickoff_utc").cast(sched["kickoff_utc"].dtype), pl.col("lock_utc").cast(sched["lock_utc"].dtype))
    cur = sched.with_columns(pl.lit(None, pl.Int64).alias("result"), pl.lit(None, pl.Float64).alias("spread_line"),
                             pl.lit(44.5).alias("total_line"))
    return pl.concat([cur, hist.select(cur.columns)], how="vertical_relaxed")


def test_probabilities_sum_to_one_and_pick_is_argmax(tmp_root, week3_schedule):
    _league(tmp_root, "2026_03_ATL_GB,2026,3,GB,ATL,-6.5,GB,test,x\n")
    sched = _with_history(week3_schedule)
    r = final.run(sched, now=LOCK - dt.timedelta(minutes=20), events=EVENTS, totals=TOTALS)[0]
    assert abs(r["p_home_cover"] + r["p_away_cover"] - 1) < 1e-3
    assert r["market_total"] != "" and r["market_total_books"] > 0 and "TOTAL_FROM_SCHEDULE" not in r["flags"]
    assert r["model_version"] == final.MODEL_VERSION and r["pick_rule"] == "argmax_cover_prob"
    # market ~ GB -5 vs league GB -6.5 -> GB less likely to cover -> ATL
    assert r["p_away_cover"] > 0.5 and r["pick_team"] == "ATL"
    assert "kickoff <" in r["training_period"]


def test_distribution_uses_only_games_before_now(week3_schedule):
    sched = _with_history(week3_schedule)
    md, period = final.fit_dist(sched, dt.datetime(2019, 1, 1, tzinfo=UTC))   # before all history
    assert md is None


def test_total_falls_back_to_schedule_then_shifted(tmp_root, week3_schedule):
    _league(tmp_root, "2026_03_ATL_GB,2026,3,GB,ATL,-6.5,GB,test,x\n")
    sched = _with_history(week3_schedule)
    r = final.run(sched, now=LOCK - dt.timedelta(minutes=20), events=EVENTS, totals=[])[0]
    assert "TOTAL_FROM_SCHEDULE" in r["flags"] and r["model_version"] == final.MODEL_VERSION
    no_tot = sched.drop("total_line")
    (tmp_root / "data" / "predictions" / "predictions.csv").unlink()
    r2 = final.run(no_tot, now=LOCK - dt.timedelta(minutes=20), events=EVENTS, totals=[])[0]
    assert "NO_TOTAL_SHIFTED_FALLBACK" in r2["flags"] and r2["model_version"] == "phase4-shifted-empirical-argmax"


def test_next_lock_finds_the_earliest_unpicked_lock_in_the_window():
    import datetime as dt
    import polars as pl
    from engine.picks import final
    t0 = dt.datetime(2026, 10, 4, 16, 0, tzinfo=dt.timezone.utc)
    s = pl.DataFrame({"game_id": ["a", "b", "c", "d"],
                      "lock_utc": [t0 + dt.timedelta(minutes=m) for m in (40, 45, 205, -5)]}) \
        .with_columns(pl.col("lock_utc").cast(pl.Datetime("us", "UTC")))
    lock, n = final.next_lock(s, t0, 240, set())
    assert lock == t0 + dt.timedelta(minutes=40) and n == 3          # d already locked; a, b, c due
    lock, n = final.next_lock(s, t0, 240, {"a"})
    assert lock == t0 + dt.timedelta(minutes=45) and n == 2
    assert final.next_lock(s, t0, 30, set()) == (None, 0)


def test_early_pick_flagged_and_on_time_pick_clean(tmp_root, week3_schedule):
    _league(tmp_root, "2026_03_ATL_GB,2026,3,GB,ATL,-6.5,GB,test,x\n")
    early = final.run(week3_schedule, now=LOCK - dt.timedelta(minutes=20), window_minutes=25, events=EVENTS)
    assert "EARLY_PICK" in early[0]["flags"]


def test_on_time_pick_has_no_timing_or_book_flag(tmp_root, week3_schedule):
    _league(tmp_root, "2026_03_ATL_GB,2026,3,GB,ATL,-6.5,GB,test,x\n")
    r = final.run(week3_schedule, now=LOCK - dt.timedelta(minutes=5), window_minutes=25, events=EVENTS)[0]
    assert "EARLY_PICK" not in r["flags"] and "LATE_AFTER_LOCK" not in r["flags"]
    assert ("FEW_BOOKS" in r["flags"]) == (r["market_books"] < final.MIN_BOOKS)


def _with_pinnacle(point):
    import copy
    ev = copy.deepcopy(EVENTS)
    evs = ev if isinstance(ev, list) else ev.get("data", ev)
    g = next(x for x in evs if x["home_team"] == "Green Bay Packers")
    b = copy.deepcopy(g["bookmakers"][0])
    b["key"] = "pinnacle"
    for m in b["markets"]:
        for o in m["outcomes"]:
            o["point"] = point if o["name"] == g["home_team"] else -point
    g["bookmakers"].append(b)
    return ev


def test_pinnacle_line_is_the_market_when_present(tmp_root, week3_schedule):
    _league(tmp_root, "2026_03_ATL_GB,2026,3,GB,ATL,-6.5,GB,test,x\n")
    r = final.run(week3_schedule, now=LOCK - dt.timedelta(minutes=5), window_minutes=25,
                  events=_with_pinnacle(-7.5))[0]
    assert r["market_at_lock"] == -7.5 and r["feature_version"] == "market:pinnacle"
    assert r["pick_team"] == "GB" and "MARKET_MEDIAN_FALLBACK" not in r["flags"]   # moved toward GB on Pinnacle


def test_median_fallback_is_flagged_without_pinnacle(tmp_root, week3_schedule):
    _league(tmp_root, "2026_03_ATL_GB,2026,3,GB,ATL,-6.5,GB,test,x\n")
    r = final.run(week3_schedule, now=LOCK - dt.timedelta(minutes=5), window_minutes=25, events=EVENTS)[0]
    assert r["feature_version"] == "market:median" and "MARKET_MEDIAN_FALLBACK" in r["flags"]
    assert r["pick_team"] == "ATL"                                                  # median ~-5: moved toward ATL


def test_failed_capture_uses_recent_capture_flagged_stale(tmp_root, week3_schedule):
    from engine.data import market
    _league(tmp_root, "2026_03_ATL_GB,2026,3,GB,ATL,-6.5,GB,test,x\n")
    market.capture(week3_schedule, now=LOCK - dt.timedelta(hours=2), events=EVENTS, all_games=True)
    r = final.run(week3_schedule, now=LOCK - dt.timedelta(minutes=5), window_minutes=25, events=[])[0]
    assert "STALE_MARKET" in r["flags"] and "NO_MARKET" not in r["flags"]
    assert r["market_at_lock"] is not None and r["pick_team"] == "ATL"            # same as the fresh-median pick


def test_capture_older_than_limit_is_not_used(tmp_root, week3_schedule):
    from engine.data import market
    _league(tmp_root, "2026_03_ATL_GB,2026,3,GB,ATL,-6.5,GB,test,x\n")
    market.capture(week3_schedule, now=LOCK - dt.timedelta(hours=7), events=EVENTS, all_games=True)
    r = final.run(week3_schedule, now=LOCK - dt.timedelta(minutes=5), window_minutes=25, events=[])[0]
    assert "NO_MARKET" in r["flags"] and "STALE_MARKET" not in r["flags"]


def test_fetch_error_reason_has_no_api_key():
    from engine.data import market
    msg = "HTTPError('502 Server Error: Bad Gateway for url: https://x.example/v1/odds?apiKey=abc123&markets=spreads')"
    out = market.redact(msg)
    assert "abc123" not in out and "apiKey=REDACTED&markets=spreads" in out
