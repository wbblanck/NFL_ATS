# 2025 Holdout Test: Pre-registration

Committed **before** any 2025 page was fetched or any 2025 result was
computed.

## Why

- **The user's benchmark:** 141 correct ATS picks in the 2025 league season,
  hand-picked, against the CBS league lines. 2025 has 272 regular-season
  games, so that is **141-131, 51.8%**.
- **Why 2025 is a fair test:** Phases 3–7 used only 2007–2021, so 2025 is out
  of sample for every design choice.

## System (frozen as of this commit)

- `phase4-shifted-empirical-argmax`.
- The margin distribution is trained on nflverse regular-season games
  1999–2024 only.

## Data

- **Frozen line (proxy):**
  - The **CBS odds-page "Open"** for each 2025 week, fetched from
    `https://www.cbssports.com/nfl/odds/2025/regular/week-{1..18}/` by a
    hosted runner.
  - This is CBS's own opener. It is **not** the league's Tuesday Pick'em
    line. The two agreed in 9 of 16 games in 2026 week 3.
- **Market at lock (proxy):** the nflverse 2025 closing `spread_line`.
- **Scores:** nflverse.

## Metrics

- **Primary:** W-L on games where the CBS open is a half-point (no push
  possible), with win rate and SE.
- **Secondary:**
  - Games with a whole-number CBS open: W-L-P, pushes excluded. Reported
    separately, because the league line for those games was a half-point
    that is unknown.
  - All games combined: W-L-P.
  - A per-week table, every week reported.
- **Comparison with 141/272, stated only as a comparison:**
  - The **projected 272-game wins**, computed as the primary win rate × 272.
  - Its 95% range.
  - It is not an equivalence claim. The line and the games differ.

## Decision rule

- **No retuning on 2025.** Whatever the result, the system is not changed
  because of this test.
- If the primary win rate is **below 51.8%**, that is reported plainly as
  "did not match the user's 2025 pace on this proxy".
