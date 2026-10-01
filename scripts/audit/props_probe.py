"""Probe: which historical NFL player-prop lines does Action Network's keyless API hold?

Read-only evidence for the player-prop question (no model, no outcomes). For one
Sunday per season (2021-2026) it lists every player-prop market on up to
GAMES_PER_DATE games: entries, players, books, lines per (player, book), and one
raw line record, so the field layout (timestamps or not) can be checked.

Writes docs/evidence/props/<UTC stamp>/summary.json and one raw props response per
date. Runs on a hosted runner (the sandbox cannot reach Action Network).
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
# One mid-October Sunday per season, plus this season's week 3 and week 4 Sundays.
DATES = ["20211017", "20221016", "20231015", "20241013", "20251012", "20260927", "20260928"]
GAMES_PER_DATE = 4


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


def main() -> None:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path("docs/evidence/props") / stamp
    out.mkdir(parents=True, exist_ok=True)
    _, bd = get(AN + "/web/v1/books")
    books = {str(b.get("id")): b.get("display_name") or b.get("name") or ""
             for b in ((bd or {}).get("books") or [])}
    summary = {"stamp": stamp, "books_listed": len(books), "dates": {}}
    for ds in DATES:
        st, sb = get(f"{AN}/web/v2/scoreboard/nfl?date={ds}&periods=event")
        games = (sb or {}).get("games") or []
        rec = {"scoreboard_status": st, "games": len(games), "probed": []}
        for g in games[:GAMES_PER_DATE]:
            pst, props = get(f"{AN}/web/v2/games/{g['id']}/props")
            grec = {"an_game_id": g["id"], "status": pst, "markets": {}}
            if props is not None and not rec["probed"]:
                (out / f"props_{ds}_{g['id']}.json").write_text(json.dumps(props)[:2_000_000])
            pp = (props or {}).get("player_props") or {}
            for market, entries in pp.items():
                per = defaultdict(set)
                bk = Counter()
                sample = None
                for e in entries:
                    for book, lines in (e.get("lines") or {}).items():
                        for ln in lines:
                            bk[books.get(str(book), str(book))] += 1
                            per[(ln.get("player_id"), str(book))].add(ln.get("value"))
                            sample = sample or ln
                grec["markets"][market] = {
                    "entries": len(entries),
                    "players": len({p for p, _ in per}),
                    "books": dict(bk.most_common()),
                    "max_lines_per_player_book": max((len(v) for v in per.values()), default=0),
                    "sample_line_record": sample}
            rec["probed"].append(grec)
        summary["dates"][ds] = rec
        mk = sorted({m for gr in rec["probed"] for m in gr["markets"]})
        print(f"{ds}: scoreboard {st}, games {len(games)}, markets {len(mk)}: {mk}", flush=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
