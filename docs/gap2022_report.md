# 2022–2024 Gap Test: Report

Rules: `docs/gap2022_preregistration.md` (commit `0b31465`, before grading). Numbers: `data/backtests/gap2022.json`
from `engine.backtest.gap2022.run()`. The AusSportsBetting file itself is not committed (personal-use terms).

## Checks before grading

| Season | Games | With bet365 open | Whole-number opens | bet365 close within ½ pt of nflverse close | Open = close |
|---|---|---|---|---|---|
| 2022 | 271 | 271 | 132 | 93.7% | 14.0% |
| 2023 | 272 | 272 | 106 | 91.5% | 12.5% |
| 2024 | 272 | 272 | 124 | 97.4% | 19.1% |

Every game matched. The closes agree with nflverse, so the file lines up with the right games and sides.

**Proxy check, 2018–2021 (same model, two different opening lines):**

| Season | bet365 open = SBRO open | within 1 pt | Record vs bet365 open | Record vs SBRO open |
|---|---|---|---|---|
| 2018 | 41% | 86% | 131-115 (53.3%) | 124-120 (50.8%) |
| 2019 | 30% | 72% | 148-105 (58.5%) | 138-109 (55.9%) |
| 2020 | 20% | 64% | 138-109 (55.9%) | 141-107 (56.9%) |
| 2021 | 18% | 67% | 147-121 (54.9%) | 143-112 (56.1%) |

The two openers often differ, but the model's record against them is similar (564-450, 55.6%, vs 546-448, 54.9%).

## Result

**Primary (half-point bet365 opens, 2022–2024): 256-197, 56.5% ± 2.3 (95%: 51.9%–61.1%).**
Per the pre-registered rule: **consistent with the 2007–2021 edge** (the interval includes 54.9% and excludes 50%).

| Season | Half-point opens | All games (pushes excluded) |
|---|---|---|
| 2022 | 71-68 (51.1%) | 144-120 (54.5%) |
| 2023 | 106-60 (63.9%) | 162-106 (60.4%) |
| 2024 | 79-69 (53.4%) | 143-123 (53.8%) |
| **Total** | **256-197 (56.5%)** | **449-349 (56.3% ± 1.8)** |

- Market moved 1+ point off the open: 301-208, 59.1%. No move: 57-64, 47.1%.
- Weeks with 12+ correct: 2022: 0, 2023: 2, 2024: 0.
- 2023 carries much of the total; 2022 and 2024 alone are modest.

## The important caveat: which opening line

Not pre-registered, reported only. 2025 graded with the same model against two openers:

| 2025 line | Record | Moved 1+ pt |
|---|---|---|
| betr open (AusSportsBetting) | 137-121 (53.1%) | 109-78 (58.3%) |
| CBS open (the earlier holdout) | 130-137 (48.7%) | 66-61 (52.0%) |

The two agreed in 35% of games. Against a bookmaker's early opener the model keeps its edge; against the CBS line it
did not in 2025. The pool uses CBS's Tuesday line, which is posted later than a bookmaker's opener, so part of the
early move has already happened when the pool line is set. **The 2022–2024 result therefore shows the market-move
signal still worked in those seasons, but it overstates what to expect against the pool line.** The honest guide
for the pool remains the CBS-line results (2025 and the live record).
