# NFL Player Props: Confirmation Report (2025)

Rules: `docs/props_confirm_preregistration.md` (commit 73a6d95), pushed before any 2025 line was fetched.
Numbers: `data/backtests/props_confirm.json`, from `engine.backtest.props_confirm.run([2025])`.

**CORRECTED 2026-10-01.** The first version of this report used 2025 data that contained first-half and
quarter props (Action Network files them under the same market from week 13; the fetch did not filter
`period`). Those lines were graded against full-game stats. The fetch now keeps full-game props only
(commit 07d7dc4), `props.load_lines` refuses any file where a book has two two-sided lines for one prop, and
2024 and 2025 were refetched. The rule and the test are unchanged; only the data changed. The first version's
claim that the rule beat ordinary unders by 6.6 points (CI excluding zero) was an artifact of the bad lines and
is withdrawn.

## Result on clean data: FAIL

| H1: under at the highest line when books disagree | 2025 |
|---|---|
| Bets / weeks | 3,198 / 13 |
| Under won | 54.6% |
| ROI at the recorded price | **+2.3%**, 95% interval −0.2% to +4.8% → condition (a) fails |
| Same weeks, every screened DraftKings under | +0.7% (n = 7,307) |
| ROI minus that baseline | **+1.6%**, 95% interval −0.5% to +3.5% → condition (b) fails |
| Books at the bet | DK 1,767, BetRivers 747, FanDuel 527, BetMGM 157 |

Reported only: H2, the under at the lowest line in the same games, −2.7% (−5.3% to −0.1%). Shopping for the
highest line instead of the lowest was worth about 5 points on the same props.

## Caveats

Action Network's records carry no timestamps: two books' disagreeing lines may not have been available at the
same moment. 2026 has not been used.
