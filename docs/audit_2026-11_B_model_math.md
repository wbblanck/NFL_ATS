# Audit B: model math, calibration and complexity (2026-11-19)

Read-only audit of the Official pick and the tracked models (v1, v3, Hybrid, Key-number). Nothing in `src/`, `data/` or the workflows was changed. Written against `main` at c51e678. All 287 tests pass on that commit.

## Headline

**I found no calculation error in the math behind the Official pick, and it cannot be hurting accuracy by being miscalculated. The real findings are different: the Official pick is just "follow the market move", so most of its machinery changes nothing, and the 2026 season cannot prove or disprove skill.**

1. **The Official pick is the sign of the line move.** On the 95 live picks that had a market line (record 49-46 against the pool line), the margin-distribution model agreed with the plain rule "pick the side the market moved toward, away on a zero move" 95 times out of 95. The cover probabilities do not change a single pick.
2. **The realistic ceiling is about 52-54%.** 26% of picks (25 of 95) have a zero move and are coin flips by construction. The average move is 0.84 points, which is worth about +2.4 points of win rate by rule of thumb (a point is worth roughly 2.9 percentage points near the middle of the margin distribution). The model's own stated average win chance on those 95 picks is 53.7%.
3. **The pre-registered 256-game threshold cannot be reached in 2026.** Weeks 3-18 have 240 games in total, and 104 of the 118 played so far are graded. Even a real 53.7% edge would pass a 5% test at 256 games only about 32% of the time.
4. **The tracked v1 and v3 models carry no information against the market and state overconfident probabilities.** v1's disagreement with the closing line has a weight of -0.04 ± 0.08 in a regression of actual margin on 2,096 games (2017-2025). Their good-looking live record (v1 55-40) is within chance and should not be acted on.
5. **The Official probabilities are well calibrated** when tested fresh (walk-forward 2010-2025, 29,225 game-and-line pairs). The "overconfident at 60%+" finding in the Phase 5 report came from using the SBRO opening line as the pool line, not from the model.

Nothing here needs an urgent change. Recommended changes are at the end, each needing Will's approval and a pre-registered test.

---

## Corrections after follow-up work (2026-11-19, see `docs/audit_2026-11_B2_followups.md`)

- The rule-of-thumb win rate of 52.4% (issue 1 and the headline) was too low. Using the out-of-sample win-rate table by move size, the follow-the-move rule's expected win rate on the live mix of moves is **53.6%**, interval 52.7% to 54.4%, one-sided 95% upper bound 54.2%, assuming an unbiased lock-time market.
- Issue 5 said the key-number weights "misallocate mass" by pooling across spreads. That was too strong: weights on actual margins are the better-specified choice, spread-specific weights fit worse, and the coded fit matches maximum likelihood. What stands: it adds nothing measurable to cover probabilities or picks, and its weights drift with the era.

## How the Official pick works (verified)

`final.decide` (`src/engine/picks/final.py:98-131`) takes the lock-time market home spread `c` and the frozen pool line `S`. It computes P(home covers S) and picks home when that is above 0.5 (`final.py:119-120`).

The probability comes from `TotalDist` (`src/engine/models/margin_dist.py:140-179`): all regular-season residuals `r = margin + c` since 2000, rescaled by a width that depends on the game total, sorted, then read off at `(−S + c)`. Home covers when `margin > −S`, which is `r > −S + c`. That is what the code does.

What I checked and found correct:
- **Sign convention.** Negative spread means home favoured. Home covers when margin > −S. nflverse `spread_line` has the opposite sign and is flipped at `final.py:61,73`. Verified against the data: lock-time Pinnacle lines match the nflverse close with mean difference −0.05 points.
- **Empirical tail.** `searchsorted(..., side="right")` gives P(r > x). Half-point pool lines make pushes impossible, so strict inequality is right.
- **Training only on earlier games.** `fit_dist` and `fit_total_dist` filter to games before the pick time (`final.py:57-60, 69-72`).
- **Width model.** `scale(T) = sigma * (alpha + beta*T) / mean|r|` fits `|r|` on the total by least squares (`margin_dist.py:154-162`). No sign or normalisation problem.
- **Tracked-model plumbing.** v1 and v3 are written after the pick is saved (`final.py:395-400`), v3 failures are caught (`final.py:152-157`), and a v1 failure skips that game only. A tracked-model failure cannot block a pick.
- **v1 formulas.** The Poisson-ridge fit, the points convolution, `p_home_cover` and `model_line` (`projection.py:51-159`) are internally consistent. See issue 9 for design weaknesses that are not errors.

