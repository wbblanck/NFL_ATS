---
name: oddspapi-api
description: How to call OddsPapi (api.oddspapi.io/v4) correctly from this repo - key handling, which endpoints cost requests, the live odds-by-tournaments and free historical-odds endpoints, response shapes, and what is still unverified for NFL spreads. Use before writing or running any code that fetches odds from OddsPapi, or when looking for a second source of Pinnacle lines.
---

# OddsPapi: what is verified, what is not

The verified facts come from wbblanck/kmodel (MLB pitcher strikeouts), which has called
OddsPapi from GitHub Actions since 2026-09 (`fetch_fd_lines.py`, `fetch_fd_timeline.py`,
`probe_oddspapi.py`, `probe_oddspapi_live.py`, `docs/project_reference.md` "Data access").
NFL details below come from one probe run (2026-10-18); add what later runs verify, citing the evidence.

Code: `src/engine/data/oddspapi.py` (client helpers, tests in `tests/test_oddspapi.py`),
`scripts/fetch/oddspapi_probe.py` + `.github/workflows/oddspapi-probe.yml` (discovery).

## Access and quota

- Base URL `https://api.oddspapi.io/v4`, key as the `apiKey` query parameter.
- Key: the repo's GitHub Actions secret is named `ODDS_PAPI`. Workflows pass it to the code as env
  `ODDSPAPI_API_KEY` (`env: ODDSPAPI_API_KEY: ${{ secrets.ODDS_PAPI }}`), the name kmodel uses.
  Never print, log or commit it, and never ask for the value; use `oddspapi.call`, which strips it
  from error text.
- Free plan: 250 requests a month. If this repo uses the same key as kmodel, the quota is shared:
  kmodel spends about 2 a day (slate + late slate) and had used 26 of 250 by 2026-10-18.
- Every data endpoint costs 1 request. `/account` is free (`subscriptions[].request_count`,
  `request_limit`); its body holds the owner's email, so keep only the counts
  (`oddspapi.request_count`). Log the count before and after each run.
- `/historical-odds` is free, with a 5 s cooldown (`pause=5.5`) and at most 3 bookmakers per call.
- Any workflow that uses the key is `workflow_dispatch` only (a push trigger spends requests on
  every edit). The sandbox cannot reach api.oddspapi.io; all calls run in GitHub Actions.
- Retry 429 and 5xx (up to 3 tries, 8 s apart); other HTTP errors return no data.

## Endpoints (verified on MLB)

| Endpoint | Cost | Notes |
|---|---|---|
| `/account` | free | request counts |
| `/sports`, `/tournaments` | 1 | ids (MLB: sport 13, tournament 109) |
| `/markets?sportId=` | 1 | every market id: `marketType`, `handicap`, `outcomes[outcomeId, outcomeName]`. Ids are stable: cache them in a committed file so later runs skip this call |
| `/fixtures?tournamentId=&from=&to=` | 1 | `from`/`to` as ISO UTC (`2026-06-10T00:00:00Z`); kmodel tries a 7-day range, then single days |
| `/odds-by-tournaments?bookmaker=<book>&tournamentIds=<id>` | 1 | every upcoming fixture (today's and later days) with that book's current markets, in one call. The live endpoint to use |
| `/odds?fixtureId=` | 1 | returned no bookmaker odds: do not use |
| `/historical-odds?fixtureId=&bookmakers=a,b,c` | free | timestamped snapshots, history from January 2026 only |

Response shape (odds-by-tournaments): fixture -> `bookmakerOdds` -> `<book>` -> `markets` ->
`<marketId>` -> `outcomes` -> `<outcomeId>` -> `players` -> `<playerId>` -> quote. A quote has
`priceAmerican` (a string), `price` (decimal), `changedAt` (ISO UTC), `active`. In historical-odds a
quote is a list of snapshots; `oddspapi.last_quote` takes the latest. Responses can be a list or
a dict with `data`; use `oddspapi.items_of`. Fixtures carry `startTime` (UTC; convert to
America/New_York for display).

## Traps kmodel hit

- Keep only `active` quotes. An active quote is live even when its price has not changed for hours.
- The live response includes later days' fixtures: filter by `startTime`, and drop started games.
- A book may post several lines (alternates). Use the most balanced two-sided quote, never a
  median across one book's lines. Drop quotes with hold > 10%.
- OddsPapi does not carry every book for every market: for MLB strikeouts it had FanDuel, Caesars,
  BetRivers, ESPN Bet, Hard Rock (BetMGM only from first pitch) and none for DraftKings, Pinnacle,
  Fanatics, bet365. Coverage for NFL spreads is a separate question (below).

## NFL: verified by the probe (2026-10-18, docs/evidence/probe/20261018T211124Z/)

- Ids: American Football is sport 14; the NFL is tournament 31 (233 is NFL Preseason).
- `/markets?sportId=14`: 4,751 market ids. Spreads are `marketType` "spreads", one market id per
  handicap and period (1,049 ids). The full game is `period` "result", `marketName`
  "Handicap (incl. overtime)" (281 ids). The others are halves and quarters (`p1`, `p1+p2`, ...):
  filter on `period == "result"` or a first-quarter line gets read as the game line.
- Side and sign: outcome "1" is participant1, which is the HOME team (15 of 15 week 6 fixtures vs our
  schedule; the London JAX v PHI game lists the designated home team first). `handicap` is the home
  team's line, so it already uses our canonical sign (negative = home favored). Check: WAS @ SF,
  Pinnacle full-game main line -7.5 on outcome "1" (-104 / -108); our Parlay capture of 2026-10-17
  had SF -7.5. Pinnacle's own `bookmakerOutcomeId` reads "-7.5/home" / "-7.5/away".
- Quotes for game lines also nest under `players` (as player props do), so
  `oddspapi.book_markets` works as written. Each quote has `mainLine`: Pinnacle flags one market
  per period, so the game line is the `period == "result"` market with `mainLine` true. Quotes also
  carry `limit` (Pinnacle's stake limit) and `bookmakerChangedAt`.
- Live fixtures (`odds-by-tournaments`) carry `participant1Id` / `participant2Id` but no team names
  (`participant1Name` was null). `/fixtures` has the names: map ids to teams from it (1 request) and
  then through `engine.teams.to_canonical`, which handled all 30 names in week 6.
- Coverage live, Sunday 2026-10-18 at 21:11 UTC: DraftKings and FanDuel had spreads for 16 fixtures,
  Pinnacle for only 2 (that night's SNF and Monday's MNF). Why Pinnacle listed so few is not known
  (a guess: it only shows games close to kickoff in this feed). Check before counting on it at lock.
- History: `/historical-odds` for JAX v PHI (2026-10-11) had Pinnacle 79 spread markets / 16,410
  snapshots, DraftKings 150 / 96,217, FanDuel 124 / 58,435. One game's response is over 3 MB, which
  is where the probe's saved copy was cut off: parse in memory, save only what you need.
- Cost: the probe used 7 requests (26 -> 33 of 250 this month, on the key shared with kmodel).

## Still unverified

- Pinnacle's live coverage at the lock times we pick at (5 minutes before lock).
- How far back Pinnacle NFL history goes (the docs say January 2026; only week 6 was checked).

## Before OddsPapi feeds a pick

The market input is Pinnacle from the Parlay API capture (docs/market_input.md). Replacing or
backing it up with OddsPapi changes the pick input: write it up like that decision (evidence,
fallback, what is recorded per pick), get the owner's go-ahead, keep it off `main` until they
say "merge", and keep `feature_version` / flags distinct so captures from the two sources are
never mixed silently.
