# NFL Player Props: Data Audit

Evidence: `docs/evidence/props/` (runs 20261001T033151Z, 20261001T033953Z, 20261001T034123Z), script
`scripts/audit/props_probe.py`. No model and no outcomes were used.

## Action Network (keyless, from a hosted runner)

- The NFL scoreboard ignores `date` (run 1 returned this week's games for every date, so run 1 says nothing about
  history). `web/v2/scoreboard/nfl?season=S&week=W` returns the right week (checked 2021–2026).
- Player props by probed game:

| Season / week | Games probed | Markets per game | Books on the main yardage / reception props |
|---|---|---|---|
| 2021 w6, 2022 w6, 2023 w6 | 1, 2, 1 | **0** | none |
| 2023 w15 | — | — | scoreboard HTTP 504, unknown |
| 2024 w1 | 2 | 70–76 | DK NJ (BetMGM on some receptions / TD) |
| 2024 w6 | 2 | 73–74 | DK NJ |
| 2024 w15 | 2 | 63–66 | DK NJ, plus FanDuel NJ or BetRivers NJ |
| 2025 w1 | 2 | 73–76 | DK NJ |
| 2025 w6 | 1 | 88 | DK, FanDuel, BetRivers, BetMGM |
| 2026 w3 | 1 | 101 | DK, FanDuel, BetRivers, BetMGM |

- So usable history is **2024 onward** (two full seasons plus 2026 so far), mostly DraftKings.
- Markets include passing / rushing / receiving yards, receptions, attempts, completions, passing TDs,
  interceptions, longest plays, anytime / first / last TD scorer, 2+ / 3+ TDs, milestone ladders, tackles.
- Line records carry no timestamp. In the MLB project the same API's prices were close-time for FanDuel and its
  book 30 ("Open") was not a bettable price; neither has been checked for NFL.

## Outcomes

nflverse weekly player stats (`load_player_stats`) has completions, attempts, passing / rushing / receiving yards
and receptions per player-game (verified for 2024). Joining needs a name + team match (Action Network player ids
are not nflverse ids).

## Next

A props test should explore on 2024 only and confirm once on 2025 (and 2026), pre-registered before 2025 is
fetched or scored.
