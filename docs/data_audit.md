# Phase 0 — Data Audit

Audit date: **2026-09-24** (2026 season, week 3). Every claim below cites an
evidence file in `docs/evidence/` or a live call made on that date. Anything
not verified that way is marked **UNVERIFIED**.

## How the evidence was gathered

The development sandbox's network policy allowed only GitHub and package
registries. CBS, ESPN, the odds APIs and the weather APIs were all refused.
So there were two ways to collect evidence:

| Method | What | Evidence |
|---|---|---|
| Local, via `nflreadpy` 0.1.5 (reads nflverse GitHub releases) | nflverse datasets | `scripts/audit/nflverse_audit.py` → `evidence/nflverse_audit.json`; `scripts/audit/spread_proxy_audit.py` → `evidence/spread_proxy_whole_numbers.csv` |
| GitHub-hosted runner (open internet) | CBS, Parlay API, The Odds API, ESPN, SBRO, AusSportsBetting, Open-Meteo, NWS, nflverse release metadata | `scripts/audit/network_probe.py` → `evidence/probe/20260924T194249Z/` (round 1) and `evidence/probe/20260924T233924Z/` (round 2: historical CBS pages, CBS Pick'em rules, SBRO season page, nfl.com injuries). Each holds raw responses plus `summary.json`. |
| GitHub Actions API | Scheduled-workflow start delays | `evidence/gha_schedule_runs.json`, `scripts/audit/gha_schedule_latency.py` |

Round 2 ran from this repository, which has no `PARLAY_API_KEY` secret yet,
so the Parlay calls were skipped in round 2. The Parlay evidence is from
round 1. Parsed CBS history: `scripts/audit/cbs_history_audit.py` →
`evidence/cbs_history_open_column.csv`.

---

## Summary: status of each downstream dependency

| Dependency | Phase | Status |
|---|---|---|
| Live CBS opening line | 1+ | **Available**. CBS odds page "Open" column, parsed and archived. Whether it equals the *league* line is **UNVERIFIED**; see 0.3. |
| Historical CBS opening lines | 2, 3, 7 | **Partial.** CBS week pages keep the odds-page "Open" column for **2025–2026** (checked: 2025 wk1 and wk10, 2026 wk1–2). **Not** for 2022 or 2018. 2023–2024 were not checked. Openers are 13–50% whole numbers per week, so they are not league lines (0.3). |
| Historical opening-line proxy | 2, 3, 7 | **Proxied.** SBRO season pages 2007-08 to 2021-22 have `Open` and `Close` columns (book unnamed). CBS odds-page Open covers 2025+. Nothing is verified for 2022-2024. nflverse `spread_line` is **not** an opener. |
| Live market spread at lock | 1, 3+ | **Available**: Parlay API (the user's existing key), 14 books incl. Pinnacle. Terms of use **UNVERIFIED**. |
| Historical closing lines | 3, 7 | **Proxied**: nflverse `spread_line` (last value before kickoff, from an unnamed source), 1999-2026. |
| Scores, schedule, kickoff, rest | all | **Available**: nflverse schedules 1999-2026. |
| Point-in-time injuries | 6 | **Report-date only.** No timestamps, so point-in-time use is not possible. |
| Point-in-time depth charts | 6 | **Available from 2025 only** (`dt` snapshot timestamps). Weekly and untimestamped for 2001-2024. |
| Inactives | 5, 6 | Released 90 min before kickoff (secondary sources; primary rule text **UNVERIFIED**). No structured feed verified. |
| Weather, historical and live | 6 | **Available**: Open-Meteo forecast, archive and historical-forecast APIs, plus NWS. |
| Precise scheduling on hosted runners | 5, 6 | **Unavailable.** Cron runs start 2.7-5.7 hours late. |

---

## 0.1 Which nflverse datasets exist via `nflreadpy`? Schemas, coverage, update frequency

`nflreadpy` 0.1.5 exposes these loaders: `load_schedules, load_teams, load_pbp,
load_player_stats, load_team_stats, load_injuries, load_depth_charts,
load_rosters, load_rosters_weekly, load_snap_counts, load_officials,
load_participation, load_nextgen_stats, load_pfr_advstats, load_ftn_charting,
load_players, load_trades, load_draft_picks, load_combine, load_contracts`,
plus `load_ff_*` fantasy helpers (not audited). `get_current_season()` returned
2026 and `get_current_week()` returned 3.

Full schemas (every column and dtype) and a sample row for each dataset are
in `evidence/nflverse_audit.json`.

| Loader | Rows (2025) | Cols | Oldest season tested (rows) | Notes |
|---|---|---|---|---|
| schedules | 7,548 (all seasons) | 46 | 1999–2026 | REG 7,239; WC 120; DIV 108; CON 54; SB 27 |
| pbp | 48,771 | 372 | 1999 (46,136) | |
| player_stats | 19,422 | 150 | 1999 (16,839) | |
| team_stats | 570 | 138 | 1999 (517) | |
| injuries | 6,068 | 16 | 2009 (4,821) | 2026 wk 1–3 present (692 rows) |
| depth_charts | 554,215 | 12 | 2001 (36,736) | **schema changed in 2025**, see 0.8 |
| rosters | 3,137 | 36 | 1999 (2,039) | |
| rosters_weekly | 46,849 | 36 | 2002 (31,086) | |
| snap_counts | 26,613 | 16 | **2012 returned 0 rows** | real start season **UNVERIFIED** |
| officials | 2,066 | 9 | 2015 (1,933) | |
| participation | 45,184 | 26 | 2016 (48,434) | release last updated 2026-02-10, so **no in-season 2026 data** |
| nextgen_stats | 605 | 29 | 2016 (573) | |
| pfr_advstats | 684 | 24 | 2018 (646) | |
| ftn_charting | 47,316 | 29 | 2022 (41,643) | |
| players / trades / draft_picks / combine / contracts | 24,830 / 4,975 / 12,927 / 8,968 / 52,944 | | n/a | |

"Oldest season tested" means that season loaded successfully. Earlier seasons
were not tried, so the true first season is **UNVERIFIED** unless it is 1999,
the first season nflverse schedules cover.

**Update frequency.** The `timestamp.json` assets on the `nflverse-data`
GitHub releases showed these `updated_at` values on 2026-09-24 (evidence:
`probe/.../gh_release_*.json`):

| schedules | injuries | depth_charts | rosters/weekly | pbp | stats_team | pfr_advstats | ftn | participation |
|---|---|---|---|---|---|---|---|---|
| 19:07Z | 12:41Z | 12:42Z | 12:44Z | 14:12Z | 14:14Z | 17:03Z | 09-23 21:03Z | **2026-02-10** |

These timestamps show that most datasets refreshed on the audit day and that
participation has not refreshed in-season. One snapshot cannot establish a
refresh cadence, so the cadence is **UNVERIFIED**. The Phase 1 daily refresh
job will log the timestamps over time.

## 0.2 Does nflverse schedules include a spread? Opening or closing? Source?

**Yes: `spread_line`.** It has a matching `home_spread_odds`,
`away_spread_odds`, moneylines and `total_line`.

- **Sign convention (verified).** Per the nflreadr `dictionary_schedules.csv`,
  "a positive number means the home team was favored … This lines up with the
  result column." Empirically, 3,252 of the 3,253 games with
  `spread_line > 0` and a moneyline have a negative home moneyline. The
  engine's canonical spread is the opposite sign (`S = −spread_line`); see
  `engine/picks/grading.py` and its tests.
- **Coverage.** 100% of regular-season games 1999–2025. Spread odds and
  moneylines exist from 2006 (moneylines are partial in 2006–2009).
- **Opening or closing: not an opener, and it updates live.** The 2026
  week-3 `spread_line` values, pulled 2026-09-24 when the schedules release
  was last updated at 19:07Z, match the CBS page's *current* spread in 14 of
  16 games. They differ from the CBS *Open* in 7 games:

  | Game | CBS Open (home) | CBS current (home) | nflverse home line |
  |---|---|---|---|
  | ATL@GB | −6.5 | −4.5 | −4.5 |
  | LAC@BUF | −4.5 | −7 | −7 |
  | TEN@NYG | −5.5 | −2.5 | −2.5 |
  | HOU@IND | +2.5 | +1.5 | +1.5 |
  | SEA@WAS | +6.5 | +7.5 | +7.5 |
  | KC@MIA | +11.5 | +11 | +10.5 |
  | BAL@DAL | +3 | +3.5 | +3.5 |

  The line tracks the market during the week. For completed games it
  therefore reflects the last update before kickoff, which approximates a
  **closing line**. The exact capture time for completed games is
  **UNVERIFIED**.
- **Source book: UNVERIFIED.** The dictionary does not name a sportsbook.
  In 2025 the share of whole-number lines fell from about 49% (2021–2024) to
  24.6% (see 0.4). That could mean the upstream source changed, but this is
  **UNVERIFIED**.

## 0.3 Can historical CBS opening lines be obtained? From where? Which seasons?

**Live, going forward: yes.** `https://www.cbssports.com/nfl/odds/` returned
HTTP 200 (1.2 MB) from a hosted runner. It renders one
`table.OddsBlock-game` per game with `data-game-abbrev="NFL_YYYYMMDD_AWAY@HOME"`,
`data-game-id`, and an **"Open"** column (`th.OddsBlock-betOdds--openingLines`).
One team row holds that team's opening spread and price, e.g. `-6.5 -112`;
the other row holds the opening total, e.g. `o46.5 -108`. The *current*
spread cells carry JSON that names the operator: for week 3 these were MGM,
DraftKings or FanDuel, all via `SRADAR` (Sportradar). The page does not say
which book or time the "Open" column comes from: **UNVERIFIED**. Evidence:
`probe/.../cbs_nfl_odds.html`; the parse is in
`tests/fixtures/cbs_odds_week3_2026_trimmed.html` and `tests/test_cbs_lines.py`.

**Critical conflict with the league rules.** The league rules say CBS lines
are always half-points. On the CBS odds page, **3 of 16 week-3 openers are
whole numbers**: NE@JAX JAX −3, BAL@DAL BAL −3, LV@NO NO −3. So **the CBS
odds-page "Open" column is not, in general, the league's grading line.** The
league most likely uses the spreads CBS posts in its **Football Pick'em /
Office Pool** product. According to search-engine summaries, which are
secondary sources, those spreads "always end in half-points" and are
"released on Wednesday morning and fixed". That product needs a login:
`picks.cbssports.com/football/pickem/` returned the logged-out landing page
with no lines. Its posting time, source, and half-point policy are
**UNVERIFIED**.

The official rules of CBS's national **Pro Football Pick'em contest** were
fetched in round 2 (`cbs_pickem_rules.html`). They say:
- Each game gets a "**Winning Margin** … by CBSI, at its sole discretion."
- "Pro Football Game match-ups will be posted no later than 1:00 pm ET on
  Tuesdays."
- "Each game listed within the Weekly Contest will lock at the scheduled
  gametime."

The rules do **not** say that margins are half-points, and they do not say
the margin equals the odds-page Open. The lock rule (scheduled gametime) also
differs from this league's kickoff −15 min, so the league may be a
commissioner-run Office Pool with its own settings. The Office Pool help
center page rendered client-side, with 8 lines of text and no rule content,
so its contents are **UNVERIFIED**. **The league's line source remains
UNVERIFIED and needs the user's confirmation.**

What the capture job does about it:
- It archives the odds-page Open column on every run. Whole-number values
  are **rejected and written to `data/lines/cbs_open_flags.csv` for manual
  review**, never graded.
- The league's actual line may differ from the odds-page Open even when both
  are half-points. **This must be confirmed by the user**, e.g. by comparing a
  week of league lines with `cbs_open_frozen.csv`. Until then, all CBS-line
  results carry that caveat.

**Historical, before 2026-09-24:** partly available from CBS week pages
`/nfl/odds/{season}/regular/week-{n}/`. Evidence:
`evidence/cbs_history_open_column.csv`.

| Page | Games | With Open | Whole-number opens |
|---|---|---|---|
| 2026 wk 1 | 16 | 16 | 4 |
| 2026 wk 2 | 16 | 16 | 8 |
| 2025 wk 1 | 16 | 16 | 5 |
| 2025 wk 10 | 14 | 14 | 2 |
| 2022 wk 5 | 16 | **0** (shown as "—") | – |
| 2018 wk 5 | 15 | **0** | – |
| 2012 wk 5 | 0 (no games rendered) | – | – |

So the odds-page Open exists for at least 2025–2026. The first season with it
lies between 2023 and 2025 and has not been checked. Across these four weeks,
19 of 62 odds-page openers (31%) are whole numbers. That is further evidence
that this column is **not** the league line. It remains usable as a *CBS
market opener* covariate, and it may be the nearest historical proxy if the
league line is set from it and rounded. Any such rounding rule is
**UNVERIFIED**.

**Update 2026-09-24 (user screenshot of the league pool, 4 of 16 week-3 games).**
The league is a CBS Office Pool ("BONSAI POOL 2026"). Its lines, recorded in
`data/lines/league_lines.csv`, compared with this audit's captures:

| Game | League line | CBS odds-page Open | Market, Thu 19:42Z (Parlay, main lines) |
|---|---|---|---|
| ATL@GB | GB −6.5 | GB −6.5 | GB −4.5 to −5.5 |
| LAC@BUF | BUF −7.5 | BUF −4.5 | BUF −7 to −7.5 |
| CAR@CLE | CAR −2.5 | CAR −2.5 | CAR −2.5 |
| NYJ@DET | DET −6.5 | DET −6.5 | DET −6.5 to −7 |

The league line matches neither the odds-page Open (LAC@BUF is 3 points off)
nor Thursday's market (ATL@GB is 1–2 points off). **Working hypothesis, not
yet verified:** the league line is the market at pool posting time (around
Tuesday), moved to a half-point. It will be tested once the capture jobs have
Tuesday and Wednesday snapshots to compare against weekly league lines.

## 0.4 Best documented proxy for historical openers; how it differs from CBS; whole-number counts

| Candidate | Status | Evidence |
|---|---|---|
| **SBRO** (sportsbookreviewsonline.com) NFL odds archive | **Verified format.** The index links season pages **2007-08 through 2021-22**, none later. The 2021-22 page is an HTML table with columns `Date, Rot, VH, Team, 1st–4th, Final, Open, Close, ML, 2H`. The favorite's row holds the spread and the other row holds the total, e.g. TB `Open 7 / Close 10`, DAL `52.5 / 52.5`. **The source book is not named: UNVERIFIED.** | `probe/20260924T194249Z/sbro_archive_page.html`, `probe/20260924T233924Z/sbro_2021_22.html` |
| AusSportsBetting `nfl.xlsx` | HTTP 403 (Cloudflare challenge) from the hosted runner: **UNVERIFIED**. The user could download it manually. | `probe/.../aussportsbetting_*` |
| CBS week pages, historical | **2025–2026 only** (see 0.3). 31% whole numbers. | `evidence/cbs_history_open_column.csv` |
| nflverse `spread_line` | **Not an opener** (0.2). Usable as a closing proxy only. | |

**How a proxy differs from CBS.** Every candidate is a market or book
opener, not the CBS league line. Proxies include whole numbers; league lines
never do. Openers differ across books by about a point in normal games, but
the size of the gap between any proxy and CBS is **UNVERIFIED** until the
live archive has weeks of overlap.

**Whole-number counts (in the nflverse line, 1999–2025 regular season, completed games).**
`evidence/spread_proxy_whole_numbers.csv`: **3,895 of 6,999 lines (55.6%)
are whole numbers**, and **190 games landed exactly on the line**. Share by
season: 1999–2020 50–67%; 2021–2024 48–51%; **2025: 67 of 272 (24.6%)**. Per
spec rule 0.4, backtests will grade landing-on-a-whole-number games as
pushes, exclude them from win rate, and report them as a separate count. The
same counts will be produced for SBRO once it is ingested.

## 0.5 Live market spread at lock time; terms of use

**Parlay API** (`parlay-api.com/v1`, the odds-api-compatible schema already
used by the kmodel MLB pipeline) returned HTTP 200 for
`/sports/americanfootball_nfl/odds?markets=spreads&regions=us`: 32 events,
260 book-level spreads from **14 books**:
`bet365, betmgm, betonline, betrivers, bovada, caesars, draftkings, fanatics,
fanduel, fliff, hardrock, parx, pinnacle, prophetx`. Each book carries a
`last_update` timestamp and a `stale_seconds` field. Evidence:
`probe/.../parlay_nfl_spreads.json`, with the key scrubbed. Implemented in
`engine/data/market.py`.

- **Terms of use, rate limits and quota: UNVERIFIED.** Not reviewed. The
  user should confirm that the plan allows automated polling.
- **The Odds API** (`api.the-odds-api.com/v4`) is reachable and returns
  `MISSING_KEY` without a key. It is a documented paid or free-tier
  alternative, not configured.
- **ESPN** `site.api.espn.com` returned HTTP 403 (Akamai "Access Denied")
  from the hosted runner, so it is not usable there.

## 0.6 Historical closing lines (for backtesting drift)

- **nflverse `spread_line`**: last pre-game value, 1999–2026 (0.2). The
  source book and exact capture time are **UNVERIFIED**, so "closing" is an
  approximation.
- **SBRO** season pages (2007-08 to 2021-22) carry a `Close` column
  (verified format, 2021-22; book unnamed).
- **Going forward**, the engine's own `market_captures.csv` archives
  lock-time and near-lock lines, which will measure lock versus close
  directly (spec Phase 3).

## 0.7 When are official inactives released relative to kickoff? Source?

Several secondary sources say **90 minutes before kickoff** and that the list
cannot change afterwards, except the emergency third QB: legionreport.com,
bettingpunter.com, and an nfl.com news article on COVID-era replacement of
late inactives. The primary NFL rulebook text was not retrieved, so this is
**UNVERIFIED (primary)**. **No structured, machine-readable inactives feed was
verified.** nflverse `injuries` holds practice and game-status reports, not
inactives (0.8). nfl.com/injuries returned 200. It shows weekly injury
reports and links to editorial "inactives" articles, but no structured
inactives table was found. Consequence: the final
pick window is kickoff −90 min to kickoff −15 min.

## 0.8 Which nflverse datasets are point-in-time, and which reflect final or report-date states?

| Dataset | Point-in-time? | Evidence |
|---|---|---|
| `depth_charts` **2025+** | **Yes.** Column `dt` holds snapshot timestamps. 2026 has 196 distinct `dt` values from 2026-03-22 to 2026-09-24T12:42Z, about two a day (~06:00Z and ~12:40Z). 2025 has 221. | `nflverse_audit.json` + live query |
| `depth_charts` ≤2024 | **No.** Weekly `season/week/club_code/depth_team`, no timestamp. | `nflverse_audit.json` |
| `injuries` | **No.** Rows are keyed by `season/week/team/player` with the final `report_status` (Out/Doubtful/Questionable) and practice status. There is no report timestamp; only 2009 has a sparse `date_modified`, and all 17 values are identical. | `nflverse_audit.json` |
| `schedules.spread_line` | **No.** Overwritten until kickoff (0.2). | |
| `schedules.home_qb_name/away_qb_name` | **No.** Filled with a *projected* starter for future games (2026 wk 3 is populated), and presumably replaced by the actual starter afterwards. Using the historical values would be look-ahead. The replacement behaviour is **UNVERIFIED**. | live query |
| `schedules.temp/wind` | **No.** Null for unplayed games and filled after the game, so it is an observed value, not a forecast. | live query |
| `rosters_weekly`, `snap_counts`, `pbp`, stats | Post-game states keyed by week. Usable only for games strictly before `as_of`. | |

Rule adopted: features from week-keyed datasets may only use weeks strictly
before the game's week. Only `depth_charts` from 2025 on may be filtered by
timestamp against `as_of`.

## 0.9 Weather source, historical and live

| Source | Result |
|---|---|
| Open-Meteo forecast `api.open-meteo.com/v1/forecast` | 200. Hourly temperature, wind and precipitation, requested in °F and mph. |
| Open-Meteo archive `archive-api.open-meteo.com/v1/archive` | 200 for 2015-12-20. Observed/reanalysis data, which is **look-ahead** if used as a lock-time feature. |
| Open-Meteo historical forecast `historical-forecast-api.open-meteo.com` | 200 for 2024-12-21. This is the correct point-in-time historical input. Its **first available date is UNVERIFIED**. |
| NWS `api.weather.gov/points` | 200 with a `forecastHourly` URL. US stadiums only. |
| nflverse `temp`/`wind` | Observed after the game (0.8); diagnostic only. |

Evidence: `probe/.../open_meteo_*.json`, `nws_points.json`. Open-Meteo terms
for commercial use are **UNVERIFIED**; this is a private league.

## 0.10 GitHub Actions scheduled-workflow timing on hosted runners

Measured on this user's own workflows in `wbblanck/kmodel`, 31 scheduled
runs from 2026-09-05 to 2026-09-24. The cron strings were verified unchanged
in the workflow history on `main`. Script:
`scripts/audit/gha_schedule_latency.py`.

| Workflow | Cron (UTC) | n | Delay to `created_at` (min / median / max) |
|---|---|---|---|
| actuals.yml | `0 12 * * *` | 10 | 193 / 242 / 343 min |
| slate.yml | `30 13 * * *` | 20 | 161 / 228 / 322 min |
| weekly.yml | `0 13 * * 1` | 1 | 335 min |
| **All** | | **31** | **161 / 239 / 343 min** |

No scheduled run was dropped: slate.yml ran on all 20 days. But **every
run started 2.7 to 5.7 hours late.** That rules out hosted-runner cron for a
per-game window of kickoff −90 to −15 minutes. By contrast, the push-
triggered probe run was created at 19:42:41Z, seconds after the push, so
event-triggered runs are prompt. The sample is one repository over three
weeks, and delays may vary by hour and load (**UNVERIFIED** in general).

**Decision (for Phase 5/6):** do not rely on `schedule:` for final picks. The
options, to be chosen by the user, are:
1. A local or always-on scheduler (cron, launchd or systemd) running
   `python -m engine run --game <id>`.
2. An external precise scheduler calling the `workflow_dispatch` API. The
   dispatch-to-start latency for that path has not been measured
   (**UNVERIFIED**).

Hosted cron stays in use only for the non-time-critical CBS capture (every
3 h) and for market snapshots, where each row records its true
`minutes_to_lock`.

---

## Open items for the user

1. **Which CBS product sets your league line?** The public odds page's Open
   column, or CBS Pick'em / Office Pool spreads? Please send one week of your
   league's lines so they can be compared with `data/lines/cbs_open_frozen.csv`.
2. **Parlay API terms and quota**: confirm that automated polling is
   allowed, and add `PARLAY_API_KEY` as a secret in this repository.
3. **Scheduler for final picks**: local machine, always-on host, or an
   external trigger (0.10).
