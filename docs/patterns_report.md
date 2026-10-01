# Overlooked Patterns: Report

Rules: `docs/patterns_preregistration.md` (committed before any result). Numbers: `data/backtests/patterns.json`;
code `engine/backtest/patterns.py`. 4,572 games: discovery 2008–2013 (1,490), confirmation 2014–2024 (2,815).

## Result

One of 15 passes: **key_cross**. It does not change any pick.

| Pattern | Confirmation 2014–24: favored side won / games | Model predicted | z | Holm pass |
|---|---|---|---|---|
| **key_cross** (move crosses 3 or 7) | 183/270 = **67.8%** | 59.4% | +2.81 | **yes** |
| bounce (after a 14+ loss as favorite) | 109/209 = 52.2% | 48.4% | +1.10 | no |
| division_dog | 542/1036 = 52.3% | 50.9% | +0.95 | no |
| ats_fade (fade 3-straight coverers) | 256/496 = 51.6% | 50.0% | +0.72 | no |
| wind_dog, home_dog, primetime_dog, dog, move_to_fav, move_to_dog, late_move | within ±0.5 pt of the model | | ≤ 0.37 | no |
| early_move, rest, nomove_home, big_fav_dog | below the model | | < 0 | no |

## key_cross, checked (after the pass, reported only)

- Half-point lines only (no pushes possible): 123/184 = 66.8% vs 58.5% predicted. Not a push artefact.
- Both key numbers: crossing 3 104/154 (67.5%), crossing 7 84/122 (68.9%).
- Above the model in 15 of 17 seasons 2008–2024. **2025 CBS opens: 13/26 (50%) vs 60.5% predicted.**
- The mirror image: 1+ point moves that do **not** cross 3 or 7 won 716/1,320 = 54.2% against 56.7% predicted.

**What it means:** the live model's margin distribution under-rates moves through a key number and slightly
over-rates other moves of the same size. **It changes no pick:** in all 374 key-crossing games, and in every
1+ point move, the live model already picks the side the market moved toward. It affects only the displayed
cover chance (and the expected win rate), not the pool picks.

## Conclusion

No overlooked situational pattern changes the picks. bounce, division_dog and ats_fade point the same way in both
periods but are far from significant; they are leads at most. The key-number finding is a calibration issue in
the cover chances, worth fixing only if cover chances are used for something beyond choosing the side.
