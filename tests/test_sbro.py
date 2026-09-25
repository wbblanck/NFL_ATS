import polars as pl

from engine.data import sbro

HDR = "<tr><th>Date</th><th>Rot</th><th>VH</th><th>Team</th><th>1st</th><th>2nd</th><th>3rd</th><th>4th</th>" \
      "<th>Final</th><th>Open</th><th>Close</th><th>ML</th><th>2H</th></tr>"


def row(date, vh, team, final, opn, close):
    cells = [date, "1", vh, team, "0", "0", "0", "0", final, opn, close, "-110", "0"]
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


PAGE = "<table>" + HDR + "".join([
    # 2021-09-09 DAL @ TB: TB favored 7 open (H row), 10? close; totals on V row
    row("909", "V", "Dallas", "29", "52.5", "52.5"), row("909", "H", "TampaBay", "31", "7", "10"),
    # 2021-09-12 PIT @ BUF: BUF fav 7 (H row)
    row("912", "V", "Pittsburgh", "23", "51", "47.5"), row("912", "H", "Buffalo", "16", "7", "7"),
    # 2022-01-09 (Jan -> season+1) SEA @ ARI: away fav 6.5 on V row; close pk
    row("109", "V", "Seattle", "38", "6.5", "pk"), row("109", "H", "Arizona", "30", "48", "47"),
    # malformed: both small
    row("919", "V", "Kansas", "35", "3", "3"), row("919", "H", "Baltimore", "36", "4", "4"),
]) + "</table>"

SCHED = pl.DataFrame({
    "game_id": ["2021_01_DAL_TB", "2021_01_PIT_BUF", "2021_18_SEA_ARI", "2021_02_KC_BAL"],
    "season": [2021] * 4, "week": [1, 1, 18, 2], "game_type": ["REG"] * 4,
    "gameday": ["2021-09-09", "2021-09-12", "2022-01-09", "2021-09-19"],
    "home_team": ["TB", "BUF", "ARI", "BAL"], "away_team": ["DAL", "PIT", "SEA", "KC"],
    "home_score": [31, 16, 30, 36], "away_score": [29, 23, 38, 35], "spread_line": [8.5, 6.5, -6.5, -3.5],
})


def test_parse_and_orient():
    rows = sbro.parse_page(PAGE, 2021)
    assert rows[2]["date"] == "2022-01-09"          # January belongs to season + 1
    m = {r["game_id"]: r for r in sbro.match_schedule(pl.DataFrame(rows), SCHED).to_dicts() if r.get("game_id")}
    assert m["2021_01_DAL_TB"]["open_home_spread"] == -7.0 and m["2021_01_DAL_TB"]["close_home_spread"] == -10.0
    assert m["2021_01_PIT_BUF"]["open_home_spread"] == -7.0
    assert m["2021_18_SEA_ARI"]["open_home_spread"] == 6.5    # away favorite -> positive home spread
    assert m["2021_18_SEA_ARI"]["close_home_spread"] == 0.0   # pk
    bad = m["2021_02_KC_BAL"]
    assert bad["open_status"] == "ambiguous_spread_total" and bad["open_home_spread"] is None


def test_season_dependent_names():
    assert sbro.resolve("LosAngeles", 2016) == {"LA"}
    assert sbro.resolve("LosAngeles", 2019) == set()
    assert sbro.resolve("NewYork", 2013) == {"NYG", "NYJ"}
