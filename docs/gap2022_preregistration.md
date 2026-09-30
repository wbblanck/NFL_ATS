# 2022–2024 Gap Test: Pre-registration

Committed **before** any 2022–2024 pick was graded. At this commit only the file's columns, its source notes
and its row count had been looked at.

## Why

- The live pick model was tested on 2007–2021 (SBRO opening lines) and on 2025 (CBS opening lines).
- 2022–2024 were never tested: SBRO stops after 2021, and the CBS week pages for 2022–2024 show no opening
  line (all 36 pages of 2023–2024 checked, 0 of 544 games).
- The user supplied the AusSportsBetting `nfl.xlsx` (downloaded 2026-09-30). Its notes say the odds from
  September 2018 to February 2025 come from **bet365** (one book), with open, min, max and close lines.

## System (frozen as of this commit)

- `total-shifted-empirical-argmax`, the live model. It picks exactly as `shifted` does (docs/total_report.md).
- Walk-forward: for season S, the margin distribution is fit on nflverse regular-season games before S
  (`engine.backtest.total._predict("shifted_total", ...)`), and the market at lock is the nflverse closing
  `spread_line`, as in every earlier test.

## Data

- **Frozen line (proxy):** bet365 `Home Line Open`, matched to nflverse games by date (±1 day) and team names.
  It is an opener, set earlier than the CBS Tuesday line, and from a different book.
- **Games:** 2022–2024 regular season. Games with no open or no nflverse closing line are dropped and counted.
- **Raw file:** kept out of git (`data/raw/aussportsbetting/`, gitignored), because its terms allow personal use
  only. Only aggregate results are committed.

## Checks before grading (reported, do not decide anything)

1. Match rate of 2022–2024 games; share of whole-number opens.
2. bet365 close vs nflverse close: share within 0.5 points.
3. **Proxy check on 2018–2021** (bet365 era, overlapping SBRO): share of games where the bet365 open equals the
   SBRO open, and the model's record on 2018–2021 graded against each.

## Metrics

- **Primary:** W-L on 2022–2024 games whose bet365 open is a half-point (no push possible, like the pool),
  pooled, with win rate and SE.
- **Secondary:** by season; all games with pushes excluded; games where the market moved 1+ point off the open;
  weeks with 12+ correct.

## Decision rule

- **No change to the live model** from this test, whatever the result. It is descriptive: it fills the gap.
- The result is reported as: consistent with the 2007–2021 edge if the pooled primary win rate's 95% interval
  includes 54.9% and excludes 50%; consistent with no edge if it includes 50% and excludes 54.9%;
  inconclusive otherwise.
- Every season is reported, good or bad.
