# Strong Calls: Report

Rules: `docs/strong_calls_preregistration.md` (committed before grading, `5d4b346`). Numbers:
`data/backtests/strong_calls.json`; code `engine/backtest/strong_calls.py` (`python -m engine strong-calls`).
Live-model pool picks 2008-2025 (4,572 games). Discovery 2008-2016, confirmation 2017-2025 (decides).

## Result: tiers by move size are real strong calls in the pool, and not strong bets

| Tier | Move | Share | Pool win rate (all) | Discovery | Confirmation | At the closing line (-110) |
|---|---|---|---|---|---|---|
| Lean | under 1 | 45% | 52.2% (1,064-976) | 52.4% | 51.9% | 51.3% (-2.0%) |
| Solid | 1 to 2 | 28% | 54.4% (690-578) | 54.4% | 54.5% | 51.1% (-2.4%) |
| Strong | 2 to 3 | 15% | 56.4% (397-307) | 57.1% | 55.5% | 50.2% (-4.1%) |
| Max | 3 or more | 12% | **61.4%** (344-216) | 57.9% | **63.7%** | 48.9% (-6.6%) |

Move 2+ together won 59.8% in confirmation (n = 661). Max held up across eras: 59% (2008-13), 59% (2014-19), 65%
(2020-24) and 60% (2025, 21 of 35, the season with real pool-line data).

## Hypotheses (confirmation period, Holm over five)

| | Result | Pass |
|---|---|---|
| H1 Move 2+ wins above 50% | 59.8%, p < 0.0001 | yes |
| H2 Move 3+ wins above 50% | 63.7%, p < 0.0001 | yes |
| H3 Win rate rises across the four tiers | z = +3.59, p = 0.0002 | yes |
| H4 Live, v1 and key-number variant all agreeing beats not agreeing (2007-2021) | 54.6% vs 54.7%, p = 0.51 | **no** |
| H5 Moves through a 3 or 7 beat the rest | 66.5% vs 53.5%, p = 0.0001 | yes, with a caveat |

H1-H3 also had discovery-period rates above 50%, so each is a **real strong call** under the rule. Labels
(Lean, Solid, Strong, Max) are therefore shown on the dashboard and in the alert. The pick itself never changes.

## What it shows

- **Strength is the size of the market move.** The model's cover probability tracks the move almost exactly
  (correlation 0.96), so there is one signal here, not two.
- **A strong call is a strong pool pick, not a strong bet.** The bigger the move, the more of the move is already in
  the closing line: Max wins 61% against the pool line and 48.9% against the closing line. The pool's stale line is
  the whole edge.
- **Agreement among models adds nothing** (54.6% vs 54.7%). Three models saying the same thing is not stronger.
- **Key-number crossing passed, but I stated in advance that it would not add beyond move size, and that was wrong.**
  Inside each move tier crossing still did better (post-hoc, exploratory): Solid 62.7% vs 53.3%, Strong 68.3% vs
  54.8%, Max 66.9% vs 59.6%. It is not used as a tier because it did not repeat in 2025 (13 of 26, the real
  pool-line sample; the whole 2025 season ran weak, 48.5% on the rest) and the earlier test of it (docs/patterns_report.md)
  also lost it there. It is shown on the card with that caveat.
- **Not repeated:** the open search of 7,814 situation rules (docs/mining_report.md) found nothing beyond chance.
  Specific situations that "tend to win" were looked for there and none survived a holdout.

## 2026 so far (descriptive)

Only 1 of the live picks has been a Strong call and none a Max call (Lean 9-8, Solid 8-5, Strong 0-1 against the pool
line), so the live season says nothing yet about the top tiers.

## Limits

- Stale lines before 2025 are proxies for the pool line.
- Tiers are by the move seen at the lock; they cannot be used to choose bets at the open.
