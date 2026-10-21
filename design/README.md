# Scoreboard dashboard (design)

A redesign of the NFL_ATS dashboard in the **dark-tech** style pack
(`.claude/skills/dark-tech`, on top of the core `design-taste` skill), read as a
stadium scoreboard. Chosen by the owner from three hero options on 2026-10-21;
the other style packs were removed.

| File | What it is |
|---|---|
| `dashboard.template.html` | The page. Reads the same `const D=__DATA__` payload that `engine.picks.dashboard` already builds. |
| `build_dashboard.py` | Copies the payload out of `site/dashboard.html` into the template, writing `dashboard.html`. |
| `dashboard.html` | Built page on the 2026-10-20 data (week 7). Open in a browser. |
| `hero-1.html` | The chosen hero. `hero-2/3.html` are the rejected options, kept for reference. |

Rebuild after a new `site/dashboard.html`: `python design/build_dashboard.py`.
Nothing here is wired into the pick pipeline or `publish-dashboard.yml`.

Team logos are nflverse's squared logos, loaded from GitHub when the page is
viewed (not stored in this repo); if one fails to load, the abbreviation shows.
Team colors come from nflverse `teams_colors_logos.csv`.

## Sections

Scoreboard (live record, win rate ± SE, graded / 256, last week, live
countdown to the next pick) · lock schedule rail · week board (filter, team
search, sort by kickoff / cover chance / line gap; each game opens to the
reasons, market-median line movement, books at pick time vs the pool line, and
the player-projection breakdown) · season drive (cumulative net wins against
the coin-flip luck band, backtest weeks shaded) · official pick by week ·
model standings · last week's finals with each pick's cover margin through the
game.

## Pre-launch check (design-taste §7 + dark-tech §6), 2026-10-21

| Check | Result |
|---|---|
| Could be made without the skill / generic template | Pass: scoreboard identity, football-specific charts (season drive, cover-margin flow) |
| Centered badge + heading + 2 buttons + screenshot hero | Pass: split hero, the scoreboard is the visual |
| Emoji as UI | Pass: none |
| Three identical cards from habit | Pass: game cards are a data grid, one per game |
| Single neutral sans | Pass: Big Shoulders Display + IBM Plex Mono + Public Sans |
| More than ~2 colors carry meaning | Known exception (owner asked for more color, 2026-10-21): navy ground, team colors and logos on game tiles, blue for the hybrid line and luck band; amber stays the one accent for the pick and next lock; green/red only for cover/miss |
| Body text column too wide | Pass: hero copy capped at 44ch |
| Accent more than ~4 times per viewport | Fixed: amber removed from pool line, cover gauge, move tag and bullets; on the board it marks only the picked team (one per card) |
| Light surfaces / gradients | Pass: none |
| Headline above 4rem or serif | Pass: clamp max 4rem, grotesk |
| Radius above 10px panels / 6px buttons | Pass: 6–10px panels, 6px controls |
| Text contrast | Fixed: muted label color raised from 4.06:1 to 5.14:1 on panels |
| Reduced motion, keyboard | Pass: the pulse and transitions are off under reduced motion; native buttons, select and details/summary with focus rings |
| No horizontal scroll at 390px | Pass (checked in headless Chromium) |
