# 2025 Holdout — results

Generated 2026-09-25T13:18:47+00:00 by `python -m engine holdout2025` (nflverse snapshot 20260925T131843Z). Pre-registration: `docs/holdout2025_preregistration.md`.

2025 regular-season games: 272; without a parsable CBS open: 1.

- **Primary (half-point CBS open):** 108-102-0 (N 210), 0.5143 ± 0.0345
- Whole-number CBS open: 22-35-4 (N 57), 0.3860 ± 0.0645
- All: 130-137-4 (N 267), 0.4869 ± 0.0306
- Diagnostic — market moved ≥ 1 pt from CBS open: 66-61-1 (N 127), 0.5197 ± 0.0443; < 1 pt: 64-76-3 (N 140), 0.4571 ± 0.0421

Projected over 272 games: **140 wins** (95% range 121–158). User's hand-picked 2025: **141** (vs the league line, a different line).

## Per week

| Week | W | L | P | Win rate |
|---|---|---|---|---|
| 1 | 5 | 10 | 1 | 0.333 |
| 2 | 9 | 7 | 0 | 0.562 |
| 3 | 6 | 8 | 1 | 0.429 |
| 4 | 9 | 7 | 0 | 0.562 |
| 5 | 8 | 6 | 0 | 0.571 |
| 6 | 8 | 7 | 0 | 0.533 |
| 7 | 5 | 10 | 0 | 0.333 |
| 8 | 3 | 10 | 0 | 0.231 |
| 9 | 7 | 7 | 0 | 0.500 |
| 10 | 12 | 2 | 0 | 0.857 |
| 11 | 6 | 8 | 1 | 0.429 |
| 12 | 7 | 7 | 0 | 0.500 |
| 13 | 7 | 9 | 0 | 0.438 |
| 14 | 7 | 7 | 0 | 0.500 |
| 15 | 7 | 9 | 0 | 0.438 |
| 16 | 8 | 8 | 0 | 0.500 |
| 17 | 6 | 9 | 1 | 0.400 |
| 18 | 10 | 6 | 0 | 0.625 |
## Interpretation (written after the result; the rules were pre-registered)

**Against the pre-registered comparison, the model did not beat the user's
2025 pace.**

- **Primary result:** 108-102, 51.4% ± 3.4 pp. That projects to about **140
  wins over 272**, essentially the user's 141 (51.8%). It is below 51.8%, so
  per the pre-registration it is reported as *not matching* on this proxy.
- **All games with a CBS open:** 130-137-4, 48.7%.
- **The historical edge did not appear in 2025.**
  - Games where the market moved ≥ 1 point from the CBS open won 52.0%
    (66-61). Historically, 2007–2021, that group won 57.3%.
  - The 2025 SE is about 4.4 pp, so this is consistent both with a smaller
    true edge and with ordinary bad luck. One season cannot separate the two.
- **Weak spot (diagnostic, not used to change anything): whole-number CBS
  opens.** These went 22-35. The worst were opens of exactly 3 (9-11), 6
  (3-7) and 7 (6-10). That is where the Phase 4 key-number bias lives. The
  league's own line for those games was a half-point we don't have, so these
  games are the least comparable. They are also where a pre-registered
  key-number fix is most likely to matter.

**No retuning was done because of this result**, as pre-registered.
