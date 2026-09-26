# Projection Model v5.1 (`proj-sim-v51`): Pre-registration, with stop rule

Committed **before** any v5.1 component was built or any v5.1 result seen.

## Stop rule

**If v5.1 fails any validation check below, the projection-distribution track stops.** v3 stays the tracked
projection, the failure is reported, and work moves on. This is the last attempt in this series:
v4, v4.1, v5, v5.1.

## Why v5.1: diagnosis of v5 (training seasons only)

1. **Too many drives, all in the second half.**
   - First half: 11.26 simulated vs 11.32 real drives per game. Second half: **12.04 vs 11.39**.
   - v5 used one "final two minutes" state for both halves. First-half endings (hurry-up) and fourth-quarter
     endings (leading teams kneel and run clock) behave oppositely, and the shared state gave late fourth-quarter
     drives first-half durations.
   - The extra 0.29 drives per team explain the +0.57 points (+2.5%). Drive durations overall match: 158.3 s
     simulated vs 158.4 s real.
2. **Key numbers are under-produced** (3: 10.5% vs 14.2%; 7: 6.2% vs 8.7%). "Trailing 1–8" merges a team that
   needs a FG (down 1–3) with teams that need a TD (down 4–8), and the endgame choices that make 3- and 7-point
   finishes happen at exactly those margins.
3. **Cross-team TD correlation is too low** (0.053 vs 0.158). Score state alone explains a third of it. v4.1
   found a shared game-environment effect (TDs up and FGs down for both teams), which v5 lacks.

## Changes from v5 (everything else unchanged, including data, means, OT rules, smoothing, 20,000 simulations)

### 1. Finer states: 9 score buckets × 5 periods = 45 cells

- **Score buckets** (offense perspective): ≤ −17, −16…−9, −8…−4, −3…−1, 0, +1…+3, +4…+8, +9…+16, ≥ +17.
- **Periods:**
  - early (Q1–Q3, excluding the last 2:00 of Q2);
  - end of first half (last 2:00 of Q2);
  - Q4 with more than 5:00 left;
  - Q4 from 5:00 to 2:00;
  - Q4 final 2:00.
- **Fitting:** the state dummies get a ridge penalty λ = 2, since some cells are sparse. The intercept and γ
  are unpenalised.
- **Durations:** drawn from the (outcome, cell) pool if it holds ≥ 30 drives, otherwise from (outcome, period).

### 2. Game-environment factor

- **Structure:** one Z ~ N(0, 1) per simulated game. It shifts both teams' drive logits: TD by +a·Z and FG by
  +b·Z.
- **Estimation (simulated method of moments):**
  - (a, b) are chosen on the grid a ∈ {0, 0.1, …, 0.5} × b ∈ {0, −0.1, …, −0.5}.
  - The criterion is the minimum sum of squared gaps between simulated and observed cross-team residual
    correlations (TD_h–TD_a, TD_h–FG_a, FG_h–TD_a, FG_h–FG_a).
  - It uses 500 simulations per game with common random numbers.
- **Seasons:** 2013–2021 for the model used in testing. For the holdout check, the drive model and (a, b) are
  refit on 2013–2018 only.

## Validation checks (any failure ⇒ stop rule)

1. **Data:** TD reconciliation ≥ 99.5%; no neutral game with home = 1; point-in-time rebuild identical.
2. **Drive model:** trailing late has a higher TD share than leading late, in data and in the model.
3. **Training (2013–2021, full model):**
   - points per team within ±0.3;
   - drives per half per game within ±0.3 of observed, **for each half**;
   - TD and FG dispersion within ±0.05;
   - 50%-interval coverage 0.47–0.53;
   - every PIT decile 0.08–0.12;
   - margins of exactly 3 and 7 each within ±1.5 pp.
4. **Out-of-sample dependence (non-circular):** with everything fit on 2013–2018, every entry of the
   [TD_h, FG_h, TD_a, FG_a] residual correlation matrix on **2019–2021** is within ±0.05 of observed.
   - The correlations are checked on seasons the factor was not fit on, since the factor is fit to
     cross-team correlations.
5. **Internal holdout calibration:** with the 2013–2018 fit, 50%-interval coverage on 2019–2021 is 0.46–0.54.

## Evaluation and decision rules

As in v5 (`docs/projection_v5_preregistration.md`):
- an informed test on 2022–2024 and 2025, reporting margin log-likelihood with paired SE vs v3 and v1,
  Monte Carlo error from a second seed, MAE, win log loss, ATS, and calibration;
- v5.1 becomes the displayed projection if its Test A margin log-likelihood beats v3's;
- the live verdict comes after 256 graded games;
- the live pick changes only if v5.1 beats the live model with z ≥ 1.96 **and** has lower log loss on live games.