## Ranked issues

Ranking is by importance to winning the pool and to reading the results correctly. "Pick impact" says whether the issue changes any pick today.

### 1. The Official pick is a drift rule, so the model machinery is decorative (importance: high, pick impact: none)

Evidence:
- 95 of 95 live picks with a market equal the rule "home if the market is more negative than the pool line, otherwise away" (`data/predictions/predictions.csv`, my replay).
- Official record against the pool line, live picks only, no backtest or reconstructed games: **55-49 on 104 graded**; 9 of those were blind away picks with no market line (6-3), so **49-46 on the 95 market-based picks**.
- Record by size of the move, market-based picks only (win-loss, games): zero move 14-11 (25); ½ point 16-11 (27); 1 point 10-13 (23); 1½ to 2 points 4-9 (13); 2½+ points 5-2 (7). The 1-2 point group is 14-22 on 36 games, below 50% when theory says about 53-55%. That is z ≈ −1.3 and not distinguishable from chance, but it is the one slice worth watching.
- Historical walk-forward calibration (below) shows the empirical, total-shifted, normal and key-number estimators all give the same side whenever the move is non-zero.

Why it matters: it tells Will what the pick really is, that no probability model can improve it, and that any gain has to come from better inputs (the market line and the pool line) or from a different rule, not from tuning the distribution. A simpler, more transparent pick (one line of code) would give identical picks. I do not recommend swapping the code during the season; the value is in knowing it.

Test plan: equivalence test, no accuracy hypothesis.
- Historical: replay every 2026 pick with both rules (done for 95 market-based picks; extend to the 9 median-fallback and 10 schedule-total picks and to every future week).
- Unseen: each week, count disagreements between `argmax_cover_prob` and the drift rule. Pass: zero disagreements apart from a documented zero-move tie rule. A non-zero count means the estimator is doing something I missed; report it.

### 2. 2026 cannot confirm skill: the 256-game bar is unreachable and the test is weak (importance: high, pick impact: none)

Evidence:
- 2026 schedule, weeks 3-18: 240 games (16, 16, 15, 14, 14, 14, 15, 14, 13, 16, 14, 15, 16, 16, 16, 16 by week 3-18; 118 played so far; 104 graded, 1 pending, 13 played games with no graded pick).
- `data/predictions/live_record.md` says no skill claim before 256 graded games.
- At 256 games the standard error is 3.1 points. A one-sided 5% test needs at least 142 wins (55.5%). If the true win rate were 53.7% (what the model itself states), the chance of passing is about 32%; at 52.4% (the drift rule of thumb) it is about 19%. To have 80% power at 53.7% you would need about 1,130 games, roughly 4.7 seasons.

Why it matters: Will could wait a season, see 130-110, and conclude nothing either way. The wins-and-losses count is the noisiest possible way to measure a small edge.

Test plan (proposal, to pre-register before the next lock run):
- Add a low-noise metric: **closing-line value, in points.** For each pick, value = side × (closing Pinnacle spread − pool line), positive when the market ended closer to your side than the pool line. By construction this is nearly the same as the move, so it will be positive, but it checks that the lock-time line is not stale relative to the close. Use the kickoff-time row in `market_captures.csv` if present, else the nflverse close (agrees with the lock line to SD 0.33 on 70 Pinnacle games).
- Historical: nflverse closes 2010-2025 give the expected relationship between move size and win rate (the calibration table below).
- Unseen: 2026 weeks 11-18 live picks (about 100-110 more games).
- Pass: mean value above 0 with the lower 90% bound above 0; separately report the win-loss record as before. One test, no multiplicity correction needed. Fail means the lock line is stale or the market input is wrong, which the second auditor's inputs review should cover.

### 3. Tracked v1, v3 and Hybrid add nothing and are overconfident (importance: medium-high, pick impact: none)

