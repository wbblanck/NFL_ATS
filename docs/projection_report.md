# Score-Projection Model: Report

The rules were pre-registered in `docs/projection_preregistration.md` (commit
`14206c2`) before any result. The raw numbers are in
`data/backtests/projection_results.json`, from
`engine.backtest.projection_eval.run()`.

## Model `proj-poisson-v1`

- **Ratings:** two Poisson regressions, one for touchdowns and one for field
  goals. Each has a home effect and attack/defense terms per team.
  - Games are time-decayed with a half-life H, and ratings halve at each new
    season.
  - A ridge penalty λ pulls team terms toward 0.
- **Scores:**
  - TD ~ Poisson and FG ~ Poisson.
  - Per-TD extra points: 1 with p_xp ≈ 0.90, 2 with p_2 ≈ 0.045, from
    training data.
  - The margin distribution is computed exactly by convolution. A test checks
    it against a 50,000-draw Monte Carlo.
- **Tuned once on 1999–2006 only**, by log loss of P(home wins), over the
  grid H ∈ {8, 16, 32} and λ ∈ {1, 5, 20}. The result, **H = 8 weeks,
  λ = 5**, is then frozen.

## Primary test: walk-forward 2007–2021, 3,722 games vs SBRO open — **does not beat the live model**

| Model | ATS | Log loss of P(cover) |
|---|---|---|
| **Live (market-based `shifted`)** | **54.89%** (2043-1679) | **0.6862** |
| proj-poisson-v1 | 50.83% (1892-1830) | 0.7016 (worse than a coin flip, 0.6931) |

- **z of proj vs live = −3.51.** The switch rule needs +1.96, so the live
  model stays.
- **Margin accuracy:** the projected line's MAE is **11.04** points; the
  market close's is **10.72**.
- **Where the model disagrees with the market by 3+ points (1,194 games),
  its pick wins 46.6% ± 1.4 pp.** Siding with team ratings against the market
  lost more often than a coin flip.
- The two models' picks agree 60.7% of the time.
- **Dispersion:**
  - TD counts: mean 2.43, variance 2.11.
  - FG counts: mean 1.58, variance 1.43.
  - Both are *under*-dispersed relative to Poisson, which assumes
    variance = mean. That makes the score distribution too wide, and it
    explains part of the poor log loss.

## Confirmation 2025 (CBS open, 210 half-point games)

| Model | ATS | Log loss |
|---|---|---|
| Live | 108-102 | 0.6919 |
| proj-poisson-v1 | 107-103 | 0.7189 |

## Conclusion

The model produces sensible projected scores, e.g. week 3 SEA 27.6 – WAS 15.8
and SF 30.5 – ARI 17.2. But it does not beat the market line as a predictor
of the margin, and picking against the market's number is a losing strategy.
This matches Phase 6: public team-strength information is already priced in.

## Tracked comparison (live)

As requested, it keeps running alongside the live model:
- **Archive:** every lock run appends its projected scores, line and pick to
  `data/predictions/projections.csv`. The projection uses only games played
  before that week.
- **Grading:** `python -m engine grade` reports its record against the league
  line.
- **Dashboard:** it shows the projected score and flags games where the
  projection's pick differs from the live pick.
- **Review:** at season end, using the pre-registered disagreement rule
  (one-sided z ≥ 1.645).

**Possible v2, not built:**
- a Conway–Maxwell-Poisson or binomial count model, for the
  under-dispersion,
- a QB adjustment,
- starting ratings from the market line (a Bayesian prior).

Each would get its own pre-registered test.
