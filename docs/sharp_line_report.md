# Sharp-Book Market Estimate: Report

Rules: `docs/sharp_line_preregistration.md` (committed before any result). Numbers: `data/backtests/sharp_line.json`;
code `engine/backtest/sharp_line.py`. 994 games, 2014–2017 (379 with half-point SBRO opens).

## Result: not worth the credits

| Market at lock (half-point SBRO opens, 379 games) | Record | Games that differ from baseline | Won there (version / baseline) | Log loss |
|---|---|---|---|---|
| Baseline: consensus close | 196-183 | — | — | 0.6904 |
| Pinnacle close | 197-182 | 3 | 2 / 1 | 0.6900 |
| Pinnacle close + price | 201-178 | 63 | 34 / 29 (z = 0.63) | 0.6905 |

Neither version reaches z ≥ 1.645 with lower log loss. On all 994 games the price version is 523-471 against the
baseline's 528-466.

## Why

- **The consensus close already is the sharp line.** Pinnacle's close equalled the nflverse consensus close in 94% of
  games; the mean difference was 0.04 points. There is almost nothing for a sharp-book estimate to add.
- **Prices do not help.** Converting Pinnacle's juice into a finer line changed 63 half-point picks and won 34 of
  them to the baseline's 29: noise.

## Corrections made after seeing results (disclosed)

1. The first run counted pushes as losses when converting prices on whole-number lines. Fixed; the price version
   went 199-180 before the fix and 201-178 after. Both runs are in the JSON.
2. A further variant, measuring the price against the model's own cover chance at that line rather than 50%, was
   added after the results (reported only, cannot pass): worse, 499-495 on all games, 43 vs 72 on differing games
   (z = −2.70).

## Conclusion

Refining the market estimate with a sharp book or with prices does not improve the pick. The planned multi-book
timing captures are not pursued on this basis; the API budget stays at the current ~230 credits a month.
