# Selective Prop Rules: Confirmation Pre-registration (2026)

Chosen on 2025 (exploration, docs/selective_preregistration.md); committed before any 2026 prop line was
fetched. Code: `engine/backtest/props_selective.py` (`run(2026)`).

Base bet: the under at the highest line where >= 2 books post different lines for the same player-game-market,
best under price at that line, screened as in docs/props_confirm_preregistration.md, gap <= 30% of the lower line.

| Rule | 2025 (exploration) |
|---|---|
| R1 three or more books quote the prop | n 1,277, under 55.2%, ROI +2.6% |
| R2 the under at the high line is priced below −120 | n 348, under 62.1%, ROI +7.5% |
| R3 the high line is at BetRivers or BetMGM | n 719, under 56.9%, ROI +4.6% |

None cleared its own interval on 2025; they are the strongest slices found, not proven ones.

**Correction (2026-10-01, before any 2026 prop line was read):** the 2025 numbers above were computed on data
that still contained first-half/quarter props (fixed in 07d7dc4, refetched). On clean 2025 data the same rules
give: R1 n 1,807, under 56.0%, ROI +4.5%; R2 n 354, under 61.9%, ROI +7.3%; R3 n 973, under 58.0%, ROI +7.1%
(R3's Bonferroni interval +2.3% to +12.6%). The rules and the decision are unchanged.

**Decision** after the 2026 regular season (weeks 1–18; interim looks are descriptive): a rule PASSES if
n ≥ 30 bets in ≥ 10 weeks and the week-clustered ROI interval at the Bonferroni level (one-sided 2.5% / 3) has
its lower end above 0.
