# Audit B follow-ups (2026-11-19): win-rate bound, estimator vs drift, key-number, QB-only v3, new architecture

Read-only. No formulas, picks, data or workflows were changed. Builds on `docs/audit_2026-11_B_model_math.md`. Scripts are in `scripts/audit_B/` (each starts with a one-line description; they write only to `/tmp/audit_B`).

Note: the first line of Will's request arrived cut off ("...iling."). I read the first item as "the win-rate ceiling: separate a rough expected win rate from a statistically supported upper bound". If it meant something else, say so.

## Headline

1. **Expected win rate of the follow-the-move rule: about 53.6% (rough point estimate); statistically supported range 52.7% to 54.4%; one-sided 95% upper bound 54.2%.** That bound holds only if the lock-time market is unbiased. It is not a bound on what the live record can do. The live record (49-46 on 95 market picks) is too small to bound anything: its one-sided 95% upper bound is 60.0%. My earlier rule-of-thumb figure (52.4%) was too low.
2. **The Official probability estimator adds nothing measurable beyond a one-number drift forecaster.** Out of sample (2010-2025), the Official log loss is 0.68265 and the drift-only lookup is 0.68271. The difference per pair is -0.00006, 95% interval [-0.00020, +0.00007]. Both beat a coin flip by 0.0104.
3. **Key-number weights are applied to actual final-margin probabilities (by |margin|), not to market-relative residuals, and that is the better-specified choice.** It beats a market-relative version by 0.118 log points per game and a plain normal by 0.125. The weights are not stable over time, and the gain in cover probabilities is under 0.0005 log loss and not significant. My first report was too harsh on this estimator; the correction is below.
4. **QB-only v3 keeps almost all of full v3's gain.** On identical games, features and fit window (2013-2021), tested 2022-2025 (1,087 games): QB-only +0.0079 per game over v1, full v3 +0.0087. The full model's extra +0.0008 has a 95% interval of [-0.0022, +0.0040]. Neither model carries a detectable weight against the market.
5. **A market-disagreement model cannot be confirmed quickly.** A real weight of 0.25 on a disagreement signal is worth about +0.9 points of pool win rate and needs about 1,360 games (5 seasons) to detect. The proposed architecture and pre-registration are in section 5.

---

## 1. Rough expected win rate versus a statistically supported upper bound

**What each number means.**
- *Rough expected win rate (53.6%)*: what the "follow the market move" rule wins if the lock-time market is the unbiased centre of the game, using the live mix of move sizes. It is a model-based expectation, not a result.
- *Statistically supported range (52.7% to 54.4%)*: how uncertain that expectation is from two sources: the historical win-rate-by-move-size table and the small live sample of move sizes. It still assumes market efficiency.
- *Upper bound from live results (60.0% one-sided 95%, 61.6% two-sided)*: what the actual 2026 record can say by itself. It says almost nothing.

**Method** (`followup_A_ceiling.py`, reads the out-of-sample table from `followup_B_scoring.py`).
- Historical table: for every regular-season game 2010-2025 (4,175 games, nflverse closing line as the market), build half-point lines 0 to ±3.5 away from the close and record how often the side the rule picks (home if the pool line is easier for home, otherwise away, zero move goes away) wins. 29,225 pairs. Cell sizes are 1,973 or 2,202.
- Live mix: the 96 live picks that have a market and a pool line (move size from `data/predictions/predictions.csv`; one move is 5.5 points and is capped at the 3.5 cell).

| Move size (points) | Win rate of the rule, 2010-2025 | Live picks (count) |
|---|---|---|
| 0 | 51.3% (away) | 25 |
| 0.5 | 52.4% (51.8% / 53.0% by side) | 27 |
| 1.0 | 54.4% (53.4% / 55.5%) | 25 |
| 1.5 to 2.0 | 56.7% | 12 |
| 2.5 and more | 59.9% | 7 |

- **Expected win rate on the live mix: 53.6%.** Bootstrap, resampling both historical games (by game) and live moves: 95% interval **[52.7%, 54.4%]**, one-sided 95% upper bound **54.2%**. History alone: [53.0%, 54.2%]; live move mix alone: [53.1%, 54.1%].
- Season-to-season stability of the table: win rate by move size varies across seasons by about the sampling noise (for example at move 1.0, season SD 1.7 points against sampling SD 3.2), so there is no sign of a drifting edge.
- The rule of thumb I quoted before (50 + 2.9 × average move = 52.4%) understated it. Key numbers make half-point moves worth more than the middle-of-the-distribution density suggests (a ½-point move across 3 or 7 is worth much more than 1.5 points).

