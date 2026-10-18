"""What does OddsPapi give us for NFL spreads? One-off discovery probe (oddspapi-probe.yml).

Questions, each answered in summary.md:
  1. American-football sport id and NFL tournament id.
  2. Spread market ids: marketType name, handicap, outcome names (whose side the handicap is).
  3. Live: do Pinnacle, DraftKings and FanDuel carry NFL spreads right now (odds-by-tournaments)?
  4. History: does /historical-odds hold timestamped Pinnacle spreads for a finished 2026 game?

Metered requests: about 7 of the plan's monthly 250 (sports, tournaments, markets, 3 x
odds-by-tournaments, fixtures); /account and /historical-odds are free. The key is shared with
kmodel's daily runs if the same key is used, so the count before and after is logged.

The key comes only from env ODDSPAPI_API_KEY and is never printed; the /account body is reduced to
its request counts (it holds the owner's email). Saves under docs/evidence/probe/<stamp>/oddspapi_*.
"""
import datetime as dt
import json
import sys
from pathlib import Path

from engine.data import oddspapi as op

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "evidence" / "probe" / dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
BOOKS = ["pinnacle", "draftkings", "fanduel"]
LOG: list[str] = []


def log(s=""):
    print(s)
    LOG.append(s)


def save(name, obj, limit=3_000_000):
    (OUT / f"oddspapi_{name}.json").write_text(json.dumps(obj, indent=1)[:limit])


def first_id(rows, name_field, id_field, *needles):
    hits = op.find_ids(rows, name_field, id_field, *needles)
    log(f"  {name_field} matching {needles}: {hits[:10]}")
    return hits[0][0] if hits else None


def main():
    try:
        before = op.request_count()
    except op.MissingKey:
        print("ODDSPAPI_API_KEY is not set: the workflow passes it from the repository secret ODDS_PAPI.")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    log(f"# OddsPapi NFL probe {OUT.name}\n\nrequests before: {before[0]} of {before[1]}")

    s, sports = op.call("sports")
    log(f"\n## 1. ids\nsports -> HTTP {s}, {len(op.items_of(sports))} rows")
    save("sports", sports)
    sport = first_id(op.items_of(sports), "sportName", "sportId", "american") or \
        first_id(op.items_of(sports), "sportName", "sportId", "football")
    if sport is None:
        return finish(before, "no American-football sport id found")

    s, tours = op.call("tournaments", sportId=sport)
    log(f"tournaments?sportId={sport} -> HTTP {s}, {len(op.items_of(tours))} rows")
    save("tournaments", tours)
    nfl = first_id(op.items_of(tours), "tournamentName", "tournamentId", "nfl")
    if nfl is None:
        return finish(before, "no NFL tournament id found")

    s, mk = op.call("markets", sportId=sport)
    mk = op.items_of(mk)
    log(f"\n## 2. markets\nmarkets?sportId={sport} -> HTTP {s}, {len(mk)} market ids")
    log(f"marketTypes: {op.market_types(mk)}")
    spreadish = [m for m in mk if any(w in str(m.get("marketType", "")).lower() for w in ("spread", "handicap"))]
    save("markets_spreadish", spreadish)
    for m in spreadish[:12]:
        log(f"  id {m.get('marketId')} {m.get('marketType')} {m.get('marketName')!r} handicap {m.get('handicap')} "
            f"period {m.get('period')} outcomes {[(o.get('outcomeId'), o.get('outcomeName')) for o in m.get('outcomes') or []]}")
    spread_ids = {str(m.get("marketId")) for m in spreadish}

    log("\n## 3. live odds (odds-by-tournaments)")
    sample, keys = None, None
    for book in BOOKS:
        s, resp = op.call("odds-by-tournaments", bookmaker=book, tournamentIds=nfl)
        fx = op.items_of(resp)
        save(f"live_{book}", resp)
        with_spread = 0
        if fx and keys is None:
            keys = sorted(fx[0].keys())
        for f in fx:
            bm = op.book_markets(f, book)
            hit = [mid for mid in bm if mid in spread_ids]
            if hit:
                with_spread += 1
                if sample is None:
                    sample = (book, f.get("fixtureId"), f.get("participant1Name"), f.get("participant2Name"),
                              {mid: bm[mid] for mid in hit[:3]})
        log(f"{book}: HTTP {s}, {len(fx)} fixtures, {with_spread} with a spread market")
    log(f"sample spread quotes: {json.dumps(sample)[:1500] if sample else 'none'}")
    log(f"fixture keys (first live fixture): {keys}")

    log("\n## 4. history (historical-odds, free)")
    today = dt.datetime.now(dt.timezone.utc).date()
    s, fx = op.call("fixtures", tournamentId=nfl, **{"from": f"{today - dt.timedelta(days=8)}T00:00:00Z",
                                                      "to": f"{today - dt.timedelta(days=1)}T12:00:00Z"})
    fx = op.items_of(fx)
    save("fixtures_last_week", fx)
    log(f"fixtures last 8 days -> HTTP {s}, {len(fx)} rows")
    if fx:
        f = fx[0]
        log(f"  using fixture {f.get('fixtureId')} {f.get('participant1Name')} v {f.get('participant2Name')} "
            f"start {f.get('startTime')}")
        s, hist = op.call("historical-odds", pause=5.5, fixtureId=f.get("fixtureId"), bookmakers=",".join(BOOKS))
        save("historical_sample", hist)
        for book, bd in ((hist or {}).get("bookmakers") or {}).items():
            mkts = bd.get("markets") or {}
            sp = [mid for mid in mkts if mid in spread_ids]
            n_snaps = 0
            for mid in sp:
                for od in (mkts[mid].get("outcomes") or {}).values():
                    for snaps in ((od or {}).get("players") or {"_": od}).values():
                        n_snaps += len(snaps) if isinstance(snaps, list) else 1
            log(f"  {book}: {len(mkts)} markets, {len(sp)} spread markets, {n_snaps} spread snapshots")
    return finish(before, "done")


def finish(before, msg):
    after = op.request_count()
    used = (after[0] - before[0]) if None not in (after[0], before[0]) else "?"
    log(f"\n{msg}. requests after: {after[0]} of {after[1]} (this probe {used})")
    (OUT / "oddspapi_summary.md").write_text("\n".join(LOG) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
