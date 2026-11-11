# Batch 6 amendment 1: paired comparison against the official pick (dated 2026-11-11)

Written 2026-11-11, before the first 2026 week 10 kickoff (Thursday 2026-11-12), in response to an external audit
(finding S5). It **adds** a test family. `docs/batch6_preregistration.md` is not edited: its tests Q and X, their Holm
family of 2, the sample, the run-once rule and the 100-pick minimum all stand exactly as registered. The date of the
commit that adds this file is the registration date; nothing in it may be changed after any week 10+ game is graded.
Research only: nothing here touches the pick pipeline, `predictions.csv` or the live record.

## Why
Q and X are tested against a 50% benchmark. A model can beat 50% and still be worse than the official pick, and only
"beats the official pick on the same games" bears on whether it should ever replace it. This amendment tests that.

## Paired family P (confirmatory, separate from the original family)
- **PQ:** Elo + expected-starter QB (Q) against the official pick.
- **PX:** XGBoost (X) against the official pick.
- Candidates are exactly the registered Q and X forecasts: same code, frozen constants, expected-starter rule, and
  injury-report start years. Nothing is refit or changed for this test.

### Eligible games and what is compared
- 2026 regular season, weeks 10-18, final score available. Week 10 is the first week; the expected-starter rule's
  week-one fallback to the recorded starter therefore never applies.
- A game is in the paired sample only if all of these hold: (1) it has one official prediction in
  `data/predictions/predictions.csv` with `created_at` before `lock_utc` (a `LATE_AFTER_LOCK` row is excluded);
  (2) it has a valid pool line; (3) the candidate produced a side (no tie at its fair margin).
- **Same line for both models.** The line is the pool line stored in the official prediction row (`league_line`), the
  line the official pick was made against. The candidate is graded on that same line. If the official row has no
  pool line, or the stored line differs from the valid line in `league_lines.csv`, the game is excluded from P and
  listed by name. (The original Q and X tests keep using the latest recorded line per game, as registered.)
- Official picks that used a degraded input (`NO_MARKET`, median fallback, `FEW_BOOKS`) stay in the sample: they are
  the official pick. Their count is reported.
- A game the official pipeline missed ("No pick") is excluded. No pick is ever reconstructed or backfilled.
- A half-point line cannot push. Any push is dropped from both models.

### Metric and test
- **Primary metric: correct picks** (covers the pool line), one point per game. No probabilities, ROI or stakes.
- On the paired sample, let b = games the candidate won and the official pick lost, c = games the official pick won and
  the candidate lost, and d = b + c (the disagreements). Agreement games add the same point to both and carry no
  information about which model is better.
- **Test:** one-sided exact binomial, H1: b > c, i.e. P(candidate wins | disagreement) > 0.5, with b ~ Binomial(d, 0.5)
  under H0 (the one-sided exact McNemar test).
- **Multiple testing:** Holm over the family {PQ, PX} at 0.05: smaller p against 0.025, the other against 0.05, stopping
  at the first failure. P is its own family; it is not combined with Q and X. Q and X share most games and many
  sides, so Holm is conservative here. A pass in P is the only result that supports promotion discussion; passing Q or
  X against 50% does not.
- **Minimums:** at least 100 paired games and at least 20 disagreements for a test to be able to pass. Below either,
  the result is reported as inconclusive (not a pass, not evidence of no difference).
- **Pass:** the paired test is significant at its Holm level (which also means b > c).

### Power, stated in advance
Needed candidate-only wins out of d disagreements for a one-sided exact test: at 0.025, 27 of 40 (68%), 33 of 50 (66%),
39 of 60 (65%); at 0.05, 26 of 40, 32 of 50, 37 of 60. With d = 55, the chance to pass at 0.025 is about 8% if the
candidate truly wins 55% of disagreements, 25% at 60%, 53% at 65%, 81% at 70%. The number of disagreements is not yet
known (a guess, not a measurement: 40-60 over nine weeks). A fail or an inconclusive result means "no evidence of
an advantage over the official pick on 2026 weeks 10-18", not "no advantage".

## Reporting standard (every model, same format)
For Q, X and every tracked model (key-number, proj-poisson-v1, proj-players-v3, hybrid) the report states: games
eligible; games with a valid prediction; games graded; games excluded and why (each named); record on the common
matched sample; disagreements with the official pick; candidate-only wins versus official-only wins; net paired
advantage. Models other than Q and X are descriptive here: no p-value from this amendment supports any claim about
them. Pass/fail is reported against pre-set bars only; no candidate is called better without a P pass, and a
descriptive 9-8 on disagreements is not evidence.

## Timing, inputs and limits
- The candidates are deterministic functions of committed code, frozen constants and games played before each week,
  so the single run after week 18 reproduces pregame forecasts; they are not stored pregame. The expected-starter
  input uses the final pregame injury report, which can post after the official pick time; the report states it.
- The paired analysis code (added to `scripts/batch6.py`) is committed before the run and must implement this text
  as written. If the code and this text disagree, this text wins and the discrepancy is reported.
- Sample is 2026 weeks 10-18 only, run once after week 18 is final. The weeks 2-9 and 2022-2025 records stay descriptive.