**What it does not show.** If the market at lock is biased, or the pool line behaves unlike a synthetic offset from the close, the numbers change. The only real check is the live record, and 49-46 on 95 is consistent with 53.6% (z = -0.4) and with 50%.

**To reach 80% power** at a true 53.6%: about 1,130 games (a 3.6-point edge, one-sided 5%). At 52.4%: about 2,680.

## 2. Does the Official estimator add information beyond the drift rule?

**Test** (`followup_B_scoring.py`). Walk-forward, 16 test seasons (2010-2025), each fit only on earlier seasons. The same 29,225 game-and-line pairs scored by proper scoring rules (log loss and Brier) for six forecasters, all giving P(home covers the line):

| Forecaster | Uses | Log loss | Brier |
|---|---|---|---|
| Coin flip | nothing | 0.69315 | 0.25000 |
| Drift-only logistic | line offset only | 0.68259 | 0.24475 |
| Drift-only lookup | exact offset (also encodes whole vs half close) | 0.68271 | 0.24481 |
| Normal | offset and one SD | 0.68291 | 0.24491 |
| Shifted empirical | offset and the pooled residuals | 0.68273 | 0.24482 |
| **Official (total-shifted)** | offset, pooled residuals, game total | **0.68265** | **0.24478** |

Same table restricted to live-like offsets (|offset| at most 2, 18,673 pairs): Official 0.68800, drift-only lookup 0.68806, logistic 0.68800, coin 0.69315.

Paired differences, bootstrap by game (negative means the first forecaster is better):

| Comparison | Log loss difference | 95% interval | Brier difference | 95% interval |
|---|---|---|---|---|
| Official minus drift lookup, all | -0.00006 | [-0.00020, +0.00007] | -0.00003 | [-0.00010, +0.00004] |
| Official minus drift logistic, all | +0.00006 | [-0.00006, +0.00017] | +0.00003 | [-0.00003, +0.00009] |
| Official minus drift lookup, |offset| ≤ 2 | -0.00006 | [-0.00022, +0.00009] | -0.00003 | [-0.00011, +0.00004] |
| Drift lookup minus coin flip, all | -0.01044 | [-0.01173, -0.00908] | -0.00519 | [-0.00583, -0.00453] |

- Official beat the drift lookup in 10 of 16 seasons (no pattern).
- Stacking test: regress the outcome on the logit of the drift lookup and on the Official's extra move beyond it. Coefficient on the extra: 1.24 (SE 0.59, p = 0.034), but the extra itself is tiny (SD 0.022 logit units, average 0.43 percentage points). A coefficient near 1 with a wide interval says "the extra is probably real but is worth about 0.0001 log loss". It does not change a single pick.

**Verdict.** All the information in the Official's probability is in the offset between the pool line and the market. The extra (total-dependent width, pooled-residual shape) is worth about 0.0001 log loss, which no sample you will ever have can resolve. The probability model can be replaced by a one-parameter function of the offset with no loss.

## 3. Key-number estimator: what the weights apply to and whether the distribution is specified correctly

**What the code does** (`src/engine/models/margin_dist.py:48-73`): the base is a normal probability for the final margin k centred at −c (the market), with one pooled SD. The weight w_|k| multiplies the base probability of final margin k, indexed by |k| from 0 to 20 (weight 1 beyond), then each game's probabilities are renormalised. So the adjustment is applied to **actual-margin probabilities, not to market-relative residuals (k + c).** The weights come from a one-pass ratio of observed to expected counts of |margin| (`_fit_keys`, lines 54-64).

**Tests** (`followup_C_keynum.py`, `followup_C2_keynum_specification.py`). Walk-forward 2010-2025, 4,175 games, mean log probability of the actual final margin (a proper scoring rule for the whole distribution). Higher is better.

