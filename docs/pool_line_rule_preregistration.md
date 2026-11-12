# Pool-Line Rule: Pre-registration (2026 weeks 11-18)

Registered 2026-11-12, before any week 11 pool line exists (week 11 lines arrive Tue 2026-11-17).
Owner instruction: "Register it". Research only; nothing in the pick pipeline changes.

## Question

Can the CBS pool's frozen Tuesday line be reproduced from the Tuesday-morning market, using the
price (juice) to decide the half point when a book sits on a whole number?

## Development sample (already seen; not evidence)

2026 weeks 4-10, 102 games, scored with `scripts/research/pool_line_rule.py --weeks 4-10`:

| Rule | Exact matches |
|---|---|
| P1 DraftKings, juice-rounded | 88/102 (86%) |
| P2 most common juice-rounded line, all books | 90/102 (88%) |
| Baseline: raw DraftKings line | 66/102 (65%) |

Juice direction on DraftKings whole numbers (pool on an adjacent half, price not even): 22/25.
The rule was found by looking at this sample, so these figures are optimistic.

## Data (fixed)

- Market: `data/lines/market_captures.csv`, rows with `status == ok` and non-missing `home_spread`
  and `home_price_decimal`. Home spread sign: negative = home favored.
- Pool lines: `data/lines/league_lines.csv` through `league_lines.load_checked()` (valid rows only),
  season 2026, weeks 11-18, entered in the usual Tuesday routine. No backfilling or editing for this test.
- Snapshot: for each game and book, the first capture from 08:00 to before 16:00 ET on the game's Tuesday
  (the last Tuesday on or before kickoff), and before kickoff.

## Rules (fixed)

- **Juice rounding.** A half-point line is kept. A whole-number home spread S becomes S − 0.5 if the home
  price (decimal) is below 1.905 (heavier than about −110), S + 0.5 if above 1.915, and no prediction otherwise.
- **P1 (primary): DraftKings, juice-rounded.**
- **P2 (secondary): the most common juice-rounded line across all books** in the snapshot; a tie is no prediction.
- **Baseline:** raw DraftKings line.

## Scoring (fixed)

- Primary metric: P1 exact matches / all weeks 11-18 games with a valid pool line. No prediction
  (missing DraftKings capture, even price) counts as a miss.
- **Confirmed** only if: at least 80 games, P1 exact rate ≥ 80%, and the Wilson 95% lower bound ≥ 70%.
  Otherwise "not confirmed".
- Also reported: P2 and the baseline on the same games, and the juice-direction count on DraftKings
  whole-number games with a one-sided binomial test against 50%.
- Scored once, after week 18's pool lines are entered:
  `python scripts/research/pool_line_rule.py --weeks 11-18`. Weekly running counts may be shown but
  change nothing.

## What a result means

- Confirmed: the rule may be used to rebuild past pool lines for research (for example 2018-2022 from
  ESPN's timestamped history in `data/raw/espn_history/`), with the caveat that ESPN's source book differs
  from DraftKings and that about 29% of its whole-number Tuesday lines have even prices.
- Not confirmed: rebuilt lines keep a half-point uncertainty on whole-number games.
