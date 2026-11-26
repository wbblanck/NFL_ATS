# Audit A (inputs and pipeline), 2026-11-19

Read-only audit of `wbblanck/NFL_ATS` at main `c51e678` (2026-11-18). No formula, model logic, data file or workflow was changed. Every number below was re-computed from the repo's CSVs and a fresh nflverse schedule pull. Guesses are labelled as guesses.

## Headline

**I found no data leak and no grading bug. The live record is computed correctly. The real problem is that nothing yet shows the pick has an edge against your pool line, and part of what the dashboard shows blends in games that were never live picks.**

1. **The official pick is the direction the line moved, and nothing else.** On all 96 picks made with a market line, the pick equals "the side the line moved toward since the pool line; no move means away". The margin distribution, the market-total scaling, the cover probabilities and the key-number shadow never changed a pick. I also swept 6 totals and every half-point market and pool-line pair on the current fit: 0 cases where the probability rule disagrees with the move rule.
2. **Live record, stated in full** (re-graded independently from `predictions.csv` and nflverse scores): **56-49, 105 graded games, 0 pushes, graded against the CBS pool line you transcribed (the line frozen in each prediction), live picks only, no backtest or reconstructed games.** That is 53.3%. A coin flip gets 56 or more wins in 105 games 28% of the time (exact binomial). `live_record.md` shows 55-49 on 104 because the Monday game finished after its last update.
3. **The record does not match where the backtest said the edge would be.** The 2007-2021 backtest (graded against SBRO opening lines, not the pool line) said moves of 1+ point win 57.3% and moves under 1 point are coin flips. Live: 1+ point moves are **20-24 (44 games)**, under 1 point are **30-22 (52 games)**, no market line **6-3 (9 games)**. Samples are small, so this is a warning, not a verdict.
4. **The dashboard "Season Drive" verdict is not the live record.** It says "150 games, official +12 net wins". Live is 56-49, +7 on 105. The 150 includes 32 weeks 1-2 backtest games, 1 hypothetical week 6 game and 12 games that were never picked.
5. **Only 81% of games get a market-informed pick.** Of 118 games in weeks 3-10, 13 were missed (11%) and 9 more were blind away picks (no market). And 9 of the 122 remaining games are not covered by the six recurring cron-job.org jobs (list in issue 4).
6. **The 256-game pre-registered claim cannot be reached in 2026.** 105 graded now, plus at most 122 games left in weeks 11-18, is 227 at best.

## Ranked issues

Severity is about impact on accuracy or on how far the numbers can be trusted.

### 1. High. No evidence yet of an edge against the pool line, and the backtest evidence is the wrong kind

**Evidence**
- `src/engine/picks/final.py:122-141` (`decide`): pick is home if the cover probability is above 0.5. With the shifted-empirical distribution (`models/margin_dist.py`, `sf`) that is a monotone function of drift, so it is the same as the move rule. Verified on the 96 live picks and on the grid above.
- Backtest used to justify it: `docs/phase7_report.md`. 2007-2021, **2043-1679-119 (3,841 games including pushes), 54.89%, graded against SBRO opening lines, with the nflverse close standing in for the market at lock.** The same 2007-2021 games were used to choose the rule, so it is in-sample (the report says so).
- Against a real CBS line: 2025 holdout, **130-137-4 (271 games), 48.7%**, and 66-61-1 on moves of 1+ point (`docs/holdout2025_results.md`). 2022-2024 against bet365 opens: 256-197 on half-point opens (`docs/gap2022_report.md`), but that report itself says it overstates the pool, because the pool line is posted after the first wave of movement.
- Live 2026 splits (my recompute, pool line, live picks only): market-informed and picked on time 41-41 (82 games); drift 0: 14-11 (25); drift 0.5: 16-11 (27); drift 1.0: 11-13 (24); drift 1.5 or more: 9-10 (19).

