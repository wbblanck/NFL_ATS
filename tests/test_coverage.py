import datetime as dt

import polars as pl

from engine.picks import coverage as C

UTC = dt.timezone.utc


def _p(gid, week=4, flags="", mtl="5.0", fv="market:pinnacle"):
    return {"prediction_id": "id-" + gid, "game_id": gid, "season": "2026", "week": str(week), "flags": flags,
            "minutes_to_lock": mtl, "feature_version": fv, "supersedes": ""}


def test_classify_one_class_per_pick():
    assert C.classify(_p("a")) == C.LIVE_MARKET
    assert C.classify(_p("a", fv="market:median", flags="MARKET_MEDIAN_FALLBACK")) == C.LIVE_MEDIAN
    assert C.classify(_p("a", fv="none")) == C.LIVE_MEDIAN                 # week 3-4 median input, unlabelled
    assert C.classify(_p("a", mtl="43.5")) == C.STALE_MARKET
    assert C.classify(_p("a", mtl="-2", flags="LATE_AFTER_LOCK")) == C.LATE_PICK
    assert C.classify(_p("a", fv="none", flags="NO_MARKET;TOTAL_FROM_SCHEDULE", mtl="50")) == C.BLIND_FALLBACK
    assert C.classify(_p("a", flags="NO_LEAGUE_LINE;LEAGUE_LINE_CONFLICT")) == C.INVALID_INPUT


def test_recurring_jobs_cover_the_usual_slots_only():
    et = C.ET
    cov = lambda y, m, d, h, mi: C.covered_by_recurring_job(dt.datetime(y, m, d, h, mi, tzinfo=et).astimezone(UTC))
    assert cov(2026, 11, 29, 13, 0) and cov(2026, 11, 29, 16, 25) and cov(2026, 11, 29, 20, 20)   # Sunday slots
    assert cov(2026, 11, 26, 20, 20)                     # Thursday night (Thanksgiving) is the Thursday job
    assert cov(2026, 11, 30, 20, 15)                     # Monday night
    assert not cov(2026, 11, 26, 16, 30)                 # Thanksgiving afternoon
    assert not cov(2026, 11, 27, 15, 0)                  # Friday
    assert not cov(2026, 12, 19, 17, 0)                  # Saturday
    assert cov(2026, 11, 29, 9, 30)                      # international 9:30 AM slot
    assert not cov(2026, 11, 29, 11, 0)                  # an international game at another time


def test_report_counts_missing_and_upcoming():
    k = lambda d, h: dt.datetime(2026, 11, d, h, 0, tzinfo=UTC)
    sched = pl.DataFrame({"game_id": ["g1", "g2", "g3", "g4", "g0"], "season": [2026] * 5, "week": [4, 4, 4, 4, 2],
                          "kickoff_utc": [k(22, 18), k(22, 18), k(26, 21) + dt.timedelta(minutes=30), k(29, 18), k(1, 18)]})
    now = k(25, 12)
    rep = C.report(sched, [_p("g1")], now, season=2026)
    assert rep["counts"][C.LIVE_MARKET] == 1 and rep["counts"][C.MISSING_PICK] == 1     # g0 predates week 4
    assert rep["locked_games"] == 2 and rep["prediction_rows"] == 1
    assert [u["game_id"] for u in rep["needs_one_off_job"]] == ["g3"]                  # Thu 4:30 PM ET; g4 is Sun 1 PM
    txt = C.alert_text(rep, now, since_hours=96)
    assert "NO PICK (lock passed): g2" in txt and "NEEDS ONE-OFF JOB: g3" in txt
    assert C.alert_text({"rows": [], "needs_one_off_job": []}, now) == ""