| Conditional distribution | Mean log P(actual margin) |
|---|---|
| Key-number as coded (actual-margin weights, ratio fit) | -3.8638 |
| Actual-margin weights, maximum-likelihood fit | -3.8639 |
| Same weights, time-decayed (half-life 8 seasons) | -3.8624 |
| Same weights, last 10 seasons only | -3.8627 |
| Weights by spread bucket (4 buckets) | -3.8988 |
| Market-relative weights (on |margin + market|), max-likelihood | -3.9823 |
| Normal, pooled SD | -3.9889 |
| Empirical residual by whole/half close (pooled residuals, i.e. the Official's family) | -4.0053 |

Paired differences per game with 95% intervals (positive means the first is better): coded vs normal +0.1251 [+0.1077, +0.1424]; max-likelihood vs coded -0.0001 [-0.0011, +0.0010]; market-relative vs actual-margin -0.1183 [-0.1344, -0.1015]; empirical residual vs actual-margin -0.1414 [-0.1594, -0.1236]; time-decayed vs all-history +0.0016 [+0.0004, +0.0027]; bucket-specific vs pooled -0.0348 [-0.0596, -0.0142].

**Findings.**
1. **Weights belong on actual margins.** The real structure is atoms at final scores (3, 6, 7, 10, 14), and the actual-margin version fits 0.118 log points per game better than the market-relative version.
2. **The ratio fit is as good as maximum likelihood** (difference -0.0001), so the fitting shortcut is not a problem.
3. **Not stationary.** Share of games ending exactly 3: 16.9% (2000-04), 14.5%, 14.3%, 14.7%, 14.6% (2020-25). Exactly 7: 10.3%, 9.2%, 8.8%, 9.9%, **7.7%**. Exactly 6: 4.9%, 5.3%, 5.7%, **7.1%**, 6.8% (the 2015 extra-point change). The coded estimator, fit on all history, predicts 9.6% for 7 against 8.7% observed pooled (and it would be worse against the last six seasons) and 15.6% for 3 against 14.5%. Time-decayed weights give a small but significant gain (+0.0016).
4. **More structure overfits.** Spread-bucket weights score worse (-0.035). The normal base also ignores the game total.
5. **The value for cover probabilities is tiny.** At live-like lines the best key-number variant (spread buckets, all history) scores 0.68753 log loss against 0.68800 for the Official, -0.00047 with 95% interval [-0.00163, +0.00076]. Every variant is within ±0.0005 of the Official, none significant. At offsets of 0.5 or less all variants are slightly worse than the Official.
6. **No zero-move tie-break edge.** On 1,973 half-point-close games where pool line equals market, the key-number models pick home about 41% of the time and win 50.2% to 50.4%; always-away wins 51.3%. By period (exploratory, not a test): 2010-2021 away 52.1% vs key-number 49.5-49.7%, 2022-2025 away 49.4% vs key-number 51.9-52.0%. The sign flips between periods, which is what noise looks like.

**Correction to my first report (issue 5).** I said the weights "misallocate mass" because they are pooled across spreads. That was too strong. Pooling is right for actual-margin atoms, spread-specific weights fit worse, and the coded estimator matches a maximum-likelihood fit. What remains true: it adds nothing measurable to cover probabilities or picks, its weights drift with the era, and the 3 and 7 shares are overstated by about 1 point for recent seasons.

## 4. QB-only v3 against full v3

**Design** (`followup_D_prepare.py`, `followup_D_v3_qb_only.py`). Both models use the pre-registered pipeline (`engine.backtest.players_v3_eval`): same 6,814 team-games, same v1 rates, same features built once, no rows dropped, same frozen constants (D = 365, k = 500, tuned on training only), both fitted by the same offset-Poisson code on 2013-2021 only (2,320 training games), both scored on identical games in 2022-2025. The only difference is which columns enter the fit. Reproduction check: full v3 gain over v1 on 2022-2024 is +0.0065 (reported +0.0065) and on 2025 +0.0152 (reported +0.0156).

Mean margin log-likelihood per game (higher is better; same games in each row):

| Block | Games | v1 | QB-only (2 betas) | Full v3 (12 features) | All except QB (11) |
|---|---|---|---|---|---|
| Training 2013-2021 | 2,320 | -4.0161 | -4.0094 | -4.0081 | -4.0140 |
| 2022 | 271 | -3.9377 | -3.9386 | -3.9415 | -3.9402 |
| 2023 | 272 | -4.0142 | -4.0069 | -4.0109 | -4.0180 |
| 2024 | 272 | -4.0372 | -4.0273 | -4.0171 | -4.0253 |
| 2025 | 272 | -3.9762 | -3.9609 | -3.9610 | -3.9759 |
| 2022-2024 | 815 | -3.9964 | -3.9910 | -3.9899 | -3.9946 |
| 2022-2025 | 1,087 | -3.9914 | -3.9835 | -3.9827 | -3.9899 |

Paired differences per game (95% bootstrap interval):
- 2022-2025, QB-only minus v1: +0.0079 [+0.0027, +0.0134]. Full v3 minus v1: +0.0087 [+0.0021, +0.0149]. **Full v3 minus QB-only: +0.0008 [-0.0022, +0.0040].**
- 2022-2024, full minus QB-only: +0.0011 [-0.0024, +0.0047]. 2025: -0.0001 [-0.0068, +0.0065].
- By year, full minus QB-only: 2022 -0.0029, 2023 -0.0040, **2024 +0.0102 [+0.0035, +0.0187]**, 2025 -0.0001. One season in four favours the full model; that is what chance looks like across four looks, and nothing pooled supports it.
- The 11 non-QB features alone: +0.0015 [-0.0020, +0.0050] over v1 on 2022-2025.
- In training the full model gains +0.0013 over QB-only; out of sample +0.0008. It is not overfitting badly, but the extra is not distinguishable from zero.
- QB-only coefficient: TD effect 2.76 (SE 0.40), FG 0.49 (SE 0.47).

**Information against the market** (regress actual margin on the close and on the model's disagreement with the close; the weight is how much of the model's disagreement is real; 2022-2025, 1,087 games, robust SE):
- v1 -0.020 (SE 0.114); QB-only +0.060 (0.119); full v3 +0.115 (0.116); non-QB 11 +0.029 (0.112). None is distinguishable from zero. Margin error: close 9.494, QB-only 9.928, full v3 9.917, v1 9.982.

**What "genuinely out of sample" means here.** Fitted only on 2013-2021, scored on 2022-2025. But those seasons were already seen in the earlier v3 evaluation (the full v3 decision), and recorded starters for 2013-2024 carry a small hindsight; both models use the same inputs, so the comparison is fair, but not clean of hindsight. The 2026 live shadow rows (about 96 games) are the only untouched data, too few to settle a 0.001 difference.

**Verdict.** The QB-only model carries 91% of the gain (+0.0079 of +0.0087) with 2 coefficients instead of 26. I cannot show the full model is better, and I cannot prove it is not (the upper end of the interval is +0.0040). Non-inferiority within 0.002 is not established; non-inferiority within about 0.004 is (the interval's upper end is +0.0040). Neither model has a measurable weight against the market.

## 5. Proposed market-disagreement model: architecture, pre-registration and holdout plan

Proposal only. Nothing here is implemented. It must stay in the shadow lane, never touching the pick path, and Batch 6's pre-registration is untouched.

### 5.1 Purpose and target
Predict the part of a game's result that is not already in the lock-time market. Target: the market residual r = final margin + c, where c is the home spread at lock (Pinnacle at kickoff minus 20 minutes, or the flagged fallback). The pool-relevant output is P(home covers the pool line S).

### 5.2 Layers
1. **Market baseline B1 (no new information).** The best-specified market-only distribution: actual-margin key-number atoms with time-decayed weights over a normal base centred at −c, width by total. This replaces the pooled-residual estimator as the comparator because it scores 0.14 log points per game better on the margin distribution (section 3). Its picks equal the drift rule.
2. **Disagreement layer.** μ(x) = Σ over blocks b of s_b × (β_b · z_b), where z are standardised features **orthogonalised against c and the total** (so they cannot just re-express the market). The prediction is the baseline with its centre shifted: centre = −c + μ. Each block has one scale s_b in [0, 1] (shrinkage), fitted by ridge/nested walk-forward, so a block with no signal collapses to zero and the model reverts to the drift rule.
3. **Fallbacks.** Any missing input zeroes that block. If every block is zero, the model is exactly the drift rule.

### 5.3 Feature blocks (at most four, fixed before any test)
| Block | Contents | Historical test possible? | Notes |
|---|---|---|---|
| Q | qb_delta of the lock-time starter minus the market-implied QB expectation | Yes, 2013-2025 (already seen) | Market prices QBs; the test is whether it prices them fully |
| I | OL, skill, DL, LB, DB injury loads (one shared scale) | Yes, 2013-2025 (already seen) | Status reports must be published before lock |
| X | rest, bye, short week, travel, division, dome (one shared scale) | Yes | Each was within 2.4 SE in v3 |
| M | market microstructure: Pinnacle open-to-lock move, gap between Pinnacle and the book median, total move, number of books | **No: lock-time multi-book history does not exist before 2026** | Forward-only; the capture jobs already collect most inputs |

The efficiency-stat, ATS-form, simulator and key-number ideas that already failed are **not** candidate blocks.

### 5.4 Pre-registration (draft, to commit before any 2026 weeks 11-18 data are scored)
- **Hypotheses.** H_Q, H_I, H_X, H_M: each block improves the mean log score of the actual margin over B1, one-sided.
- **Primary metric.** Paired mean log probability of the actual final margin, B1 versus B1 plus block, with a game-level bootstrap interval. **Secondary:** cover log loss and Brier at offsets within ±2 of the lock market. **Tertiary, descriptive only:** win-loss against the pool line.
- **Family.** Holm over the four blocks at 0.05. A block counts as passing only if its lower one-sided 95% bound on the score gain is above zero **and** its fitted weight on the disagreement (regression of margin on close and block disagreement) is at least 0.15 with a lower 95% bound above zero.
- **Minimum useful effect.** A weight of 0.25 (worth about +0.9 points of pool win rate on the live mix of move sizes, simulation in `followup_E_power.py`). A weight of 0.15 is worth only +0.4 points and is not treated as useful.
- **Kill rule.** If, after the 2028 season (about 650-760 holdout games, standard error about 0.14), the upper 95% bound on the pooled weight is below 0.25 (the minimum useful effect), the disagreement layer is retired.
- **Frozen artifacts.** Feature definitions, orthogonalisation, shrinkage procedure, training window, random seeds and the committed code hash are fixed in the commit. Nothing is tuned after the holdout opens.
- **Switching.** No effect on picks. Promotion would need all of the above plus Will's approval.

### 5.5 Data tiers and holdout
| Tier | Data | Use |
|---|---|---|
| Development | 2013-2021 (rolling-origin, nested) | All fitting, shrinkage and selection |
| Burned | 2022-2025 | Already used by the v3, v1, key-number and simulator work. Reported as a consistency check; **cannot confirm** anything |
| Holdout H1 | 2026 weeks 11-18 live and shadow (about 100-110 games), frozen at registration | First look; underpowered by design |
| Holdout H2 | 2027 full season (about 272 games) and later seasons | Confirmatory, sequential |
| Forward-only logging | All books, every capture, from now on | The only way block M can ever be tested |

**Sequential testing.** Looks at the end of 2026, 2027, 2028 and 2029 with an O'Brien-Fleming alpha-spending schedule on the pooled holdout, so an early lucky streak cannot confirm anything. Nothing is confirmed on H1 alone.

### 5.6 Power: be honest about what can be confirmed
Weight on the disagreement signal, disagreement SD 3.45 points (the v1 value; a quieter feature set is worse), margin SD against the market 12.8, one-sided 5%, 80% power:

| True weight | Shift SD (points) | Win-rate gain in the pool | Games needed | Seasons |
|---|---|---|---|---|
| 0.05 | 0.17 | +0.1 | 34,000 | 125 |
| 0.10 | 0.35 | +0.2 | 8,500 | 31 |
| 0.15 | 0.52 | +0.4 | 3,780 | 14 |
| 0.25 | 0.86 | +0.9 | 1,360 | 5 |
| 0.35 | 1.21 | +1.5 | 690 | 2.6 |
| 0.50 | 1.73 | +2.5 | 340 | 1.3 |

With SD(disagreement) = 1.5 the counts are 5 to 6 times larger at small weights. So: only a weight near 0.5 can be confirmed on holdout within two seasons. A smaller real weight can be neither confirmed nor ruled out on holdout alone in a useful time. The development tier is larger: 2,320 games give a standard error of about 0.08 on a weight, so it can detect a weight of 0.25 with roughly 90% power. That is why v1's estimate on 2,096 games (-0.04 ± 0.08, upper 95% bound about +0.09) already rules out a useful v1 weight. v3's 2022-2025 estimate (+0.12 ± 0.12, 1,087 games) cannot rule out 0.25. So the earlier failures are informative for weights of 0.25 or more, and uninformative for smaller ones.

My recommendation: do not build this model for the pool yet. Run the development-tier test first (2013-2021, nested walk-forward, block Q and block I and X only, which needs no new data). It has about 90% power for a useful weight of 0.25, and a clean negative there closes the question cheaply. Block M can only be tested forward, so start the forward-only logging in the last row of 5.5 now; it costs nothing and keeps the option open. Holdout confirmation is only worth running if the development tier shows an estimate near or above 0.25.

## Files
Scripts: `scripts/audit_B/followup_A_ceiling.py`, `followup_B_scoring.py`, `followup_C_keynum.py`, `followup_C2_keynum_specification.py`, `followup_D_prepare.py`, `followup_D_v3_qb_only.py`, `followup_E_power.py`. Run `followup_B_scoring.py` before `followup_A_ceiling.py`, and `followup_D_prepare.py` before `followup_D_v3_qb_only.py`.
