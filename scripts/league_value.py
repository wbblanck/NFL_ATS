"""What a per-game ATS edge is worth in the league (decision aid, not a backtest).

League (from the user, 2026-10-01): 44 entrants, $100 buy-in. Each week the most
correct picks wins $100; at season's end the top 3 are paid, first the most.
Assumptions, stated because they are not known: the season pot is what is left
after 18 weekly prizes (44*100 - 18*100 = $2,600), split 50/30/20; a tie (for the
week or a season place) is settled at random, which has the same expected value
as splitting the prize; the other 43 entrants are coin flips against the line
unless stated. Game counts per week are the 2026 schedule's.

Field models:
  indep  - each entrant picks each game independently, right 50% of the time.
  herd   - per game one side is "popular"; each entrant takes it with prob h.
           The popular side covers 50% of the time. Our pick is independent of it.
Contrarian check (herd model): on a share m of games we have no edge (p = 0.5);
compare always taking the popular side there with always taking the other side.

Usage: python scripts/league_value.py [--sims N]
"""
from __future__ import annotations

import argparse

import numpy as np

WEEK_GAMES = [16, 16, 16, 16, 15, 14, 14, 14, 15, 14, 13, 16, 14, 15, 16, 16, 16, 16]
N_FIELD = 43
SEASON_PRIZES = (1300.0, 780.0, 520.0)   # 50/30/20 of $2,600 (assumed split)
WEEK_PRIZE = 100.0


def simulate(p_us: float, sims: int, rng: np.random.Generator, herd: float | None = None,
             p_field: float = 0.5, no_edge_share: float = 0.0, contrarian: bool = False):
    """Return (expected weekly $, P(place 1,2,3), expected season $)."""
    weekly_money = np.zeros(sims)
    season_us = np.zeros(sims)
    season_field = np.zeros((sims, N_FIELD))
    for g in WEEK_GAMES:
        if herd is None:
            us = rng.binomial(g, p_us, sims).astype(float)
            field = rng.binomial(g, p_field, (sims, N_FIELD)).astype(float)
        else:
            cover_pop = rng.random((sims, g)) < 0.5              # popular side covers?
            on_pop = rng.random((sims, N_FIELD, g)) < herd       # entrant took popular side?
            field = (on_pop == cover_pop[:, None, :]).sum(axis=2).astype(float)
            # our games: a share with no edge, where we pick by popularity; the rest with edge p_us
            no_edge = rng.random((sims, g)) < no_edge_share
            us_on_pop = np.where(no_edge, not contrarian, rng.random((sims, g)) < 0.5)
            right_edge = rng.random((sims, g)) < p_us
            us_right = np.where(no_edge, us_on_pop == cover_pop, right_edge)
            us = us_right.sum(axis=1).astype(float)
        best = field.max(axis=1)
        n_tied = (field == best[:, None]).sum(axis=1)
        weekly_money += np.where(us > best, WEEK_PRIZE, np.where(us == best, WEEK_PRIZE / (n_tied + 1), 0.0))
        season_us += us
        season_field += field
    # season rank with random tie-breaks
    jitter_us = rng.random(sims)
    jitter_f = rng.random((sims, N_FIELD))
    above = ((season_field > season_us[:, None]) |
             ((season_field == season_us[:, None]) & (jitter_f > jitter_us[:, None]))).sum(axis=1)
    place = above + 1
    p_place = [float((place == k).mean()) for k in (1, 2, 3)]
    season_money = sum(pk * prize for pk, prize in zip(p_place, SEASON_PRIZES))
    return float(weekly_money.mean()), p_place, season_money


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=40000)
    a = ap.parse_args()
    rng = np.random.default_rng(20261001)
    print(f"{sum(WEEK_GAMES)} games, {len(WEEK_GAMES)} weeks, {N_FIELD} opponents; season prizes {SEASON_PRIZES}")
    print("\nIndependent coin-flip field")
    print(" p(us)  weekly $  P(1st)  P(2nd)  P(3rd)  season $  total $  net of $100")
    for p in (0.50, 0.52, 0.54, 0.55):
        w, pp, s = simulate(p, a.sims, rng)
        print(f" {p:.2f}  {w:7.0f}  {pp[0]:6.3f}  {pp[1]:6.3f}  {pp[2]:6.3f}  {s:8.0f}  {w + s:6.0f}  {w + s - 100:+7.0f}")
    print("\nField skill 51% (others also use some information)")
    for p in (0.52, 0.54):
        w, pp, s = simulate(p, a.sims, rng, p_field=0.51)
        print(f" {p:.2f}  {w:7.0f}  {pp[0]:6.3f}  {pp[1]:6.3f}  {pp[2]:6.3f}  {s:8.0f}  {w + s:6.0f}  {w + s - 100:+7.0f}")
    print("\nHerding field (h = 0.7): edge p on 75% of games, none on 25%")
    for contr in (False, True):
        for p in (0.50, 0.54):
            w, pp, s = simulate(p, a.sims // 4, rng, herd=0.7, no_edge_share=0.25, contrarian=contr)
            tag = "contrarian" if contr else "popular   "
            print(f" {tag} p={p:.2f}  weekly ${w:4.0f}  P(1st) {pp[0]:.3f}  P(top3) {sum(pp):.3f}  total ${w + s:5.0f}")


if __name__ == "__main__":
    main()
