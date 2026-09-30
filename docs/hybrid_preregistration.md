# Hybrid Rule (market move 1+ pt, something else below): Pre-registration

Committed before the hybrid results below were computed. Already seen (disclosed): in no-move games, v1 as the
pick vs the live model (edge2 H4b: 2014–19 +1, 2020–24 +11) and v3 (H5b), and the closing-price side (H1). Not
yet seen: any candidate in **half-point-move** games, or in half-point and no-move games combined.

## Rule

- Move off the proxy line of 1+ point: live model pick (unchanged).
- Move of ½ point or none: the candidate's pick.

## Candidates (all available 2014–2024)

1. **v1**: proj-poisson-v1 cover probability against the proxy line.
2. **Price**: the side with the shorter closing spread price (ties: live pick).
3. **Agree**: v1's pick only where it agrees with the price side, else the live pick.

## Procedure

- Proxy line: the book's half-point open; market: book close (as edge2).
- **Selection on 2014–2019 only:** the candidate with the highest net wins over the live model (candidate-only
  wins − live-only wins) on the ½/no-move games. Only that candidate is tested.
- **Test on 2020–2024:** one-sided z on the games where the picks differ, pass at p ≤ 0.05.
- **2025 CBS open:** reported for v1 (no reliable 2025 prices).
- A pass does not switch anything on; it would go to live tracking with the user's approval.

## Power, stated in advance

About 290 ½/no-move games in 2020–2024. A true improvement from 50% to 53% on those games would be detected
only about 1 time in 4. A fail therefore says "no evidence", not "no effect".
