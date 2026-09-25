# NFL ATS League Engine

Picks a side in every NFL regular-season game against the **frozen CBS Sports
opening spread** for a private ATS league. Rigor and honesty come before
complexity: the null model is the CBS opener itself, and anything more
complex must beat it out of sample.

> **Status: Phase 0 (data audit) done. Phase 1 line capture is built and
> waiting for its first scheduled runs.** No model exists yet; the spec gates
> modeling behind Phases 2–7. `python -m engine run --game <id>` therefore
> exits with an explanation instead of a pick.
>
> Historical ATS performance, when it is reported, will not guarantee future
> performance.

## League rules (`config/league.yaml`)

| Rule | Value |
|---|---|
| Grading line | CBS Pick'em spread, posted by about 12:00 ET Tuesday and final for the week. Recorded in `data/lines/league_lines.csv` |
| Games picked | Every regular-season game (postseason excluded) |
| Lock | 15 min before each game's kickoff, per game |
| Spread format | Always x.5, so no pushes. Whole numbers are rejected and flagged for manual review |

Sign convention: `S` is the home spread, negative when home is favored.
`Margin = home − away`. Home covers if `Margin > −S`. nflverse `spread_line`
has the opposite sign, and `engine.picks.grading` converts it.

## Data sources (details and evidence: `docs/data_audit.md`)

| Source | Use | Verification |
|---|---|---|
| nflverse via `nflreadpy` | schedules, scores, pbp, injuries, depth charts | Verified 2026-09-24 |
| CBS odds page `cbssports.com/nfl/odds/` "Open" column | live CBS opener capture | Page structure verified. **Whether it is the league line is UNVERIFIED**: 3 of 16 week-3 openers were whole numbers |
| Parlay API (odds-api schema) | market spread near lock | Verified live, 14 books. Terms **UNVERIFIED** |
| nflverse `spread_line` | historical closing-line proxy | Updates live, so it is not an opener. Source book **UNVERIFIED** |
| Open-Meteo / NWS | weather (Phase 6) | Endpoints verified |

## Install

```bash
pip install -e ".[dev]"      # add ".[model]" once modeling phases start
pytest -q
```

## Pipeline (current)

```bash
python -m engine capture-cbs        # fetch CBS odds pages (this and next week), append captures, refresh frozen openers
python -m engine backtest           # Phase 7 walk-forward -> docs/phase7_results.md
python -m engine grade              # live record vs league line -> data/predictions/live_record.md
python -m engine features           # Phase 6 ablation -> docs/phase6_results.md
python -m engine calibrate          # Phase 5 report -> docs/phase5_results.md
python -m engine coverprob          # Phase 4 report -> docs/phase4_results.md
python -m engine drift              # Phase 3 report -> docs/phase3_results.md, data/backtests/
python -m engine baselines          # Phase 2 report -> docs/phase2_baselines.md, data/backtests/
python -m engine freeze-cbs         # re-derive data/lines/cbs_open_frozen.csv from the capture archive
PARLAY_API_KEY=... python -m engine capture-market                  # games locking within 90 min
PARLAY_API_KEY=... python -m engine capture-market --all-games      # snapshot of every upcoming game
```

Files in `data/lines/`:

| File | Content |
|---|---|
| `cbs_open_captures.csv` | Append-only archive of every parsed CBS opener, with `captured_at`, `source_url` and page hash |
| `cbs_open_flags.csv` | Rejected (whole-number), unmatched, missing and fetch-error rows for manual review |
| `cbs_open_frozen.csv` | Derived. First valid capture per game. Later changes are listed, never applied |
| `market_captures.csv` | Append-only, one row per game × book, with `minutes_to_lock` |
| `raw_cbs/` | Gzipped raw CBS HTML, saved whenever the parsed openers change |

## Weekly routine: recording the league line

CBS posts the league spreads by about 12:00 ET Tuesday, behind the pool
login. No public copy exists (audit 0.3). Each Tuesday afternoon:

1. Screenshot the pool's Picks screen, scrolling to cover all games, and send
   the screenshots.
2. The lines are transcribed into `data/lines/league_lines.csv`.
3. `python -m engine check-league-lines --season 2026 --week N` confirms that
   every line is a half-point, matches the schedule, and that no game is
   missing.

## Final picks at lock

`lock-run.yml` makes the final pick for every game 15–25 minutes before its
lock. An **external timer** triggers it through the GitHub API; setup is in
`docs/scheduling.md`. Current pick rule: the side with the higher
probability of covering the league line, given the market at lock
(`phase4-shifted-empirical-argmax`). Without a margin distribution it falls
back to the Phase 3 drift rule. Picks are appended, never edited, to
`data/predictions/predictions.csv`, with a weekly slate in
`data/predictions/slate_<season>_wNN.md`. Probabilities are raw (Phase 5
found no calibrator that helps) and overconfident at the extremes.

## Automation (`.github/workflows/`)

