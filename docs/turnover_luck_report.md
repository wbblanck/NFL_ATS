# Turnover and Late-Score Luck: Report

- **Rules:** `docs/turnover_luck_preregistration.md`, commit 79d8408, made before any result.
- **Numbers:** `data/backtests/turnover_luck.json`.
- **Code:** `engine/backtest/turnover_luck.py`.
- **Games:** 4,572 regular-season games with a stale line, 2008–2025: discovery 1,490, confirmation 2,815.

## Result: fail (0 of 6)

| Input (away − home) | Discovery z | Confirmation 2014–24, side it favors | Model expected | z in discovery sign | 2025 |
|---|---|---|---|---|---|
| to_last: last game's turnover margin | +0.30 | 1053/2168 = 48.6% | 49.8% | −2.23 | 109/211 |
| to_last4: last 4 games | −0.09 | 1231/2407 = 51.1% | 50.1% | +1.67 (p 0.048; Holm needs 0.008) | 106/228 |
| to_season: per game, season to date | −0.10 | 1280/2479 = 51.6% | 50.1% | +0.64 | 112/233 |
| fumble_luck: recoveries above half | +0.88 | 1190/2382 = 50.0% | 50.1% | −0.76 | 124/239 |
| close_record: one-score games W − L | +0.92 | 1127/2221 = 50.7% | 50.4% | +0.79 | 109/220 |
| late_cover_flip: lost or won the cover in the last 5:00 last game | −0.62 | 244/523 = 46.7% | 50.3% | −1.76 | 36/60 |

## What it shows

- **Discovery was pure noise.** Every input had a discovery z within ±1. The signs it fixed were close to coin
  flips, and the confirmation results scatter around zero in both directions.
- **No input adds to the live model.** The best one, to_last4, would have won 51.1% where the model expected
  50.1%. That misses the corrected threshold by a wide margin.
- **to_last went the wrong way, z −2.23 against its discovery sign.** Read on its own terms, that would mean
  teams that won last week's turnover battle kept covering. It is not a finding: the discovery sign was itself
  noise (z +0.30), and it is one of six tries.
- **The market already prices turnover luck.** Past turnover margins, fumble recoveries, close-game records and
  late cover swings carry nothing it has not absorbed.
- **Sanity checks:**
  - 2024 inputs: 1.14 giveaways per team-game, and 47% of fumbles lost.
  - Every team-game has its opponent's row.
  - Late score states are available for 4,897 games.

## Conclusion

Turnovers and late scores decide individual games, as the week 3 losses showed. But how lucky a team has been
says nothing about its next game beyond what the line already reflects. The live model is unchanged.