Evidence:
- Regression of actual margin on the closing line plus (v1's margin minus the closing line), games 2017-2025 (weeks 3-18, 2,096 games, standard errors clustered by week): weight on v1's disagreement **−0.038 ± 0.080**. By season it ranges −0.26 to +0.11, never clearly above zero. Script: `scripts/audit_B/v1_shrink.py`.
- v1 margin error against the close: mean absolute error 10.38 vs the market's 9.93 on those games. v1's own predictive margin SD is 16.6 points against an actual SD around the close of 12.8, so its width is 29% too wide (documented in `docs/projection_report.md`: TD variance 2.11 < mean 2.43, FG variance 1.43 < mean 1.58).
- Even so, its disagreement with the pool line is treated at full strength: v1 states an average edge of 6.5 percentage points over a coin flip (mean |p − 0.5| = 0.065) on the 93 games common to Official, v1 and v3; the real value is about zero.
- Live (pool line, live picks only, no backtest): per `live_record.md`, v1 55-40 on 95 market games, v3 52-40 on 92 (3 excluded: injury statuses not yet published), Hybrid 55-49 on 104 (differs from Official on 18 games, 9-9). On the 93 games where all three have picks, Official is 48-45 and v1 is 55-38. They differ on 37 games: v1 right 22, Official right 15. That is a net +7, z = +1.15, not significant. Backtest 2007-2021 vs SBRO open: v1 50.83% (1892-1830) against Official 54.89% (2043-1679); z = −3.51 (from `docs/projection_report.md`).
- v1's reliability on those live games: picks stated at 50-55% hit 29 of 44 (65.9%); picks stated at 55-65% hit 22 of 43 (51.2%). Stated confidence and hit rate are inversely ordered, which is what noise looks like.

Why it matters: a 7-game lead on a tracked model is exactly what tempts a mid-season switch. With five comparators (v1, v3, Hybrid, Key-number, and anything added later) a lead of this size is expected by chance.

Test plan:
- Historical (development data only, already used): the regression above, extended to v3 by re-running its feature build on 2022-2025. Not re-run here because it needs a play-by-play download.
- Unseen: 2026 weeks 11-18 plus the 2027 season. Pre-register one family: {v1, v3, Hybrid, Key-number} each against Official on games where they differ, one-sided exact binomial on differing games, **Holm over 4**. With 4 tests the smallest p must be at most 0.0125 (z ≈ 2.24) and at least 100 differing games each. This tightens the existing Hybrid bar (z ≥ 1.645, `docs/hybrid_tracking.md`).
- Separately, report the regression weight each week-block with a cluster-robust CI. Pass for "worth blending in": weight ≥ 0.15 with lower 95% bound > 0 on at least 150 games.

### 4. The "overconfident" label on the Official probabilities is not supported (importance: medium, pick impact: none)

Evidence:
- `docs/phase5_report.md`: stated 0.653 vs actual 0.554 for p ≥ 0.60 (74 games), stated 0.356 vs actual 0.397 below 0.40, 2010-2021. That test used the SBRO opening line as the pool line. The earlier audit found SBRO and AusSportsBetting opens agree exactly in only 35% of games, so SBRO opens contain noise that looks like a move but is not.
- Fresh test, no opening lines needed (`scripts/audit_B/offset_calibration.py`): for every regular-season game 2010-2025, take the nflverse close, build pool-style half-point lines 0 to ±3 points away from it, fit the Official estimator on earlier seasons only, and compare its probability with how often home covered. 29,225 game-and-line pairs (16 test seasons).

  | Predicted P(home covers) | Pairs | Mean predicted | Actual |
  |---|---|---|---|
  | 0.30-0.40 | 877 | 0.395 | 0.377 |
  | 0.40-0.45 | 7,883 | 0.424 | 0.419 |
  | 0.45-0.50 | 5,738 | 0.467 | 0.467 |
  | 0.50-0.55 | 6,226 | 0.525 | 0.533 |
  | 0.55-0.60 | 6,864 | 0.577 | 0.586 |
  | 0.60-0.70 | 1,637 | 0.605 | 0.611 |

  Log loss 0.68265 and Brier 0.24478 for the total-shifted estimator (the live one); shifted 0.68273 / 0.24482; normal 0.68291 / 0.24491; key-number 0.68253 / 0.24472 (differences of 0.0001, not meaningful).
- Live (pool line, 95 market-based picks): stated average win chance 53.7%, actual 51.6% (49 of 95), z = −0.4. Brier of the stated pick probability 0.2501, log loss 0.6933, i.e. coin-flip level. At n = 95 that cannot distinguish anything (SE 5.1 points).

Why it matters: it removes a worry. The probabilities are fine **if the market at lock is the unbiased centre of the game**, which is also the assumption behind the pick. The previous "simulator Brier 0.289, overconfident" is a different model (the play-by-play simulator) and says nothing about this one.

Test plan: monitoring only, no fix needed. Re-run `offset_calibration.py` each off-season with the new season added. Pass: no reliability bin off by more than 2 standard errors in more than 1 of 6 bins. Unseen: Brier and log loss of the 2026 weeks 11-18 live picks against the pool line, reported with the CI, no threshold (underpowered).

### 5. Key-number shadow estimator is mis-specified and adds nothing (importance: medium, pick impact: none, tracked only)

Evidence:
- `margin_dist.py:54-64`: the key-number weights are observed ÷ expected counts of |margin| = k, pooled over all spreads (w₀ = 0.08, w₃ = 2.81, w₇ = 1.87, others 0.36-1.4). The same weight is then applied to the mass at margin k whatever the game's spread, so a 3-point margin gets 2.8× the mass in a 14-point favourite's game as well as in a pick'em. Real key-number mass depends on the distance between the margin and the spread, not on |margin|.
- Out of sample 2010-2025, on integer closes at 3 and 7 with a half-point move (1,760 pairs): Brier for the key-number estimator 0.24905 against 0.24855 for the live total-shifted one, so it is no better exactly where it should help.
- Live: it disagreed with Official on 20 of 95 games and won 10 of them (`live_record.md`: shadow 49-46). 9 of the 25 zero-move games are picked "home" by the shadow and "away" by Official; both are coin flips there.
- The earlier key-number lead already failed out of sample on 2022-2024 (38-40 on 78 differing games).

Why it matters: it is tracked noise that costs dashboard space and attention. I am not re-proposing the key-number idea as an edge.

Test plan: none needed for an edge. If Will wants it kept for the record, no change. If retired, it is a presentation change only.

### 6. Zero-move games always go "away", with a slightly biased probability (importance: low, pick impact: none)

Evidence:
- The pooled residual distribution mixes integer and half-point closes. Integer closes put 4.8% of games exactly on the close (r = 0); half-point closes have none. The pooled code treats the whole r = 0 mass as "not home", so P(home covers) at zero move is 0.474-0.476 (the live rows show 0.4757, 0.4759, 0.476).
- Actual, 2010-2025 walk-forward, half-point close and an equal pool line (1,973 games): home covered **48.7%** (SE 1.1). So away is right 51.3%, not 52.4% as stated; not significant.

Why it matters: it is why every zero-move pick is "away" instead of being decided by something real. It is harmless: the true edge there is zero or about +1.3 points for away (z = 1.2).

Test plan: no change recommended. If a better zero-move tie-break is wanted, pre-register one candidate (for example "home when the home spread is a favourite") with historical test on 2010-2025 nflverse closes and a Holm bar of 0.05; on current evidence it will not beat 51.3%.

### 7. Training data hygiene (importance: low-medium, pick impact: negligible)

Evidence:
- The share of nflverse closes that are whole numbers (as opposed to x.5) was 49-67% in 2000-2024 and **24.6% in 2025 and 30.7% in 2026**, week by week 7% to 56%. That points to a change in what nflverse records as `spread_line` from 2025, which the model's closes feed on.
- Residual mean by season swings from −2.03 (2006) to +1.15 (2005); SD from 11.4 (2022) to 14.5 (2014). Seasons are weighted equally from 2000.
- Mismatch between what is trained on and what is applied: trained on nflverse closes, applied to Pinnacle at kickoff −20 min. On the 70 live Pinnacle picks, the lock line minus the nflverse close has mean −0.05, SD 0.33, equal in 60% of games and 1 game off by a point or more. The 26 median or other-source rows: mean +0.11, SD 0.55.

Why it matters: negligible for picks (they use only the sign). It can mislead the displayed probabilities if the 2025 change is real.

Test plan:
- Historical: walk-forward 2010-2025 log loss of the Official estimator trained on all history vs the last 10 seasons vs last 5 (reuse `offset_calibration.py`). Pass: the alternative beats all-history log loss by at least 0.0005 and does so in at least 12 of 16 seasons, otherwise leave it.
- Unseen: compare 2026 weeks 11-18 residual mean and SD with the pooled values; flag if either is more than 2 standard errors off.

### 8. v3 has 26 coefficients and only one is clearly real (importance: low-medium, pick impact: none)

Evidence:
- `data/processed/players_v3_model.json`, `docs/players_v3_report.md`: 12 features, 26 coefficients (TD and FG each). Only the quarterback term is large, TD effect exp(2.38 × qb_delta), about 7 SE. Every other coefficient is within 2.4 SE, and the report itself says a few near 2 SE are expected by chance.
- The shrinkage constant k = 500 is the largest value in the grid (report item 10), so the optimum may lie outside it. D = 365.
- The Test A gain (+0.0065 ± 0.0036 per game) falls to +0.0021 ± 0.0021 with the depth-chart starter instead of the recorded starter (hindsight). Only the 2025 test (+0.0156 ± 0.0078) uses honest inputs.
- Against the market, v3 is still no better: Test A 49.9% vs the close, 2025 51.3%; margin error 9.92 vs 9.42 (Test A) and 9.91 vs 9.72 (2025).

Why it matters: 25 of 26 coefficients are fit noise by the report's own account. They cost nothing now because v3 is tracked only, but they add live data dependencies (injury reports, snap counts, depth charts) to the lock run.

Test plan:
- Historical (development data, 2013-2025, already used): non-inferiority test of a QB-only model (v1 × exp(β·qb_delta), 2 coefficients) against full v3 on margin log-likelihood. Pass: the QB-only model is within 0.002 per game of full v3 (the size of v3's honest-input advantage) on each of 2022-2024 and 2025.
- Unseen: the 2026 shadow rows (about 96 games now). Too few for the tight non-inferiority bound; report only, decide after 2027 data.

### 9. v1 internals (importance: low, pick impact: none except through Hybrid on low-move games)

Evidence, none of it an error:
- `PROJ_H = 8` (`final.py:137`) is the smallest value in the tuning grid {8, 16, 32}; tuned on 1999-2006 only, by log loss of the straight-up win. The decay across a season boundary stacks two discounts, 0.5^(Δt/8) with 8 units across the offseason, and a further 0.5 per season (`projection.py:80`), so last season's final game weighs 0.25.
- Poisson count variance exceeds the observed counts (TD var 2.11 < mean 2.43), giving the 29% width problem in issue 3.
- `extra = clip(extra, 0, 2)` (`projection.py:97-98`) undercounts a game with two successful 2-point tries (rare). Scores are modelled as independent between the teams.
- Hybrid (`hybrid.py:7,20`) uses the v1 pick for moves below 1 point, which is 54% of picks (52 of 95 market picks have |drift| ≤ 0.5). Since v1's disagreement with the market has weight about zero, Hybrid is a coin flip on those games, so it cannot beat Official except by luck.

Test plan: covered by issue 3 (Holm family). No separate test; fixing v1 only helps if Will later wants to promote it.

### 10. Drift mixes market movement with book differences (importance: low, pick impact: none)

The pool line is a CBS line from Tuesday. The market input is Pinnacle (or OddsPapi/OddsLink Pinnacle, or the median of books) at lock. The gap between them mixes real movement since Tuesday with the CBS-vs-Pinnacle book difference. The earlier work found the pool line matches individual books exactly only 80-91% of the time. This is not a flaw for the pick: P(home covers the pool line) depends on the gap whatever its cause. It does mean the gap's size tells you little about "who moved". Not worth a test.

## Not covered or limits

- v3's features and the Batch 6 models (Elo + QB, XGBoost) were not rebuilt; Batch 6 is under pre-registration and was left alone.
- The calibration test (issue 4) assumes the market centre is unbiased and uses nflverse closes as the centre. It uses 2022-2025 closing lines in aggregate for calibration only, not the locked simulator holdout's games for any simulator fit, and no AusSportsBetting rows.
- Live samples (95-104 games) cannot confirm or refute anything about calibration.
- Inputs, leakage, grading and workflow checks are Auditor A's.

## Recommended changes, all needing Will's approval

1. **Add the closing-line-value metric to `live_record.md`** (issue 2). Presentation only.
2. **Tighten the tracked-comparator bar to a Holm family of 4** and register it before the next kickoff (issue 3).
3. **Say plainly in the dashboard and docs that the pick is the move rule** and that p is the market-implied probability, not a skill estimate (issues 1, 4).
4. **Retire the key-number shadow and Hybrid from the headline standings** if Will wants fewer moving parts (issues 5, 9). No effect on picks.
5. **No change to the pick rule.** Every alternative I looked at has either failed before or has no test that could pass in 2026.

Reproduction: `scripts/audit_B/` (live checks, v1 shrink regression, offset calibration, key-number table). They read only the repo and public nflverse data, and write only to a temp folder.