**Why it matters.** The pool line is set after part of the move has happened, so the real drift is smaller than any bookmaker-open proxy. Every historical test used a proxy that was earlier than the pool line. The one test with a real CBS line (2025) and the live record both sit near 50%.

**Fix (no logic change, a test).**
- *Historical:* the ESPN timestamped line history for 2018-2022 and the registered Tuesday pool-line rebuild rule (DraftKings first Tuesday 8 AM-4 PM ET line, commit 2c022b4) give the closest thing to a pool line for 1,311 games. Run the frozen rule once on those rebuilt lines, but only if the rebuild passes its own registered bar (80% exact on weeks 11-18, 2026). Report W-L on all games and on drift 1+ separately.
- *Unseen:* pre-register now, before week 11 kicks off, one primary test: "official pick, weeks 11-18, graded on the frozen pool line, versus 50%", plus one secondary: "drift 1+ versus drift under 1". Expect about 110 games and about 40 with drift 1+, which cannot detect a 4-point edge (see issue 7). Say so in advance rather than reading the result as proof either way.

### 2. High (trust). Dashboard Season Drive verdict mixes backtest, hypothetical and unpicked games

**Evidence**
- `src/engine/picks/curve.py` (`build`) makes one series from every finished game with a pool line. Live picks use `predictions.csv`; other games use `data/backtests/early2026.json` (weeks 1-2, market at lock = nflverse close, so hindsight) and `data/backtests/week6_fill.json`. `MODELS` includes `official`, so a hypothetical official pick is filled for ARI@LA even though the comment in `dashboard.py` (near line 120) says "the official pick is never filled". `n = len(games)` counts every finished game, including ones with no official pick.
- Published page (`site/dashboard.html`): "Inside the luck band ... (150 games, official +12 net wins, a coin-flipper would be within ±24)".
- My reconstruction of the +12: live 56-49 (+7), weeks 1-2 backtest official 18-14 (+4), ARI@LA hypothetical (+1) = +12. The 150 is 138 pick rows plus 12 games with no pick.
- Same page, "Model standings": team-only projection **59-44** includes week 6 backtest 3-4 (live 56-40); key-number **57-48** includes 7-2 backtest (live 50-46); official is live only (56-49). The note is there, but the totals sit side by side.

**Why it matters.** The headline number is better than the live record and uses a wider luck band than the live sample warrants. It also sits uneasily with the rule that picks are never written or backfilled after the fact (it is labelled `bt`, but not in the verdict sentence). This was flagged in the 2026-11-09 audit (finding 9, "Low") and is still open; it is larger now.

**Fix.** Compute the verdict from live graded rows only (N from `live.compute`), and label backtest rows separately. Test: assert the verdict's N and net equal `live_record.md` (56-49, +7 on 105 today); add a unit test in `tests/test_curve.py`. Needs your approval because it changes what the dashboard states.

### 3. Medium. 2022-2025 and 2007-2021 are no longer unseen for line-based ideas

**Evidence (what has touched which years)**
- 2007-2021: designed Phases 3-7 on it (in-sample, disclosed).
- 2022-2024 (AusSportsBetting bet365): gap2022 test, key-number lead (38-40, failed), ATS-form replication (236/468), hybrid-with-simulator (failed), factors v7 (342-352), pattern65 (55-23 on 2022-24 reported), variants. A grep finds 2022-2025 in 29 of the backtest modules.
- 2025: holdout2025 (CBS opens) and the simulator out-of-sample test. Betr 2025 lines failed verification.

**Why it matters.** More than 20 tests have been run against the same few seasons. Holm inside each family does not control the error across families, so a "pass" in the next test needs a higher bar.

**Fix.** Keep a ledger (`docs/test_ledger.md`) listing every test, family size, data used, and result. Treat 2026 weeks 11-18 and 2027 as the only clean data. Before any new idea touches 2022-2025, state how many tests have already used it. Cheap, no logic change.