| Workflow | Trigger | Purpose |
|---|---|---|
| `ci.yml` | push / PR | tests |
| `capture-cbs.yml` | every 3 h | CBS opener capture; commits to `data/lines/` |
| `capture-market.yml` | every 30 min in game-day windows; daily all-games snapshot | market capture |
| `audit-probe.yml` | push to the probe script / manual | Phase 0 evidence on an open-internet runner |

**Scheduling caveat (audit 0.10).** Scheduled runs on GitHub-hosted runners
started **2.7–5.7 hours late** (31 runs measured). Hosted cron is fine for
openers captured every 3 h. It **cannot** hit the kickoff −90 to −15 minute
final-pick window. Final picks will need a local or always-on scheduler, or
an external trigger calling `workflow_dispatch`. That decision is open.

**Secrets:** add `PARLAY_API_KEY` in the repository settings (Secrets and
variables → Actions).

## Methodology, backtests, calibration

**Phase 2 (baselines): done.** See `docs/phase2_report.md`. Against the SBRO
opening line for 2007–2021 (3,722 decided games), the best fixed strategy is
*always away* at **51.37% ± 0.82 pp**. That is not distinguishable from 50%
(z = 1.67), and it is the bar later models must clear. No league-line games
have been graded yet.

**Phase 3 (drift): passed on the historical proxy.** See
`docs/phase3_report.md` (pre-registered in `docs/phase3_preregistration.md`).
Picking the side the market moved toward between the open and the close,
graded against the frozen open, won **54.84% ± 0.90 pp** (N = 3,060, z = 5.38
vs 50%, z = 2.85 vs the Phase 2 bar). It was above 50% in all 15 seasons. The
edge against the actual CBS Tuesday line is expected to be smaller and is not
yet measured.

**Phase 4 (cover probabilities): done.** See `docs/phase4_report.md`.
P(cover) comes from the empirical distribution of the final margin around the
market spread (the shifted-empirical estimator, which had the lowest
walk-forward log loss). The pick is the higher-probability side. The
probabilities are weak, 90% between 0.40 and 0.60, and **not yet
calibrated**. Key-number probabilities (3 and 7) are known to be biased.

**Phase 5 (calibration): report done, probabilities stay raw.** See
`docs/phase5_report.md`. Platt, isotonic and Platt-with-key-numbers were fitted
chronologically. None beat the raw probabilities on both out-of-sample log
loss and calibration error, so none was adopted. The raw extremes are
overconfident: a stated 60%+ has hit about 55%.

**Phase 6 (residual features): no group survived.** See
`docs/phase6_report.md`. QB change, rest and opponent-adjusted EPA efficiency
each made out-of-sample results worse once the market line was known. The
efficiency rating correlates 0.79 with the spread but only 0.02 with what the
spread missed. The model stays market-only. Weather was not tested, because
its historical data is post-game.

**Phase 7 (full-system walk-forward): kill criterion passed on the historical
proxy.** See `docs/phase7_report.md`. For 2007–2021 (3,722 decided games) the
record is 2043-1679, **54.89% ± 0.82 pp**, z = 3.04 vs the 51.37% bar. It was
above 50% in all 15 seasons, with a worst season of 50.8%. The edge is
concentrated in games where the market moved ≥ 1 point (57.3%). This is **not
independent**: the same seasons informed the design. The independent test is
live 2026 play, graded in `data/predictions/live_record.md`, with no skill
claim before 256 graded games.

**Key-number fix: failed its pre-registered test; now running as a live shadow.**
See `docs/keynumber_report.md`. Over 2007–2021 it lost to the live estimator
(54.57% vs 54.89%). In 2025 it won 144-123 vs 130-137. Both estimators are
recorded on every live pick. The switch rule is pre-registered for the end of
2026.

**Historical ATS performance does not guarantee future performance.**

Later phases are gated per the spec:
Phase 2 baselines → 3 drift → 4 cover probability → 5 calibration → 6 residual
features → 7 walk-forward. Results will be reported here, including
failures, with standard errors.

## Known limitations

- The league's exact CBS line source is unconfirmed (audit 0.3).
- Historical CBS odds-page openers exist only for 2025–2026, and 31% of them
  are whole numbers. Earlier backtests need a proxy: SBRO open/close for
  2007–2021, nflverse close for 1999+. See audit 0.3 and 0.4.
- nflverse injuries have no timestamps. Point-in-time depth charts exist
  only from 2025.
- Hosted-runner cron is hours late (audit 0.10).

## Repository layout

```text
config/        league.yaml, data.yaml, model.yaml
data/          raw/ processed/ lines/ predictions/ backtests/
docs/          data_audit.md, evidence/
scripts/audit/ reproducible Phase 0 evidence scripts
src/engine/    config, teams, data/{nflverse,cbs_lines,market,store}, picks/grading, __main__
tests/         grading, team mapping, CBS parser/archive, market + lock + no-lookahead
```

The layout differs from the spec in two ways, both deliberate:
- `teams.py` and `config.py` sit at the package root because every module
  uses them.
- The line archive is CSV rather than Parquet so each capture is a
  reviewable git diff. Parquet and DuckDB are for processed data.
