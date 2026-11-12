"""One-off fetch of ESPN's timestamped spread and moneyline history, 2018-2022 regular season.

Source: ESPN core API, odds provider 1002 ("teamrankings"; the underlying book is not named).
Endpoint: /events/{id}/competitions/{id}/odds/1002/history/1/movement (history/1 = spread).
In each item, `line` is the AWAY team's spread and `lineDate` is UTC. We store the raw
movements and add home_spread = -line (engine sign: negative = home favored).

Research only: not used by the pick pipeline. Run by .github/workflows/fetch-espn-history.yml
because the development sandbox cannot reach ESPN.
"""
from __future__ import annotations

import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "raw" / "espn_history"
GAMES = OUT_DIR / "games_2018_2022.csv"
# history/1 = spread, history/0 = moneyline. A kind is skipped when its output already exists.
KINDS = {
    "spread": (1, OUT_DIR / "spread_movements_2018_2022.csv", OUT_DIR / "fetch_status_2018_2022.csv"),
    "moneyline": (0, OUT_DIR / "moneyline_movements_2018_2022.csv",
                  OUT_DIR / "fetch_status_moneyline_2018_2022.csv"),
}
URL = ("https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{e}"
       "/competitions/{e}/odds/1002/history/{h}/movement?limit=1000")


def fetch(espn_id: str, hist: int = 1) -> tuple[str, int | None, list[dict], str]:
    last_err = ""
    for attempt in range(4):
        try:
            r = requests.get(URL.format(e=espn_id, h=hist), timeout=30,
                             headers={"User-Agent": "nfl-ats-research"})
            if r.status_code == 200:
                d = r.json()
                items = d.get("items", [])
                if d.get("pageCount", 1) > 1:
                    last_err = f"more pages: {d.get('pageCount')}"
                return espn_id, d.get("count"), items, last_err
            last_err = f"http {r.status_code}"
        except (requests.RequestException, json.JSONDecodeError) as exc:
            last_err = type(exc).__name__
        time.sleep(2 ** attempt)
    return espn_id, None, [], last_err


def run(kind: str, by_id: dict) -> None:
    hist, out, status_path = KINDS[kind]
    if out.exists():
        print(f"{kind}: {out.name} exists, skipped")
        return
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda e: fetch(e, hist), by_id))
    rows, status = [], []
    for espn_id, count, items, err in results:
        g = by_id[espn_id]
        status.append({"game_id": g["game_id"], "espn": espn_id,
                       "count": "" if count is None else count, "error": err})
        for it in items:
            line = it.get("line")
            row = {"game_id": g["game_id"], "espn": espn_id, "line_date_utc": it.get("lineDate")}
            if kind == "spread":
                row["away_line"] = line
                row["home_spread"] = None if line is None else -float(line)
            row["away_odds"] = it.get("awayOdds")
            row["home_odds"] = it.get("homeOdds")
            rows.append(row)
    rows.sort(key=lambda r: (r["game_id"], r["line_date_utc"] or ""))
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with status_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(status[0]))
        w.writeheader()
        w.writerows(sorted(status, key=lambda s: s["game_id"]))
    failed = sum(1 for s in status if s["count"] == "")
    empty = sum(1 for s in status if s["count"] == 0)
    print(f"{kind}: games {len(status)}, movements {len(rows)}, failed {failed}, empty {empty}")


def main() -> int:
    with GAMES.open() as f:
        games = list(csv.DictReader(f))
    by_id = {str(int(float(g["espn"]))): g for g in games}
    for kind in KINDS:
        run(kind, by_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
