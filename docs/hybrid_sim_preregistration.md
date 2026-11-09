# Hybrid rule with the simulator: Pre-registration (2026-11-09)

Requested by the owner (2026-11-09, picked "Hybrid with simulator" as the next test), following the design sketched
in `docs/HANDOFF_game_simulator.md` ("Next step"). Committed **before** the simulator's output is joined to any
AusSportsBetting line or outcome. Research only: nothing here touches the pick pipeline, `predictions.csv`, the live
record or the tracked hybrid. Code: `scripts/hybrid_sim.py`, tests `tests/test_hybrid_sim.py`.

## Rule (one candidate, no selection step)
Same structure as the hybrid (`docs/hybrid_preregistration.md`):
- Market moved **1+ point** from the proxy line to the close (|close − open| ≥ 1): the live model's pick.
- Moved **½ point or not at all**: the simulator's side against the proxy line. Home if the simulator's fair home
  margin (G3 mean of 1,000 runs, seed 101) is greater than −open, away if it is below; equal keeps the live pick.
- The simulator's mean margin is used, not its cover probability (its probabilities near 3 and 7 are not trusted;
  handoff).

## Data
- **Simulator:** G3 as frozen in nfl-betting-model, regenerated here by `scripts/gamesim_reproduce.py` into
  `data/gamesim/g3_2022_2025.parquet`. That script refuses to write unless the margin MAE reproduces 9.983. If it does
  not reproduce on today's nflverse files, the test stops and that is reported. The tolerance is not loosened.
- **Lines:** AusSportsBetting `nfl.xlsx` (the owner's upload of 2026-11-09, sha256 starting `494509b4c5e9f8bb`).
  It stays local in `data/raw/aussportsbetting/` (gitignored) and is never committed. Proxy line = the book's open,
  market = the book's close, matched to nflverse games exactly as `engine.backtest.gap2022.match` and
  `engine.backtest.edge2.dataset` do (half-point opens only, so no pushes against the proxy line).
- **Live model:** as in edge2 and the hybrid backtest: the live margin distribution (`TotalDist("shifted_total")`,
  fit on seasons before the game's season) centered on the book close, P(home covers the open) > 0.5.
- **Spread sign:** canonical (negative = home favored); home covers when margin > −open.

## Sample
- **Test: 2022-2024**, regular season weeks 2-18 (the weeks the simulator output covers), every game with a
  half-point open, a close and a simulator row. Only 2022-2025 are out of sample for the simulator.
- 2025: reported as description only (the simulator's 2025 opener bets were already seen in nfl-betting-model, below).
  Used only if the file holds 2025 opens and closes.
- Run once.

## Test (one test, no family)
- Count only the ½/no-move games where the hybrid and the live pick differ. Net = simulator-only wins − live-only wins.
- z = net / √(games that differ). **Pass: z ≥ 1.645** (one-sided p ≤ 0.05), the same statistic as the hybrid backtest.
- A pass switches nothing on. It would be reported to the owner, and any live tracking would need his approval.

## Already seen (disclosed)
- In this repo, on 2022-2024 ½/no-move games: the live model's record (in the hybrid test's 2020-2024 window, live
  150-143 on those games), v1 (hybrid H4b), v3 (edge2 H5b) and the key-number lead (failed 38-40). None of them used
  the simulator.
- In nfl-betting-model, on 2022-2025: the simulator against nflverse's close (no edge: 1.5+ point disagreements went
  49.6%), the line moving about 30% of the gap toward the simulator from bet365's open to the close (all games, no
  outcomes by move size), and simulator bets at the 2025 opener (174 bets, 53.4%, failed).
- **Not seen by anyone:** the simulator's side on ½/no-move games against the book open, in any season.

## Power, stated in advance
The handoff estimates about 175 ½/no-move games in 2022-2024. The live pick on a no-move game is close to a coin flip
relative to the simulator's side, so roughly half should differ (my guess: about 85; the real count is printed).
With 85 differing games, a pass needs the simulator right on at least 51 of them (60%, net +17). Power: true rate on
differing games 55% → 21%, 60% → 55%, 65% → 86%. A fail means "no evidence", not "no effect".

## Descriptive only
- **Plain Elo** as a second candidate in the same rule (it matched the simulator on margin): net, z and record.
- Per season: ½/no-move games, games that differ, the simulator's and the live model's record on them.
- The whole hybrid's record on all games, and the simulator's record on all ½/no-move games.
- 2025 under the same rule, if the file has it.

## Known answers first
1. `scripts/gamesim_reproduce.py` reproduces G3's MAE 9.983 before anything is joined.
2. Hand cases in `tests/test_hybrid_sim.py`: the move split (|drift| 0, ½, 1), the simulator's side against a
   half-point open in both signs, a tie keeping the live pick, and the net and z on a planted example.
