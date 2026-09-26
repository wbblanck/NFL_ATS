# Projection Model v4.1 (`proj-latent-v41`): Pre-registration

Committed **before** any v4.1 component was built or any v4.1 result seen.

v4 failed its drive-model fit check (`docs/projection_v4_report.md`), so no v4 test result exists. v4.1 keeps
v4's two data fixes, which passed their checks, and replaces the score distribution.

## Carried over from v4 (passed validation)

- **Fix 1:** TDs are counted from play-by-play.
- **Fix 2:** neutral sites carry no home advantage.
- **Features and means as v3:**
  - Expected TDs μ_TD and FGs μ_FG = v1 walk-forward rates (recomputed with fixes 1–2) × exp(β·x).
  - β is fit by offset Poisson on 2013–2021.
  - **D and k are fixed at v3's frozen values (365 days, 500 dropbacks)** and not re-tuned. That removes a
    degree of freedom; v3's tuning surface was flat, −4.0095 to −4.0081.

## New: the joint score distribution

The four counts (TD_h, FG_h, TD_a, FG_a) are **independent given latent game factors**. Each count is binomial
with n trials and mean μ·m, where m is the product of the factors below:

| Factor | Distribution | Home TD | Home FG | Away TD | Away FG |
|---|---|---|---|---|---|
| Z: game environment | N(0, 1) | exp(a·Z) | exp(b·Z) | exp(a·Z) | exp(b·Z) |
| V: dominance | N(0, 1) | exp(e·V) | exp(f·V) | exp(−e·V) | exp(−f·V) |
| W_h: home finishing | N(0, 1) | exp(c·W_h) | exp(−d·W_h) | — | — |
| W_a: away finishing | N(0, 1) | — | — | exp(c·W_a) | exp(−d·W_a) |

**Details**
- **Mean-preserving:** each multiplier is divided by its expectation, e.g. exp((a² + e² + c²)/2) for TD. The
  expected counts therefore stay exactly μ, apart from a cap p ≤ 0.95 per trial, which is disclosed and counted.
- **Trials:**
  - n_TD ∈ {max_obs + 1, 12, 15, 20, 30, ∞ (Poisson)};
  - n_FG ∈ {max_obs + 1, 12, 20, ∞};
  - where max_obs is the largest count in the training seasons.
- **Signs are not imposed.** a, b, c, d, e, f are free.
- **Points:** 6 per TD plus 0, 1 or 2 extra points per TD (p_xp, p_2 as v1), plus 3 per FG. Safeties are ignored,
  as in all versions.
- **Integration:** Gauss–Hermite quadrature, 5 nodes per factor (5⁴ = 625 nodes).
- **Estimation:**
  - The six loadings and (n_TD, n_FG) are fit by **maximum likelihood of the observed four counts, on the
    2013–2021 regular season only**. The means μ come from that same training fit.
  - Nelder–Mead is run for each (n_TD, n_FG) pair, and the best likelihood wins.
  - Loadings are reported with approximate SEs from a numerical Hessian.

## Validation checks (must pass before any 2022–2025 result is read)

1. **Data fixes re-confirmed:** TD reconciliation ≥ 99.5%; no neutral game with home = 1.
2. **Point-in-time:** the v3 feature rebuild is repeated.
3. **Dependence structure reproduced (training):**
   - The model-implied residual correlation matrix of (TD_h, FG_h, TD_a, FG_a) matches the observed matrix
     within **±0.05 in every entry**.
   - Implied TD and FG dispersion within **±0.05** of observed.
   - Implied values are computed by simulation from the fitted model at the training means, with 200 draws
     per game and a fixed seed.
4. **Calibration (training):**
   - The 50% interval covers **0.47–0.53** of margins.
   - Every PIT decile is within **0.08–0.12**.
5. **Internal holdout:**
   - Refit the latent parameters on 2013–2018 only, keeping μ from the same design.
   - 50%-interval coverage on 2019–2021 must be within **0.46–0.54**.
   - This guards against the distribution merely memorising its training seasons.

If any check fails, v4.1 is not scored, and the failure is reported as v4's was.

## Evaluation (informed test: see the v4 disclosure)

- 2022–2025 informed v4's design and still does for v4.1. Those results are reported as an **informed test**;
  **live 2026+** is the clean test.
- **Test A (2022–2024) and Test B (2025):**
  - margin log-likelihood with paired SE vs v3 (as specified) and v1,
  - MAE,
  - P(home wins) log loss,
  - ATS vs the close,
  - 50%-interval coverage and PIT deciles.
- **Test B also:** ATS vs the CBS open and vs the live model.
- **Ablation:**
  - v3 as specified;
  - v3 + fix 1;
  - + fix 2 (Poisson);
  - + latent distribution (= v4.1).

## Decision rules (fixed in advance)

- **Tracked projection:**
  - v4.1 is recorded alongside v3 from its merge onward.
  - It becomes the displayed projection if its informed-test margin log-likelihood beats v3's on Test A.
  - The final verdict is the live paired margin log-likelihood after 256 graded games.
- **Live pick:** unchanged, unless v4.1 beats the live model against the league line or CBS open with
  z ≥ 1.96 **and** has lower log loss on live games.
