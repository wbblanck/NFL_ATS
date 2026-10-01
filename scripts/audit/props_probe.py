"""Probe: which historical NFL player-prop lines does Action Network's keyless API hold?

Read-only evidence for the player-prop question (no model, no outcomes).
Run 1 (20261001T033151Z) showed the v2 NFL scoreboard ignores `date`: every date
returned the same game. This run tries several scoreboard parameter forms per
target Sunday, records each returned game's start time, and summarizes the props
of the first game that is really on the target date (markets, players, books).

Writes docs/evidence/props/<UTC stamp>/summary.json. Runs on a hosted runner
(the sandbox cannot reach Action Network).
"""
from __future__ import annotations

import datetime as dt
import json
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

AN = "https://api.actionnetwork.com"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def get(url: str, tries: int = 3):
    headers = {"User-Agent": UA, "Accept": "application/json",
               "Referer": "https://www.actionnetwork.com/", "Origin": "https://www.actionnetwork.com"}
    last = None
    for i in range(tries):
        time.sleep(1.0 + (2 ** i if i else 0))
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
                return r.status, json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            last = e.code
            if e.code == 404:
                break
        except Exception as e:  # noqa: BLE001 - evidence probe, record and continue
            last = str(e)
    return last, None


SCOREBOARD_VARIANTS = [
    "web/v2/scoreboard/nfl?date={date}&periods=event",
    "web/v2/scoreboard/nfl?season={season}&week={week}&periods=event",
    "web/v2/scoreboard/nfl?season={season}&week={week}&seasonType=reg&periods=event",
    "web/v1/scoreboard/nfl?season={season}&week={week}",
    "web/v1/scoreboard/nfl?date={date}",
]
# (date, season, week): mid-October Sundays, plus 2026 week 3
TARGETS = [("20211017", 2021, 6), ("20231015", 2023, 6), ("20251012", 2025, 6), ("20260927", 2026, 3)]


def game_brief(g: dict) -> dict:
    teams = {t.get("id"): t.get("abbr") or t.get("display_name") for t in (g.get("teams") or []) if isinstance(t, dict)}
    return {"id": g.get("id"), "start_time": g.get("start_time"), "season": g.get("season"), "week": g.get("week"),
            "home": teams.get(g.get("home_team_id")), "away": teams.get(g.get("away_team_id"))}


def main() -> None:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path("docs/evidence/props") / stamp
    out.mkdir(parents=True, exist_ok=True)
    _, bd = get(AN + "/web/v1/books")
    books = {str(b.get("id")): b.get("display_name") or b.get("name") or ""
             for b in ((bd or {}).get("books") or [])}
    summary = {"stamp": stamp, "scoreboards": {}, "props": {}}
    for date, season, week in TARGETS:
        for v in SCOREBOARD_VARIANTS:
            url = v.format(date=date, season=season, week=week)
            st, sb = get(f"{AN}/{url}")
            games = (sb or {}).get("games") or []
            briefs = [game_brief(g) for g in games]
            summary["scoreboards"][url] = {"status": st, "games": len(games), "first": briefs[:3],
                                           "top_keys": sorted((sb or {}).keys())[:20]}
            print(f"{url}: {st}, {len(games)} games, first {briefs[:2]}", flush=True)
            # props for the first game whose start date matches the target date
            hit = next((b for b in briefs if (b["start_time"] or "")[:10].replace("-", "") == date), None)
            key = f"{date}"
            if hit and key not in summary["props"]:
                pst, props = get(f"{AN}/web/v2/games/{hit['id']}/props")
                pp = (props or {}).get("player_props") or {}
                mk = {}
                for market, entries in pp.items():
                    per = defaultdict(set)
                    bk = Counter()
                    for e in entries:
                        for book, lines in (e.get("lines") or {}).items():
                            for ln in lines:
                                bk[books.get(str(book), str(book))] += 1
                                per[(ln.get("player_id"), str(book))].add(ln.get("value"))
                    mk[market] = {"players": len({p for p, _ in per}), "books": sorted(bk)}
                summary["props"][key] = {"game": hit, "status": pst, "n_markets": len(mk), "markets": mk}
                print(f"  props {date} game {hit}: {pst}, {len(mk)} markets", flush=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
