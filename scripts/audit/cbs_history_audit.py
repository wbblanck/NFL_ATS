"""Audit 0.3/0.4: which archived CBS week pages still carry the "Open" column,
and how many of those openers are whole numbers (impossible as league lines)."""
import csv
import glob
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from engine.data.cbs_lines import opening_home_spread, parse_odds_page  # noqa: E402
from engine.picks.grading import is_half_point  # noqa: E402

rows = []
for f in sorted(glob.glob(str(ROOT / "docs/evidence/probe/*/cbs_odds_*_w*.html"))):
    season, week = re.search(r"cbs_odds_(\d{4})_w(\d+)\.html", f).groups()
    games = parse_odds_page(open(f).read())
    spreads = [opening_home_spread(g)[0] for g in games]
    have = [s for s in spreads if s is not None]
    rows.append({"season": season, "week": week, "games_on_page": len(games), "with_open": len(have),
                 "whole_number_opens": sum(not is_half_point(s) for s in have),
                 "probe": Path(f).parent.name})
out = ROOT / "docs/evidence/cbs_history_open_column.csv"
with open(out, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
for r in rows:
    print(r)
