# NFL ATS League Engine

Picks a side against the spread in every NFL regular-season game for the CBS "Bonsai Pool 2026". The pick is graded
against the **pool line**, the CBS spread posted by about 12:00 ET each Tuesday. Rigor and honesty come before
complexity: the null model is the line itself, and anything more complex must beat it out of sample.

> **Status (2026 season, in play).** The live pick pipeline runs every week. The record is in
> `data/predictions/live_record.md` (29-23 after 52 graded games, as of 2026-10-19). **No skill claim is made before
> 256 graded games** (pre-registered). Historical ATS performance does not guarantee future performance.

## How a pick is made

1. About 20 minutes before kickoff (5 minutes before the 15-minute lock) the lock run captures every book's spread.
2. **Market input:** the Pinnacle line. If Pinnacle is missing it retries once 60 seconds later, then uses the median of
   all books and flags the pick `MARKET_MEDIAN_FALLBACK`. Any pick with fewer than 5 books is flagged `FEW_BOOKS`.
   See `docs/market_input.md`.
3. **Model** (`total-shifted-empirical-argmax`, config in `config/model.yaml`): the market spread is the predicted
   margin. The model fits the distribution of final margins around the market spread from regular-season games since
   2000, widens or narrows it with the game total, and computes P(home covers the pool line).
4. **Pick:** the side with the higher cover probability. In practice that is the side the market has moved toward
   since the pool line was set.
5. One immutable row is appended to `data/predictions/predictions.csv`. Picks are never edited or backfilled, and a
   missed lock stays missed.

Probabilities are raw: no calibrator improved out-of-sample results (Phase 5), and the extremes are overconfident.

### Tracked comparisons (they never make the pick)

Recorded at lock and graded alongside the official pick in `live_record.md`:

| Tracked | What it is | Notes |
|---|---|---|
| Key-number shadow | Margin distribution that keeps the mass at 3 and 7 | `docs/keynumber_report.md`; switch rule pre-registered for the end of 2026 |
| `proj-poisson-v1` | Team-only score projection | `docs/projection_report.md` |
| `proj-players-v3` | Player-based score projection | `docs/players_v3_report.md` |
| Hybrid | Live pick on 1+ point moves, `proj-poisson-v1` otherwise | `docs/hybrid_tracking.md`; promotion needs z ≥ 1.645 |

## Dashboard

`site/dashboard.html` is a static page that `publish-dashboard.yml` rebuilds after each lock run and on a score
schedule. A private Streamlit app (`streamlit_app/app.py`) embeds it and adds a live-scores strip from ESPN.

- **Week view:** games grouped into kickoff slots, a next-lock countdown, the live record, and filters (1+ point off the
  pool line, projection disagrees, hybrid disagrees).
- **Game cards:** pool line, market move, the pick and its cover chance, the tracked projections, and the result.
- **Game detail:** why the pick was made, a line-movement chart (Pinnacle, median, range of books, pool line), and the
  book-by-book capture table.
- **Season panels:** season path with a luck band, tiebreaker guesses, record by week, a slate replay, and a loss
  review.

Rebuild it locally with `python -m engine dashboard`.

## Weekly operations

The full runbook is in `CLAUDE.md`. In short:

- **Lock runs** (`lock-run.yml`) are dispatched by six external cron-job.org jobs (Thursday, Sunday x4, Monday). Setup
  and request bodies are in `docs/scheduling.md`. Each run picks, grades finished games, commits, sends a phone alert
  and dispatches the dashboard build. GitHub's own cron is hours late, so it is not used for locks (audit 0.10).
- **Pool lines:** each Tuesday the pool screenshots are transcribed into `data/lines/league_lines.csv`, then
  `python -m engine check-league-lines --season 2026 --week N` confirms every line is a half-point, matches the
  schedule and that no game is missing.
- **Secrets** (`PARLAY_API_KEY`, the alert topic) live in GitHub Actions secrets and cron-job.org only.

## Automation (`.github/workflows/`)

| Workflow | Trigger | Purpose |
|---|---|---|
| `ci.yml` | push / PR | tests |
| `lock-run.yml` | external dispatch | final picks, grading, alert |
| `publish-dashboard.yml` | dispatch from lock runs, plus game-day crons | rebuilds `site/dashboard.html` |
| `capture-cbs.yml` | every 3 h, every 30 min on Tuesday | CBS odds-page capture |
| `capture-market.yml` | daily all-games snapshot, Tuesday every 2 h | book spreads for line-movement history |
| `fetch-*`, `probe-*`, `audit-*`, `*-probe`, `ntfy-test`, `render-page` | manual | one-off evidence and connectivity checks |

`backfill-market.yml` must not be dispatched: the provider's history endpoint is unusable.

## Commands

```bash
pip install -e ".[dev]"                 # add ".[model]" for the modeling extras
pytest -q

python -m engine lock-run               # what lock-run.yml runs; never use it after a game's lock
python -m engine grade                  # live record -> data/predictions/live_record.md
python -m engine dashboard              # build site/dashboard.html
python -m engine preview                # pre-lock preview for a week
python -m engine alert                  # phone-alert lines for locked picks
python -m engine check-league-lines --season 2026 --week N
python -m engine cbs-lines              # compare pool lines to captured sources -> docs/cbs_lines_report.md
python -m engine capture-cbs            # CBS odds-page openers
python -m engine freeze-cbs             # re-derive data/lines/cbs_open_frozen.csv
PARLAY_API_KEY=... python -m engine capture-market [--all-games]
```

