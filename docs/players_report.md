# Player-Availability Projection (v2): Report

> **CORRECTION (2026-09-26): this test is invalid. Do not rely on its
> results.**
>
> The `qb_backup` flag marked a QB as a "backup" whenever he was not the
> team's most frequent starter over its previous 4 games. That wrongly flags:
> - **offseason and new starters:** 20 of 31 games in 2025 weeks 1–2 were
>   flagged, e.g. Cam Ward (TEN) and Daniel Jones (IND);
> - **starters returning from injury:** e.g. Brock Purdy in 2025 week 4 was
>   flagged as a "backup" because Mac Jones had started the games before.
>
> The injury counts also weighted every starter equally and ignored
> Questionable players. **The fitted "−11% TDs for a backup QB" mixes real
> backups with new and returning starters.** A rebuilt test (v3), with a QB
> quality rating and snap-weighted injuries, replaces this one:
> `docs/players_v3_preregistration.md`.

The rules were pre-registered in `docs/players_preregistration.md` (commit
`0037885`) before any result. The raw numbers are in
`data/backtests/players2025_results.json` and `players2025_games.csv`, from
`engine.backtest.players_eval.run()`.

## What was added

`proj-players-v1` is `proj-poisson-v1` plus three availability inputs, known
before each game's lock:
- **Backup QB starting.** For 2025, this uses the QB1 on the **last
  depth-chart snapshot before lock**. The flag is also set if the usual
  starter is Out or Doubtful.
- **Offensive starters Out or Doubtful:** RB, WR, TE and offensive line, from
  the depth chart and that week's injury report.
- **Opponent's defensive starters Out or Doubtful.**

## Effect sizes (fit on 2012–2024, on top of the team ratings)

| Input | Effect on touchdowns per game | Effect on field goals per game |
|---|---|---|
| Backup QB starting | **−11% (SE 2%)**, about −2 points | −1% (not significant) |
| Each offensive starter out | −1.5% (SE 1.1%) | −1.3% |
| Each opposing defensive starter out | +1.6% (SE 1.0%) | +0.5% |

Only the QB effect is clearly real. Individual non-QB injuries are small and
noisy at this level of detail.

## 2025 test (point-in-time depth charts, graded against the CBS open)

| | Live (market) | v1 (teams only) | v2 (+ players) |
|---|---|---|---|
| **Half-point opens (210)** | **108-102, 51.4%** | 107-103, 51.0% | 102-108, 48.6% |
| Log loss | **0.692** | 0.719 | 0.719 |
| All opens (267) | 130-137 | **143-124, 53.6%** | 136-131 |
| Games with a QB change (95) | **52-43** | 52-43 | 49-46 |
| Margin MAE (points) | **market close 9.76** | 10.15 | 10.13 |

With one season, the SE is about 3.4 pp. None of these ATS differences is
distinguishable from the others. On the all-opens view, v1's 143 is ahead of
the live model's 130 by about 1.5 SE, which does not meet the pre-registered
bar.

## Conclusion

- **Adding player availability made the projections slightly more
  accurate.** Margin MAE improved from 10.15 to 10.13 and log loss improved
  slightly.
- **It did not produce better picks**, and it did not get closer to the
  market's accuracy (9.76).
- The market line already contains QB news and injury reports, usually
  before our data does.
- **The switch rule is not met.** v2 joins the tracked comparisons alongside
  v1 and the key-number shadow.