### 4. Medium. Roughly one game in nine gets no pick; one in thirteen more gets a blind away pick

**Evidence** (schedule weeks 3-10 = 118 games; `predictions.csv` = 105 rows)
- 13 missed: ATL@GB (Thu, wk 3), ATL@NO (Mon, wk 4), DEN@LAC, DET@ARI, SF@SEA, BAL@ATL (wk 5), ARI@LA (wk 6), PIT@NO, GB@DET, LA@LV (wk 7), LA@ARI, SEA@LV, SF@DAL (wk 10). Causes recorded in project memory: cron window 55 instead of 75, Actions billing outage, the push race fixed by PR #66.
- 9 blind away fallbacks (week 6, no market, flag `NO_MARKET`): 6-3.
- 17 picks in weeks 3-4 carry `feature_version = none` (an older median input, no label), and 14 picks were made 15-63 minutes before lock (stale market): early 9-5.
- By source (all 105 live picks): Pinnacle or unlabelled 36-37 (73, includes the 17 unlabelled early picks), OddsPapi Pinnacle 9-5 (14), median fallback 5-4 (9), no market 6-3 (9).
- Rest of season, per the nflverse schedule pulled today and the six-job table, **not covered by a recurring job (needs a one-off): Wed Nov 25 8:00 PM GB@LA; Thu Nov 26 1:00 PM CHI@DET; Thu Nov 26 4:30 PM PHI@DAL; Fri Nov 27 3:00 PM DEN@PIT; Sat Dec 19 5:00 PM SEA@PHI and 8:20 PM CHI@BUF; Fri Dec 25 1:00 PM GB@CHI, 4:30 PM BUF@DEN and 8:15 PM LA@SEA.** (A Wednesday game looks unusual; confirm it before scheduling.)
- `docs/scheduling.md` says a game that gets no pick sends nothing; the "PICK MISSING" alert only runs inside a Claude session.

**Fix and test.** A read-only check that compares each week's kickoffs with the job table, and a post-lock check that every game has a prediction row, with an alert. Test on weeks 3-10 history: it should flag exactly the 13 games above. Forward test: weeks 11-18, target zero silent misses.

### 5. Medium. "No move means away" decides a quarter of picks, and its probability is an artifact

**Evidence.** 25 of 105 live picks had drift 0 and went to away (14-11). In the code, ties get P(home) 0.474 (my fit, any market or total), so P(away) 0.526. The residual distribution is fit on closes of which 55% are whole numbers (`r = margin + close`; P(r = 0) is 2.7% overall and 5.0% among whole-number closes). That mass of exact pushes is counted as "not home" when a half-point market equals the pool line. For a half-point market the true tie probability is about 50/50 (a guess; Auditor B owns calibration). The backtest drift-0 group was 51.6% (`phase7_report.md`, N=699).

**Why it matters.** Not a grading bug, but the 0.526 is not evidence of an away tilt, and the dashboard shows a confident-looking probability for a coin flip.

**Fix and test.** No change proposed yet. Test: on 2007-2024 half-point-market ties, the away versus home cover rate with a 95% interval, split 2007-2016 and 2017-2024; forward weeks 11-18 as a tracked comparison only.

### 6. Medium (hygiene). More than half the code never affects a pick

**Evidence.** Static import trace from the live entry points: about 5,985 of 15,386 lines are reachable; **9,401 (61%) are research or backtest only** (gamesim, projection v4-v6 evals, backtests). Even inside the live tree, the dashboard (1,704 lines), the player model (`features/players_v3.py` 312, `models/players_v3_live.py` 127), the projections, hybrid and the key-number shadow never change a pick. The decision itself is under 100 lines.