Research reports, each rewriting its file in `docs/` and `data/backtests/`:
`baselines`, `drift`, `coverprob`, `calibrate`, `features`, `backtest`, `holdout2025`, `players-v3`,
`efficiency-residual`, `projection-v6`.

### Data files (`data/lines/`)

| File | Content |
|---|---|
| `league_lines.csv` | The pool line per game, transcribed from the Tuesday screenshots |
| `cbs_open_captures.csv` | Append-only archive of every parsed CBS odds-page opener |
| `cbs_open_flags.csv` | Rejected (whole-number), unmatched, missing and fetch-error rows |
| `cbs_open_frozen.csv` | Derived: first valid capture per game |
| `market_captures.csv` | Append-only, one row per game x book, with `minutes_to_lock` |
| `raw_cbs/` | Gzipped raw CBS HTML, saved whenever the parsed openers change |

AusSportsBetting data is for personal use and is never committed or republished.

## Conventions

Spread `S` is the home spread, negative when home is favored. `Margin = home - away`. Home covers if
`Margin > -S`. nflverse `spread_line` has the opposite sign, and `engine.picks.grading` converts it. Pool lines are
always x.5, so there are no pushes; whole numbers are rejected and flagged for review.

## Data sources (details and evidence: `docs/data_audit.md`)

| Source | Use | Verification |
|---|---|---|
| nflverse via `nflreadpy` | schedules, scores, play-by-play, injuries, depth charts | Verified 2026-09-24 |
| Parlay API (odds-api schema) | book spreads near lock, including Pinnacle when available | Verified live. Terms **UNVERIFIED**. The feed has often lacked Pinnacle since 2026-10-08 |
| CBS odds page "Open" column | CBS opener capture | **Not confirmed to be the pool line**: 31% of historical openers are whole numbers |
| nflverse `spread_line` | historical closing-line proxy | Updates live, so it is not an opener. Source book **UNVERIFIED** |
| SBRO | 2007-2021 opening and closing lines for backtests | Proxy for the pool line |
| Open-Meteo / NWS | weather | Endpoints verified; weather was not tested |

## Methodology and results

Each phase was pre-registered in `docs/` before its results were computed, and failures are reported with standard
errors. The historical numbers use proxy lines (SBRO open as the pool line, nflverse close as the market) and the same
seasons informed the design, so they are **not independent evidence**. Live 2026 play is the independent test.

| Phase | Result | Report |
|---|---|---|
| 2 Baselines | Best fixed strategy is always-away at 51.37% +/- 0.82 pp over 2007-2021 (z = 1.67 vs 50%). This is the bar to clear | `phase2_report.md` |
| 3 Drift | Picking the side the market moved toward: 54.84% +/- 0.90 pp (N = 3,060), passed on the proxy | `phase3_report.md` |
| 4 Cover probability | Shifted-empirical distribution had the lowest walk-forward log loss. 90% of probabilities fall between 0.40 and 0.60 | `phase4_report.md` |
| 5 Calibration | Platt, isotonic and Platt-with-key-numbers all failed to beat raw out of sample. Raw kept | `phase5_report.md` |
| 6 Residual features | QB change, rest and EPA efficiency each made results worse once the market was known. The model stays market-only | `phase6_report.md` |
| 7 Walk-forward | 2043-1679, 54.89% +/- 0.82 pp over 2007-2021, z = 3.04 vs the Phase 2 bar. Concentrated in games where the market moved 1+ point (57.3%) | `phase7_report.md` |
| 2025 holdout | On the 210 half-point CBS openers: 108-102 (51.4% +/- 3.5 pp). Reported only | `holdout2025_results.md` |
| Key-number fix | Lost its pre-registered test (54.57% vs 54.89%), so it runs as a live shadow | `keynumber_report.md` |
| Game-total fix | Adopted. Improves log loss slightly and changes no picks | `total_report.md` |
| Hybrid rule | Failed its backtest. Tracked live at the owner's request | `hybrid_report.md` |

More pre-registered studies (projection v4 to v6, player models, tiebreaker, sharp line, and others) have their own
`*_preregistration.md` and `*_report.md` pairs in `docs/`.

## Known limitations

- The pool's exact line source is unconfirmed (audit 0.3). Pool lines are recorded by hand from screenshots.
- Historical CBS odds-page openers exist only for 2025-2026, so earlier backtests use proxy lines.
- The odds feed often lacks Pinnacle, so many picks use the median of books. Check the `MARKET_MEDIAN_FALLBACK` share
  of recent rows in `predictions.csv`.
- nflverse injuries have no timestamps. Point-in-time depth charts exist only from 2025.
- GitHub Free gives 2,000 Actions minutes a month, shared with other private repos. When minutes run out, jobs fail
  within seconds with no steps and no logs.
- The live sample is small. 52 games cannot separate a 55% edge from luck.

## Repository layout

```text
config/          league.yaml, data.yaml, model.yaml
data/            raw/ processed/ lines/ predictions/ backtests/
docs/            pre-registrations, reports, data_audit.md, scheduling.md, evidence/
scripts/         audit/ (Phase 0 evidence), fetch/
site/            dashboard.html (generated)
streamlit_app/   private viewer for the dashboard plus a live-scores strip
src/engine/      __main__ (CLI), config, teams
  data/          nflverse, market, cbs_lines, league_lines, store, and other sources
  features/      efficiency, QB, rest, availability, player features
  models/        margin_dist, projection models, drift, adaptive
  picks/         final (lock picks), live (grading), grading, dashboard, alerts, hybrid, and more
  backtest/      one module per pre-registered study
tests/           grading, team mapping, parsers, market and lock logic, no-lookahead checks
```

The line archive is CSV rather than Parquet so each capture is a reviewable git diff.
