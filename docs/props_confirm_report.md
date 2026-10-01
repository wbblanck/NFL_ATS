# NFL Player Props: Confirmation Report (2025)

Rules: `docs/props_confirm_preregistration.md` (commit 73a6d95), pushed before any 2025 line was fetched (fetch
run on that commit, data commit d985f0c). Numbers: `data/backtests/props_confirm.json`, from
`engine.backtest.props_confirm.run([2025])`.

## Result: FAIL (not profitable), though the signal is real

| H1: under at the highest line when books disagree | 2025 |
|---|---|
| Bets / weeks | 2,343 / 13 |
| Under won | 54.0% |
| ROI at the recorded price | **+0.9%**, 95% interval −3.1% to +4.2% → condition (a) fails |
| Same weeks, every screened DraftKings under | −5.8% (n = 7,387) |
| ROI minus that baseline | **+6.6%**, 95% interval +2.1% to +11.4% → condition (b) holds |
| Books at the bet | DK 1,291, BetRivers 548, FanDuel 396, BetMGM 108 |

The rule needed both; it fails. In plain terms: when books disagree on a player's line, the under at the
highest line did 6.6 points better than unders in general, and that difference is unlikely to be luck. But in
2025 unders in general lost 5.8%, so the rule only broke even.

Reported only: H2, the under at the lowest line in the same games, returned −4.1% (−7.6% to −1.0%). The gap
between H1 and H2 (about 5 points on the same games) is what shopping for the highest line is worth.

## Caveats

- Action Network's records carry no timestamps: two books' disagreeing lines may not have been available at the
  same moment, so even the relative edge may not be fully capturable live.
- Join coverage 2025: 35,265 full name matches, 253 last-name matches, 1,480 graded 0 (played, no stat row),
  1,605 unmatched (mostly team-defense TD props) of 38,603 real-book rows.
- 2024 supplied almost no multi-book weeks, so this test was effectively the first real look; 2026 (weeks so far)
  has not been used.
