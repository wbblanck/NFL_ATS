# Projection Model v4 (`proj-drives-v4`): Pre-registration

Committed **before** any v4 component was built or any v4 result seen. v4 corrects the errors found in the
2026-09-26 audit of v1/v3. It adds no new football variables. Candidate variables (kicker quality, turnover
luck, pace) will each get their own pre-registration later.

## Disclosure: how these fixes were found

The audit that found the problems used diagnostics on **2022–2025**, which are v3's test seasons:
- TD dispersion 0.78;
- cross-team TD residual correlation +0.18;
- model margin SD 16.4 against 12.7 realised.

That makes 2022–2025 **not a clean test** of whether v4 beats v3. The *decision* to fix these things was
informed by those seasons, even though no v4 parameter will be fit on them. Therefore:
- The 2022–2025 comparison is reported, but labelled **"informed test"**.
- The clean test is **live 2026 onward**, where v4 and v3 are both recorded at lock and graded.
- A stage-2 check confirms that each problem also exists in the **training seasons** (2013–2021). If a problem
  does not appear in training, its fix is dropped from v4.

## Fixes

### 1. Touchdowns counted from play-by-play
- **The problem:** nflverse `team_stats` misses ordinary passing and rushing TDs. In 2023–24, 39 of 1,088
  team-games (3.6%) have one TD too few.
- **The fix:** v4 counts TDs as play-by-play plays with `touchdown == 1`, credited to `td_team` (regular season).
- Field goals, PATs and safeties stay from `team_stats`; they reconcile with the score once TDs are corrected.

### 2. Neutral sites carry no home advantage
- The home indicator is 0 for **both** teams when the schedule's `location == "Neutral"`.
- This applies in fitting and in projection.

### 3. Score distribution: a drive model instead of independent Poisson counts
- **Drives:** each game has drive counts (N_h, N_a), drawn from their **empirical joint distribution** in the
  training seasons, counted as distinct `fixed_drive` values per possession team.
- **Each drive ends in:** a TD with probability p_td, a FG with p_fg, or nothing.
  - p_td = μ_td / E[N] and p_fg = μ_fg / E[N].
  - μ comes from the same regressions as before, so the expected TDs and FGs are unchanged.
- **After a TD:** 0, 1 or 2 extra points, as in v1.
- **What this produces:**
  - TD counts vary less than Poisson (binomial given N).
  - TD and FG within a team are negatively related (one drive, one result).
  - The two teams' scores are positively related through the shared number of drives.

  The last two are the patterns the audit found.
- **Disclosed approximation:** defensive and return TDs are treated as drive outcomes.

### Everything else is unchanged from v3
- Same features, and the same D/k grid, tuned again on 2013–2021 because the TD targets change.
- Same base v1 ratings (H = 8, λ = 5), recomputed with fixes 1–2.
- Same offset-Poisson fit of β on 2013–2021.

## Validation checks (must pass before any 2022–2025 result is read)

1. **TD reconciliation.** points − 6·TD − PAT − 3·FG − 2·safeties is in {0, 2, 4, …, 2·TD} (2-point
   conversions) for ≥ 99.5% of team-games 1999–2025. Exceptions are listed.
2. **Neutral sites.** The count per season is listed. No neutral game carries home = 1.
3. **The problems exist in training (2013–2021).** Under the v3-style Poisson model on training seasons:
   - TD dispersion < 0.95, **or** cross-team TD residual correlation > 0.05, **or** the 50% interval covers
     > 55% of results.

   Otherwise fix 3 is dropped and v4 = fixes 1–2 only.
4. **The drive model fits training.** On 2013–2021, v4's implied figures are reported next to the observed ones:
   - TD and FG dispersion,
   - cross-team TD correlation,
   - 50%-interval coverage.

   Pass: coverage in [0.46, 0.54], and correlation within ±0.07 of observed.
5. **Point-in-time.** The v3 feature test is repeated. The drive distribution uses training seasons only.

## Evaluation

- **Informed test** on Test A (2022–2024) and Test B (2025), with the same metrics as v3:
  - margin log-likelihood (with paired SE vs v3 and v1),
  - MAE,
  - P(win) log loss,
  - ATS vs the close,
  - Test B: ATS vs the CBS open and vs the live model.
- **Ablation (diagnostic only):** v3 + fix 1; + fix 2; + fix 3 (= v4). This shows each fix's contribution.

## Decision rules (fixed in advance)

- **Tracked projection:** v4 is recorded **alongside** v3 from its merge onward.
  - v4 replaces v3 as the displayed projection if its informed-test margin log-likelihood beats v3's on Test A.
  - The final verdict between them is the **live 2026+** paired margin log-likelihood, once 256 games are graded.
- **Live pick:** unchanged unless v4 beats the live model against the league line or CBS open with z ≥ 1.96
  **and** has lower log loss, on live games.
