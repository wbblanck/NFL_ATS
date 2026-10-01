# NFL Player Props: Confirmation Pre-registration (step 2 of 2)

Committed before any 2025 or 2026 prop line was fetched. Step 1: `docs/props_preregistration.md` (2024 =
exploration). Exploration output: `docs/props_explore_2024.txt` (script `scripts/props_explore_2024.py`).
Code for this test: `engine/backtest/props_confirm.py` (`run([2025])`), known-answer checks in
`tests/test_props.py` (a planted disagreement effect passes; none fails).

## What the 2024 exploration found (all hypotheses, not results)

- Unders won 52.6% of 13,854 over/under quotes, and de-vigged prices sat about 2 points too high on the over
  in every probability band; but books charge more for the under, so always-under returned −2.1%. Not taken
  forward (already unprofitable on the exploration season).
- Anytime TD "yes" lost at every price band (−47% on longshots below 10% implied). Not a bet.
- Where books post different lines for the same player-game-market, the under at the highest line won 62.4%
  (n = 189, ROI +17.0%). **Weak support:** 183 of the 189 bets come from one week (2024 week 15, the only week
  FanDuel and BetRivers appear), and every under won 57.9% that week. Against that week's own baseline the
  edge was +7.3% ROI. The under at the lowest line was +0.8% over baseline.
- Data caveat found while exploring: some BetMGM quotes are implausible pregame prices (e.g. 1.5 passing TDs at
  +220/−300 while DraftKings had −115/−115), so Action Network's records can hold in-game or stale prices. A
  price screen is part of the rules below. Even screened, these data cannot show that two books' quotes were
  available at the same moment.

## Hypothesis taken forward (one; no Bonferroni needed)

**H1** Where at least two books post different lines for the same player-game-market, bet the under at the
highest line, at the best under price among the books at that line.

Screen and rules (code: `screened`, `disagreement_bets`): real books only; over/under markets except passing
TDs and interceptions; both prices present; de-vigged P(over) in [0.35, 0.65]; hold < 10%; the lines differ by
at most 15% of the lower line (floored at 1); pushes dropped; one bet per player-game-market. Join to outcomes
as in `engine/backtest/props.py` (player who played with no stat row = 0; no snaps = void).

## Decision (season 2025, all regular-season weeks)

**PASS** only if all hold: n ≥ 30 bets in ≥ 10 different weeks; the week-clustered 95% interval of ROI (under,
at the recorded price) has its lower end above 0; and the 95% interval of ROI minus the same weeks' baseline
(every screened DraftKings under, one per player-game-market) has its lower end above 0. The bootstrap resamples
whole weeks, with the same draw for the bets and the baseline.

Reported, not deciding: H2 (under at the lowest line), books at the bet, win rate. 2026 is not used here.
