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


SCOREBOARD_VARIANTS = ["web/v2/scoreboard/nfl?season={season}&week={week}&periods=event"]
# Run 2 (20261001T033953Z): season/week works; props on 2025 wk 6 and 2026 wk 3, none on 2021/2023 wk 6.
# Run 3 bounds the start: (label, season, week); props are summarized for the first 2 games of each.
TARGETS = [("2022w06", 2022, 6), ("2023w15", 2023, 15), ("2024w01", 2024, 1), ("2024w06", 2024, 6),
           ("2024w15", 2024, 15), ("2025w01", 2025, 1)]
GAMES = 2


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
    for label, season, week in TARGETS:
        for v in SCOREBOARD_VARIANTS:
            url = v.format(season=season, week=week)
            st, sb = get(f"{AN}/{url}")
            games = (sb or {}).get("games") or []
            briefs = [game_brief(g) for g in games]
            summary["scoreboards"][url] = {"status": st, "games": len(games), "first": briefs[:3],
                                           "top_keys": sorted((sb or {}).keys())[:20]}
            print(f"{url}: {st}, {len(games)} games, first {briefs[:2]}", flush=True)
            for hit in briefs[:GAMES]:
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
                summary["props"][f"{label}_{hit['id']}"] = {"game": hit, "status": pst, "n_markets": len(mk),
                                                           "markets": mk}
                print(f"  props {label} game {hit}: {pst}, {len(mk)} markets", flush=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
