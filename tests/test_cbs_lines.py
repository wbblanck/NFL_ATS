import datetime as dt

from engine.data import cbs_lines, store
from tests.conftest import FIX

HTML = (FIX / "cbs_odds_week3_2026_trimmed.html").read_text()


def test_parse_fixture():
    g = {x.cbs_abbrev: x for x in cbs_lines.parse_odds_page(HTML)}
    assert set(g) == {"NFL_20260924_ATL@GB", "NFL_20260927_NE@JAC", "NFL_20260927_CAR@CLE",
                      "NFL_20260927_KC@MIA", "NFL_20260927_LAR@DEN"}
    atl = g["NFL_20260924_ATL@GB"]
    assert atl.open_home == "-6.5 -112" and atl.open_away == "o46.5 -108"
    assert atl.current_home_spread == -4.5


def test_opening_spread_orientation(week3_schedule):
    rows = {r["game_id"]: r for r in cbs_lines.match_games(cbs_lines.parse_odds_page(HTML), week3_schedule)}
    assert rows["2026_03_ATL_GB"]["spread"] == -6.5 and rows["2026_03_ATL_GB"]["favorite"] == "GB"
    # CLE row shows +2.5 -> home dog -> canonical +2.5, CAR favored
    assert rows["2026_03_CAR_CLE"]["spread"] == 2.5 and rows["2026_03_CAR_CLE"]["favorite"] == "CAR"
    assert rows["2026_03_KC_MIA"]["spread"] == 11.5 and rows["2026_03_KC_MIA"]["favorite"] == "KC"
    # JAC alias -> JAX; LAR alias -> LA
    assert rows["2026_03_NE_JAX"]["home_team"] == "JAX"
    assert rows["2026_03_LA_DEN"]["away_team"] == "LA"


def test_whole_number_open_is_rejected_not_graded(week3_schedule):
    rows = {r["game_id"]: r for r in cbs_lines.match_games(cbs_lines.parse_odds_page(HTML), week3_schedule)}
    r = rows["2026_03_NE_JAX"]
    assert r["spread"] == -3.0
    assert r["status"] == "rejected" and "manual review" in r["reason"]
    assert all(rows[g]["status"] == "ok" for g in rows if g != "2026_03_NE_JAX")


def test_capture_is_append_only_and_freeze_keeps_first(tmp_root, week3_schedule):
    t0 = dt.datetime(2026, 9, 22, 12, tzinfo=dt.timezone.utc)
    cbs_lines.capture(week3_schedule, now=t0, urls=["fixture://a"], fetcher=lambda u: HTML)
    p = tmp_root / "data" / "lines" / "cbs_open_captures.csv"
    first = p.read_text()
    moved = HTML.replace("-6.5\n", "-7.5\n", 1)
    assert moved != HTML
    cbs_lines.capture(week3_schedule, now=t0 + dt.timedelta(hours=6), urls=["fixture://a"], fetcher=lambda u: moved)
    assert p.read_text().startswith(first)            # earlier rows untouched
    assert len(store.read_rows(p)) == 10
    frozen = {r["game_id"]: r for r in cbs_lines.freeze()}
    assert "2026_03_NE_JAX" not in frozen             # rejected lines never frozen
    assert frozen["2026_03_ATL_GB"]["spread"] == "-6.5"
    assert frozen["2026_03_ATL_GB"]["later_changes"] == "-7.5"
    flags = store.read_rows(tmp_root / "data" / "lines" / "cbs_open_flags.csv")
    assert len(flags) == 1 and flags[0]["game_id"] == "2026_03_NE_JAX"   # deduplicated


def test_fetch_error_is_recorded(tmp_root, week3_schedule):
    def boom(u):
        raise ConnectionError("blocked")
    rows = cbs_lines.capture(week3_schedule, urls=["x"], fetcher=boom)
    assert rows[0]["status"] == "fetch_error"
