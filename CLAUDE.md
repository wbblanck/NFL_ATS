# NFL_ATS: notes for Claude

Against-the-spread pick engine for the CBS "Bonsai Pool 2026". The goal is to win the pool without disturbing the live pick pipeline. Python package in `src/engine`, run as `python -m engine <command>`. Tests: `pytest`.

## Rules from the owner

- Never ask for, print, or paste secrets (`PARLAY_API_KEY`, `NTFY_TOPIC`, GitHub tokens). They live in GitHub Actions secrets or cron-job.org only.
- Merge to `main` only when the owner says "merge". Research work stays on its branch.
- No model names or identifiers in commits, PRs, or committed files. Use only the `Claude-Session:` trailer.
- Label guesses as guesses. Verify against the repo or data before stating facts.
- Do not read settings files, `.mcp.json`, or `~/.claude.json`.
- Only `wbblanck/NFL_ATS` and `wbblanck/kmodel`. The repo stays private.
- AusSportsBetting data is for personal use: never commit or republish it.
- Never write, edit, or backfill picks after the fact. Missed locks stay missed.
- Keep tool output small: filter lists, tail logs, read single rows.

## Conventions

- **Spread sign (canonical):** negative = home favored. Home covers when `margin > -spread`. nflverse `spread_line` has the opposite sign (positive = home favored).
- **Lock** = kickoff − 15 min. Picks are made 5 min before lock (`lead_minutes` 5).
- **Market input:** the Pinnacle line from the pick-time capture. One retry 60 s later if Pinnacle is missing; then Pinnacle from OddsPapi (`MARKET_ODDSPAPI`), then from OddsLink (`MARKET_ODDSLINK`) (owner decisions 2026-10-18/19, no end date: `final.ODDSPAPI_FALLBACK_UNTIL`); then the median of all books, flagged `MARKET_MEDIAN_FALLBACK`. `FEW_BOOKS` marks any pick with fewer than 5 books, Pinnacle or median.
- **Record:** `data/predictions/live_record.md`, graded against the pool line. No skill claim before 256 graded games (pre-registered).
- Projection models (team-only v1, player v3, hybrid, key-number) are tracked for comparison only. Only the official pick counts.

## Weekly operations

- **Lock runs** (`lock-run.yml`) are dispatched by six cron-job.org jobs (America/New_York), each with `wait` true, `lead_minutes` 5:

  | Fires (ET) | Covers | `window_minutes` |
  |---|---|---|
  | Thu 7:15 PM | 8:15 PM kickoff | 55 |
  | Sun 8:30 AM | 9:30 AM (international) | 55 |
  | Sun 12:00 PM | 1:00 PM games | 55 |
  | Sun 3:05 PM | 4:05 / 4:25 PM games | 75 |
  | Sun 7:20 PM | 8:20 PM kickoff | 55 |
  | Mon 7:15 PM | 8:15 PM kickoff | 55 |

  Any kickoff these jobs miss needs a one-off job (Saturday, Thanksgiving afternoon, Christmas, Friday, an earlier Monday doubleheader game, an international game not at 9:30 AM Sunday); check each week's kickoffs against the table, and never add a job for a game a recurring job already covers. Request body and details: `docs/scheduling.md`. Missed locks stay missed: never use the `game_id` input or `engine run --game` after a game's lock. Do not also dispatch a slot from Claude: a game could be picked twice. GitHub's own cron starts hours late, so it is not used for locks.
- Each lock run picks, grades finished games, commits, sends the ntfy alert, and dispatches `publish-dashboard.yml` (rebuilds `site/dashboard.html`, shown in the private Streamlit app). Do not republish the retired claude.ai artifact.
- **Pool lines:** the owner sends CBS pool screenshots on Tuesday. Transcribe them into `data/lines/league_lines.csv` (`spread` = home team's spread, `favorite`, source with the phone-clock time in ET, `recorded_at` in UTC), confirm with the owner, commit to `main`, then run `python -m engine cbs-lines` and report exact matches per source from the regenerated `docs/cbs_lines_report.md` (the command itself prints only a count). Committing lines does not rebuild the dashboard: dispatch `publish-dashboard.yml` on `main` afterwards and check that the new page shows every game's pool line.
- **Captures:** `capture-market.yml` (`all_games` true) and `capture-cbs.yml`. There is no market backfill: the provider's history endpoint is unusable, so its workflow was removed.

## Known limits

- GitHub Free: 2,000 Actions minutes a month, shared with the owner's other private repos; a small budget covers overage. When minutes run out, jobs fail within seconds with no steps and no logs.
- OddsPapi (secret `ODDS_PAPI`, passed as env `ODDSPAPI_API_KEY`; 250 requests a month, maybe shared with kmodel): read the `oddspapi-api` skill (`.claude/skills/oddspapi-api/SKILL.md`) first. Not used by the pick pipeline. NFL ids, spread markets and sign verified 2026-10-18 (skill has details).
- As of 2026-10-15, the odds provider's feed has often lacked Pinnacle (since 2026-10-08), so most picks use the median. Check the `MARKET_MEDIAN_FALLBACK` share of recent rows in `data/predictions/predictions.csv` before assuming this still holds.

## Branches

- `claude/nfl-ats-league-engine-q5vkbf`: research (FTN shadow model, bettable record, skip filters). Unmerged, and conflicts with `main` (its Pinnacle retry is already on `main`). Remaining live-pipeline changes (strength tag in ntfy alerts, bettable/strength dashboard sections) are on hold by owner decision 2026-10-29. Holds two one-off probe workflows (`parlay-pinnacle-probe.yml`, `openmarkets-auth-probe.yml`) to remove before any merge.
- `claude/nfl-alt-markets`: merged into `main` 2026-10-29 (alt-market research only; no pipeline changes).
- `claude/cbs-lines-w6`: deleted 2026-10-29 (its week 6 report was superseded on `main`).