**Why it matters.** Every extra piece is a place the live path can break (week 10's missed games came from a push conflict in the capture files, fixed by the `.gitattributes` change in PR #66).

**Fix.** After the batch 6 run (week 18), move research code to a separate package; do not touch `gamesim` before then (frozen constants, pre-registered). Test: the 279 passing tests plus a golden run that replays weeks 3-10 and reproduces every stored pick and grade.

### 7. Medium. Sample size: the live test cannot answer the question this season

105 games, 56-49. Detecting a true 54% versus 50% needs roughly 600 games for 80% power (normal approximation, my estimate). At 227 games at most this season, the 95% interval on the win rate would still be about ±6.5 points. Decide on a rule fixed in advance (for example the paired comparison already registered for batch 6) rather than on the 256-game threshold alone.

### 8. Low. Workflow and dashboard operations

- `publish-dashboard.yml`: crons are UTC and now an hour early versus their ET labels (`30 21 * * 0` is 4:30 PM EST, labelled "~5:30 PM ET"). The commit loop never aborts a half-done rebase and never fails the job if every push fails, so the dashboard can go stale silently (the Streamlit staleness on Nov 16 was a different cause, but this one is possible). Still open from the previous audit (findings 8 and 11).
- `lock-run.yml` interpolates `inputs.*` straight into shell (`game_id`, `window_minutes`, `lead_minutes`). Open (previous finding 10); low risk because only you can dispatch.
- `final.run` uses the schedule loaded at job start, before waiting up to about 75 minutes, so same-day finished games are not in the fit. No pick effect (the fit is on past seasons).
- Test gaps: no test that the pick equals the sign of drift, none that the dashboard verdict equals the live record, none for a stale Pinnacle row.

## Checked and found fine

- **Grading.** Independent re-grade from `predictions.csv` plus nflverse scores: 56-49 on 105, 0 pushes (all pool lines are half-points), the same as `live_record.md` plus the Monday game, and the dashboard "Official pick" row. The sign convention (home covers when margin > -spread) matches `grading.py`.
- **Leakage in the live pick.** `fit_dist` and `fit_total_dist` use only games with `kickoff_utc < now` and a result. The market comes from captures at or before the pick. The projection models fit to games before the current week.
- **Market input quality.** Pinnacle line age at pick: median 3.6 minutes, 2 of 83 older than 30 minutes (CAR@GB 44, LAC@BAL 66; both equal the median). OddsPapi-sourced Pinnacle lines (14 picks) differ from the nflverse close by 0.25 points on average versus 0.23 for the direct feed. The median and Pinnacle differ by 0.17 on average (max 2.0).
- **Pool-line transcription.** 130 lines from week 3 on agree with the all-book median captured nearest the screenshot time (mean absolute gap about 0.3-0.7 points by week). **One outlier: 2026 week 10 SEA@LV, recorded home +3.5 while the market at that time was +6.5 and the close +6.5.** That game was not picked, so the record is unaffected; please check it against your screenshot because it feeds the CBS-line study and batches 2 and 6. Other lines 3+ points from the close are explained by real moves.
- **Earlier audit items now fixed.** Blind-fallback split labelled in `live_record.md` (finding 1), the tie-break (3), the push race (6, PR #66), unquoted source rows (7), frozen-line grading and the duplicate guard (PR #63).
- **Still open from the earlier audit.** Findings 2 (denominators, see issue 2), 8, 9, 10, 11 above.
- **Tests.** `pytest`: 279 passed locally excluding `test_batch6.py` and `test_gamesim_xgb.py`, which need `xgboost` (CI installs it through the `dev` extra).

## Suggested order (all need your approval)

1. Pre-register the weeks 11-18 primary test and its stated power (issue 1). No code.
2. Fix the Season Drive verdict to live-only (issue 2).
3. Add the weekly coverage and missing-pick check; schedule the nine one-off jobs (issue 4).
4. Verify SEA@LV in `league_lines.csv`.
5. Start the test ledger (issue 3).
6. After week 18: run batch 6 once, then consider simplifying (issue 6).
