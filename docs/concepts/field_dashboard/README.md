# Field-strip dashboard concept (2026-10-19)

A design concept, not the live dashboard. Each game is a strip of turf; the yellow TV first-down line is the
pool line; the ball sits where the game ended relative to it (past the line = covered). Yard marks every
7 points. A dark scorebug bar holds the records.

`template.html` is self-contained apart from its data: replace `__DATA__` with the `D` object that
`engine.picks.dashboard.render` embeds in `site/dashboard.html` (same keys). Chart colors were checked with
the dataviz palette validator: light `#2a6fdb` / `#c2560b`, dark `#3f82e0` / `#d9722a`.

Display only: nothing here changes a pick.
