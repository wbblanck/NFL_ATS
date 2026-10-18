---
name: oddspapi-api
description: How to call OddsPapi (api.oddspapi.io/v4) correctly from this repo - key handling, which endpoints cost requests, the live odds-by-tournaments and free historical-odds endpoints, response shapes, and what is still unverified for NFL spreads. Use before writing or running any code that fetches odds from OddsPapi, or when looking for a second source of Pinnacle lines.
---

# OddsPapi: what is verified, what is not

The verified facts come from wbblanck/kmodel (MLB pitcher strikeouts), which has called
OddsPapi from GitHub Actions since 2026-09 (`fetch_fd_lines.py`, `fetch_fd_timeline.py`,
`probe_oddspapi.py`, `probe_oddspapi_live.py`, `docs/project_reference.md` "Data access").
Nothing has been verified for the NFL yet. Run the probe (below) before relying on any NFL detail,
then move what it shows from "Unverified" to "Verified" here, citing the evidence folder.

Code: `src/engine/data/oddspapi.py` (client helpers, tests in `tests/test_oddspapi.py`),
`scripts/fetch/oddspapi_probe.py` + `.github/workflows/oddspapi-probe.yml` (discovery).

## Access and quota

- Base URL `https://api.oddspapi.io/v4`, key as the `apiKey` query parameter.
- Key: env `ODDSPAPI_API_KEY`, a GitHub Actions secret. Never print, log or commit it; use
  `oddspapi.call`, which strips it from error text. The owner adds the secret to this repo
  (Settings > Secrets and variables > Actions); never ask for the value.
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

## Unverified for the NFL (the probe answers these)

- American-football sport id and NFL tournament id.
- The spread `marketType` name, and whose side `handicap` is (home or away, sign). This repo's
  canonical sign is negative = home favored (CLAUDE.md); map to it and test on a known game before
  any use.
- Whether game-line outcomes nest under `players` like props do (`oddspapi.book_markets` handles
  both, unconfirmed).
- Which of Pinnacle, DraftKings and FanDuel carry NFL spreads live and in `/historical-odds`.
- How fixture team names are spelled (`engine.teams.to_canonical` must map them).

## Before OddsPapi feeds a pick

The market input is Pinnacle from the Parlay API capture (docs/market_input.md). Replacing or
backing it up with OddsPapi changes the pick input: write it up like that decision (evidence,
fallback, what is recorded per pick), get the owner's go-ahead, keep it off `main` until they
say "merge", and keep `feature_version` / flags distinct so captures from the two sources are
never mixed silently.
