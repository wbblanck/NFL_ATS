# Edge Search With the AusSportsBetting Data: Pre-registration

Committed **before** any result below was computed. Already seen before this commit (disclosed): the gap test
(docs/gap2022_report.md): the live model vs bet365 opens 2022–2024 and vs betr/CBS opens 2025, including its
moved-1+ and no-move splits. Nothing about closing prices, moneylines or projections against these lines has been
looked at.

## What the file adds

One book per era (Pinnacle 2014–Feb 2018, bet365 Sep 2018–Feb 2025, betr from Sep 2025): spread open/min/max/close,
the **closing prices on each side of the spread**, moneylines, totals. Before 2014 only a single line per game.

## Common setup

- **Pool-line proxy:** the book's own opening spread, half-point opens only (as the pool). 2025: the CBS open
  (half-point), the closest thing to the pool line.
- **Market at lock:** the book's closing spread (2014–2024); nflverse close where the book close is missing (2025).
- **Baseline:** the live model (`shifted_total`, walk-forward, fit on nflverse seasons before the test season)
  picking against the proxy with the market at lock.
- **Splits:** discovery 2014–2019 (anything fitted is fitted here only); **confirmation 2020–2024 (decides)**;
  2025 CBS open (reported, must not be negative for a candidate).
- **Comparison statistic:** each rule is compared with the baseline on the games where their picks differ:
  z = (rule-only wins − baseline-only wins) / sqrt(games that differ), one-sided. Pushes excluded.

## Hypotheses (family of 7, Holm-corrected at 0.05 one-sided on confirmation)

1. **H1 price tie-break.** In no-move games (book close = proxy), pick the side whose closing spread price is
   shorter (the side the book charges more for). Equal prices: keep the baseline pick. No fitting.
2. **H2 price-adjusted market.** Market = close + b·(no-vig home cover probability at the close − 0.5), b fitted
   on discovery by cover log-likelihood (grid −6..6 by 0.25). Picks by the live model with that market.
3. **H3 moneyline vs spread.** Market = close + c·(moneyline-implied spread − close). The moneyline-implied
   spread is the spread whose win probability (live margin distribution) equals the no-vig moneyline home win
   probability. c fitted on discovery (grid 0..1 by 0.05).
4. **H4a v1 projection as the pick** (proj-poisson-v1, walk-forward) against the proxy.
5. **H4b v1 as the no-move tie-break** (baseline elsewhere).
6. **H5a v3 player projection as the pick**, 2022–2024 only (the seasons v3 was built to be tested on).
7. **H5b v3 as the no-move tie-break**, 2022–2024.

H5 is confirmation-only (v3's own design used 2013–2021); if v3's inputs cannot be rebuilt it is reported as not
run, and the family shrinks to 5.

## Decision rule

- A rule is a **candidate** only if its confirmation z passes Holm, its 2025 CBS-open disagreement record is not
  negative, and it is live-deployable (prices: yes, from our captures; moneylines: need a new capture).
- A candidate is **not** switched on by this test. It would get its own live-tracking period and the user's
  approval first.
- Every hypothesis is reported, whatever the result.

## Verification and simulations (reported, decide nothing)

- File checks: duplicates, open/close inside min/max, overround by era, sign agreement with nflverse closes,
  and 2026 weeks 1–3 against our own live captures and the recorded pool lines.
- Uncertainty: week-clustered bootstrap intervals for the confirmation results.
- Season Monte Carlo: the distribution of season wins over 272 games at the measured win rates.
