# CBS Pool Line-Setting Analysis: Pre-registration

Committed **before** any Tuesday posting-window data was analysed. The questions and metrics are fixed here.
Results are added to `docs/cbs_lines_report.md` as weeks accumulate.

## Why

- The pool line L is frozen at CBS's Tuesday posting (about 12:00 ET). The market keeps moving until lock.
- How CBS sets L decides where the pool's edge comes from:
  - which source and time it copies;
  - how it turns whole numbers into half-points;
  - how far the market moves afterwards.

**Week-3 observation that motivated this:** 5 of 14 pool lines differ from the CBS odds page's "Open" value, for
example LAC @ BUF −7.5 vs −4.5. So L is not simply that page's opener.

## Data

- **L:** the league line from the user's pool screenshots (`data/lines/league_lines.csv`).
- **Candidate sources for L,** captured every 30 minutes on Tuesdays 08:00–17:00 ET:
  1. the CBS odds page's *current* line and its named operator (`data/lines/cbs_open_captures.csv`,
     `current_home_spread` / `current_operator`);
  2. each book's line and the median consensus (`data/lines/market_captures.csv`).
- **Past weeks:**
  - Historical market snapshots, **if** the Parlay `/historical` endpoint works. It is being probed; the
    result will be recorded in `data_audit.md`.
  - Past pool lines, if the user can supply them: weeks 1–2 of 2026, and 2025.

## Questions and metrics

**Q1. Source and timing.**
- For each candidate (source × Tuesday snapshot time), compute the exact-match rate with L. For a whole-number
  candidate, count it matched if either half-point rounding reproduces L, and record which rounding.
- Report the best candidate and its match rate as matches / N.
- "Identified" requires **≥ 45 games (about 3 weeks)** and a match rate ≥ 90%. Otherwise the report says
  "not identified", with the top candidates.

**Q2. Half-point rule.** For games where the identified source sits on a whole number:
- record whether CBS moved it toward the favorite (e.g. −3 → −3.5) or toward the underdog (−3 → −2.5);
- report the counts and a two-sided binomial test against 50/50.

**Q3. Value of the hook.**
- From 2006–2025 regular-season games with whole-number closing lines, estimate P(margin exactly = |line|),
  e.g. the push probability at 3, 7, 10 and 14.
- The side the half-point favours gains about that probability in cover chance, compared with a push.
- Report the expected cover rate of "take the side the hook favours" per key number, with standard errors.
- Report whether the live model's pick agrees with the hook side on those games. The live model already prices
  key numbers through its margin distribution, so this checks rather than adds an edge.

**Q4. Movement after posting.**
- Each week, the distribution of (market at lock − L): mean, absolute mean, and share of moves ≥ 1 point.
- Also the week's live record on games with moves ≥ 1 point vs < 1 point.
- Descriptive only until 256 graded games (the Phase 7 rule).

## Rules

- No result from this analysis changes the live pick rule. Any proposed change would need its own
  pre-registration and to pass the Phase 7 bar.
- All counts are reported, including games that don't fit any candidate.
