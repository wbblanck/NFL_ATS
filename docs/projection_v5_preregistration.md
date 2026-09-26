# Projection Model v5 (`proj-sim-v5`): Pre-registration

Committed **before** any v5 component was built or any v5 result seen.

**Why v5.** v4 and v4.1 failed validation because they draw each game's scoring counts all at once. Real
scoring reacts to the scoreboard. From 2017–2021 training drives, fourth quarter:
- teams trailing by 9+ score a TD on 26.2% of drives and a FG on 6.5%;
- teams leading by 9+ score a TD on 14.1%, and their drives are shorter;
- tied: TD 11.8%, FG 25.8%.

v5 therefore simulates games **drive by drive**.

## Carried over (validated)

- **Fix 1:** play-by-play TD counts.
- **Fix 2:** no home edge at neutral sites.
- **Players and team strength enter through v3's expected counts:**
  - μ_TD and μ_FG = v1 walk-forward rates (with fixes 1–2) × exp(β·x).
  - x: the starting QB's `qb_delta`, snap-weighted injuries (OL, skill; opponent DL, LB, DB), rest, travel,
    division, roof.
  - β is fit on 2013–2021, with D = 365 and k = 500 frozen from v3.

## Drive model (fit on 2013–2021 drives only)

**Drives.** Each drive in the 2013–2021 regular season, from play-by-play `fixed_drive`, with:
- the offense's score differential and the game clock at the drive's first play;
- the result: TD, FG, opponent TD (defensive or return score), or nothing (punt, turnover, missed FG,
  downs, end of half, safety);
- the drive's duration in game-clock seconds.

**Outcome model.** A multinomial logit over {TD, FG, opponent TD} against "nothing":
- η_TD = α + γ_TD · log μ_TD(offense, game) + state terms;
- η_FG = α + γ_FG · log μ_FG(offense, game) + state terms;
- η_OppTD = α + state terms.

**State.** Score bucket × period:
- Buckets: trailing 9+, trailing 1–8, tied, leading 1–8, leading 9+.
- Periods: *early* (Q1–Q3, excluding the last 2:00 of Q2), *late* (Q4 with more than 2:00 left), and
  *final two minutes* (of either half).
- That gives 14 dummy variables per outcome.

Fit by maximum likelihood (Newton).

**Duration.** Each simulated drive's clock use is drawn from the empirical training durations in the same
(outcome, state) cell.

## Game simulation

- **Drives per simulation:** 20,000 simulations per game, with common random numbers across games.
- **Kickoffs:** a random team receives the opening kickoff, and the other team receives in the second half.
- **Clock:** each half has 1,800 s, and drives continue until the half's clock runs out.
- **Scoring:**
  - TD = 6 plus extra points, drawn with p_xp and p_2 from the v1 fit.
  - FG = 3.
  - Opponent TD = 6 plus extra points to the defense.
  - After any score, the team that did not score receives.
- **Overtime (if tied, simplified and disclosed):**
  - A random receiver starts.
  - Drives alternate for up to 600 s, in the "tied, final two minutes" state.
  - The game ends at a TD, or at a FG that is not on the first possession. Otherwise it ends tied.
- **Margin pmf:** (counts + 1/121 on each margin in −60…60) / (20,000 + 1). The floor keeps log-likelihoods
  finite; margins beyond ±60 get only the floor.
- **Monte Carlo error:** every reported log-likelihood is repeated with a second seed, and the difference is
  reported.

## Validation checks (must pass before any 2022–2025 result is read)

1. **Data:**
   - TD reconciliation ≥ 99.5%.
   - No neutral game with home = 1.
   - Point-in-time feature rebuild identical (to 10⁻¹²).
2. **Drive model sanity:**
   - γ_TD and γ_FG are reported with SEs.
   - Trailing late must have a higher TD share than leading late, which the logit must reproduce.
3. **Simulation matches training (2013–2021), with the same bars as v4.1:**
   - Mean points per team within ±0.3 of observed.
   - TD and FG dispersion within ±0.05.
   - Every entry of the [TD_h, FG_h, TD_a, FG_a] residual correlation matrix within ±0.05.
   - 50%-interval coverage of margins 0.47–0.53.
   - Every PIT decile 0.08–0.12.
4. **Key numbers:** the simulated share of games decided by exactly 3 and exactly 7 points, in either
   direction, is each within ±1.5 percentage points of observed (training).
5. **Internal holdout:** refit the drive model on 2013–2018 only, simulate 2019–2021, and 50% coverage must be
   0.46–0.54.

If any check fails, v5 is not scored, and the failure is reported.

## Evaluation (informed test: 2022–2025 informed v4's design; live 2026+ is the clean test)

- **Test A (2022–2024) and Test B (2025):**
  - margin log-likelihood (paired SE vs v3 as specified, and vs v1),
  - MAE,
  - P(home wins) log loss,
  - ATS vs the close,
  - coverage and PIT deciles.
- **Test B also:** ATS vs the CBS open and vs the live model.

## Decision rules (fixed in advance)

- **Tracked projection:**
  - v5 is recorded alongside v3 from its merge onward.
  - It becomes the displayed projection if its informed-test margin log-likelihood beats v3's on Test A.
  - The final verdict is the live paired margin log-likelihood after 256 graded games.
- **Live pick:** unchanged, unless v5 beats the live model against the league line or CBS open with
  z ≥ 1.96 **and** has lower log loss on live games.
