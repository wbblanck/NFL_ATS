# Bettable Record: Pre-registration

Written before any of the tests below were run. Question: would any model's picks have made money if they had been
bet at a sportsbook, instead of graded against the pool's stale line?

## Disclosure

- One result was seen before this was written, in conversation: the live model's picks, 2008-2025 (4,572 games),
  went 2,495-2,077 (54.6%) against the stale line and 2,276-2,203 (50.8%) against the closing line, a return of -3.0%
  at -110. It is re-run below under these rules and counted as already seen.
- Nothing was computed for keynum, v1 or Hybrid against any closing line before this document.
- The 2026 live results against the line at the pick (30 games) were also seen, and are treated as
  hypothesis-generating only (30 games, five models, see "Live tracking").

## The bet

- **The pool pick, bet at the closing line.** For each game, take the team the model picked against the stale line
  and bet that team at the closing spread (`nflverse` close, about 15 minutes after the lock), one unit, flat.
- Pushes are refunded and excluded from the record.
- **Price:** -110 on every bet. A win returns 100/110 units, a loss costs 1. Break-even win rate is **52.38%**.
- Return = (wins × 100/110 − losses) / (wins + losses).

## Models and windows

| Model | Picks regenerated from | Decision window |
|---|---|---|
| Live (official) | `patterns.dataset()`: walk-forward `shifted` model against the proxy stale line | 2008-2025 |
| Key-number variant | `MarginDist("keynum")`, walk-forward, SBRO opens | 2007-2021 |
| v1 (team-only projection) | `proj-poisson-v1` with the frozen H = 8, λ = 5, SBRO opens | 2007-2021 |
| Hybrid | live pick on 1+ point moves (close − open), v1 pick otherwise | 2007-2013 and 2020-2021 (the rule was chosen on 2014-2019; that stretch is reported but does not decide) |

- **v3 (player projection) is not backtested here.** Its historical per-game picks are not stored and rebuilding them
  is a separate job. It is judged only by live tracking until then.
- The stale lines before 2025 are proxies for the pool line (SBRO opens, then book opens), as in every earlier test.

## Decision rule

A model is called **profitable at -110** only if, over its decision window, its return is above zero with a one-sided
z ≥ 1.645 against the 52.38% break-even (z = (win rate − 0.5238) / √(0.5238 × 0.4762 / n)), after a Holm
correction across the four models above. Every model is reported either way, with its win rate and a 95% interval.

My expectation, stated in advance: none passes. The live model's closing-line win rate is 50.8% on 4,479 bets, and
v1 lost to the market in its own backtest.

## Live tracking (not a test)

The dashboard will show, for each model, the 2026 live record against the line at the pick (`market_at_lock`: the
Pinnacle line, or the median of books when Pinnacle had none), with units and return at -110, next to the backtest
numbers and a 95% interval. It carries no decision rule: with about 270 picks a season, a true 54% bettor would need
years to separate from break-even (about 5,900 bets for 80% power).

## Limits

- Flat -110 is an assumption. Pinnacle often posts about -105, where break-even is 51.2%.
- "Closing" is the nflverse close, a little after our lock, and some of the move after the lock was not
  available to the pick.
- Betting the same side at the close is one definition of a bettable bet. A bettor who instead compared each model's
  own margin projection with the closing line would be making a different bet; that is not tested here.
- Wins and losses are counted over games with a stale line available; the proxy lines before 2025 are not the pool's
  exact numbers.
