"""Dashboard live-scores strip (streamlit_app/live.py): display only, graded nowhere."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "streamlit_app"))
import live  # noqa: E402

BOARD = json.loads((ROOT / "docs/evidence/probe/20260930T034922Z/espn_site_web_scoreboard.json").read_text())


def _in_progress(board, home, away, hs, as_, detail="6:42 - 3rd", possession=None):
    b = copy.deepcopy(board)
    for e in b["events"]:
        comp = e["competitions"][0]
        abbrs = {c["homeAway"]: c["team"]["abbreviation"] for c in comp["competitors"]}
        if abbrs == {"home": home, "away": away}:
            e["status"]["type"].update(state="in", name="STATUS_IN_PROGRESS", shortDetail=detail, completed=False)
            for c in comp["competitors"]:
                c["score"] = str(hs if c["homeAway"] == "home" else as_)
            if possession:
                pid = next(c["team"]["id"] for c in comp["competitors"] if c["homeAway"] == possession)
                comp["situation"] = {"possession": pid, "shortDownDistanceText": "3rd & 4", "isRedZone": True}
            return b
    raise AssertionError("game not in the saved board")


def test_finished_games_show_no_strip():
    assert live.live_games(BOARD) == []                      # the saved board is all finals
    assert live.render(live.cards([], {})) == ""
    assert live.inject("<header>x</header><p>", "") == "<header>x</header><p>"


def test_cover_margin_against_the_pool_line():
    # pool line GB -1.5 (home spread); DAL 17 - GB 13: DAL +1.5 covers by 5.5, GB -1.5 needs 5.5
    assert live.cover_margin("DAL", "GB", 13, 17, -1.5) == 5.5
    assert live.cover_margin("GB", "GB", 13, 17, -1.5) == -5.5
    assert live.cover_margin("GB", "GB", 16, 14, -2.0) == 0.0  # push


def test_live_game_card_with_pick_and_differing_hybrid():
    b = _in_progress(BOARD, "GB", "ATL", 13, 17, possession="away")
    games = live.live_games(b)
    assert len(games) == 1 and games[0]["home"]["code"] == "GB" and games[0]["possession"] == "away"
    picks = {("GB", "ATL"): {"pick_team": "ATL", "hybrid_team": "GB", "league_line": "-2.5"}}
    (c,) = live.cards(games, picks)
    assert [(p["who"], p["team"], p["line"], p["cls"]) for p in c["pick"]] == \
        [("Pick", "ATL", "+2.5", "cov"), ("Hybrid", "GB", "-2.5", "miss")]
    page = live.inject("<div><header>h</header><section>rest</section></div>", live.render([c]))
    assert page.index("Live now") > page.index("</header>") and "Covering by 6.5" in page and "Needs 6.5" in page
    assert "Red zone" in page and "3rd &amp; 4" in page


def test_espn_wsh_maps_and_no_pick_is_shown_plainly():
    b = _in_progress(BOARD, *next(([c["team"]["abbreviation"] for c in sorted(e["competitions"][0]["competitors"],
                                    key=lambda c: c["homeAway"] != "home")] for e in BOARD["events"]
                                   if "WSH" in json.dumps(e["competitions"][0]["competitors"]))), 7, 7)
    (g,) = live.live_games(b)
    assert "WAS" in (g["home"]["code"], g["away"]["code"])
    (c,) = live.cards([g], {})
    assert c["pick"] is None and "No pick recorded" in live.render([c])


def test_hybrid_matches_the_tracked_rule_on_real_rows():
    picks = live.load_picks()
    p = picks[("JAX", "HOU")]                                 # 2026-10-18: live HOU, hybrid took v1's JAX
    assert p["pick_team"] == "HOU" and p["hybrid_team"] == "JAX" and p["hybrid_source"] == "v1"


def test_page_data_carries_live_and_final_games_and_fills_the_placeholder():
    b = _in_progress(BOARD, "GB", "ATL", 10, 14)
    d = live.page_data(b)
    by = {(g["away"], g["home"]): g for g in d["games"]}
    assert by[("ATL", "GB")] | {"detail": None} == {"home": "GB", "away": "ATL", "hs": 10, "as": 14, "state": "in",
                                                    "detail": None, "halftime": False}
    assert {g["state"] for g in d["games"]} == {"in", "post"}      # the rest of the saved board is final
    page = '<script id="live-data" type="application/json">{}</script>'
    out = live.inject_data(page, d)
    assert '"state":"in"' in out and out.startswith('<script id="live-data"')
    assert live.inject_data("<p>no placeholder</p>", d) == "<p>no placeholder</p>"
