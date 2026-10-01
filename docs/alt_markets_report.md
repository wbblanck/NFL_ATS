# Real-Money Market Tests: Report

Rules: `docs/teaser_preregistration.md`, `docs/halftime_preregistration.md`, `docs/move_preregistration.md`, all
committed (055e095) before any bet was graded. Numbers: `data/backtests/alt_markets.json` (nflverse snapshot
20261001T033819Z), from `engine.backtest.alt_markets.run()`. None of these touches the pool pick.

## Result: nothing passed

Each test needed the lower end of a week-clustered 95% interval above break-even (Bonferroni over 2 per family).

| Test | Seasons | Bets | Win rate | 95% interval | Break-even | Verdict |
|---|---|---|---|---|---|---|
| Teaser H1: all half-point Wong legs | 2015–2025 | 589 | 76.1% | 72.2%–79.8% | 73.85% (−120) | fail |
| Teaser H2: legs with total ≤ 45.0 | 2015–2025 | 299 | 75.6% | 70.0%–80.5% | 73.85% | fail |
| Halftime H1: back the halftime trailer | 2015–2021 | 1,612 | 49.3% | 46.9%–51.6% | 52.38% | fail |
| Halftime H2: regression side vs 2H line | 2015–2021 | 1,736 | 51.3% | 49.1%–53.5% | 52.38% | fail |
| Move A: market-memory rating at the open | 2007–2021 | 2,846 | 51.7% | 50.0%–53.4% | 52.38% | fail |
| Move B: margin rating at the open | 2007–2021 | 2,925 | 51.7% | 49.8%–53.5% | 52.38% | fail |

## Teasers: closest to a result, not one

- 448 of 589 half-point legs won in 2015–2025. If legs are independent, a 2-team teaser at that rate returns
  +6.1% at −120 (+10.4% at −110). At the interval's ends it is −4.5% to +16.7% at −120, so the data cannot
  separate a real edge from break-even. 589 legs over 11 seasons is the whole sample; it will not grow faster than
  ~55 legs a season.
- 1999–2014 (reported, not deciding): 357 of 478, 74.7%.
- Not tested, so only a hypothesis: underdog legs (+1.5 to +2.5) won 77.5% (n = 387) and favorite legs 73.3%
  (n = 202) in 2015–2025. Splitting by kind was not pre-registered; it can only be tested on seasons not yet
  graded (2026 week 5 onward).
- Whole-number legs (+2, −8), 2015–2025: 81-29 with 2 pushes.

## Halftime lines: priced right

On 2007–2014 the second-half margin was fitted as 0.76 × the 2H line's expectation + 0.11 × the pregame
expectation + 0.016 × the first-half margin. The first-half score carries essentially nothing the 2H line has not
already used, and backing the trailing team was a coin flip.

## Line moves: real information, too small to bet

- Both ratings know something about the closing line beyond the open: coefficient on the rating in
  close = a + b·open + c·rating, A 0.035 (0.005–0.068), B 0.133 (0.089–0.181).
- B's bets saw the close move their way 45.5% of the time and against them 35.9% (mean +0.23 points), i.e. real
  closing line value.
- It is not enough: 51.7% at the open is short of the 52.38% that −110 requires. As in the MLB project, a model
  can lean the way the market later moves without overcoming the vig.

## Limits

nflverse closing lines and SBRO openers, 2H lines and source books are unverified; no prices were available, so
−110 and −120 are assumptions; best-available prices (or reduced juice) would change every break-even.
