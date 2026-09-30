"""Quick test: is ESPN's core API reachable from a GitHub runner, and does it keep historical NFL odds
(open/close per game)? Saves raw responses under docs/evidence/probe/<stamp>/espn_*."""
import datetime as dt
import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "evidence" / "probe" / dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
GAMES = {"2022_10_SEA_TB": "401435638", "2023_05_JAX_BUF": "401547228", "2024_12_KC_CAR": "401671651",
         "2026_01_BUF_HOU": "401872660"}
urls = {"site_scoreboard": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
        "site_web_scoreboard": "https://site.web.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"}
for g, e in GAMES.items():
    base = f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{e}/competitions/{e}"
    urls[f"core_odds_{g}"] = base + "/odds"
    urls[f"site_summary_{g}"] = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={e}"
summary = []
for name, url in urls.items():
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=30)
        (OUT / f"espn_{name}.json").write_text(r.text[:3_000_000])
        rec = {"name": name, "url": url, "status": r.status_code, "bytes": len(r.content)}
        if r.ok and name.startswith("core_odds"):   # follow the first provider's item for open/close fields
            items = r.json().get("items", [])
            rec["providers"] = [(i.get("provider") or {}).get("name") for i in items]
            if items and "$ref" in items[0]:
                d = requests.get(items[0]["$ref"].replace("http://", "https://"), headers={"User-Agent": UA}, timeout=30)
                (OUT / f"espn_{name}_item0.json").write_text(d.text)
        summary.append(rec)
    except Exception as ex:
        summary.append({"name": name, "url": url, "error": repr(ex)})
    print(summary[-1])
(OUT / "espn_summary.json").write_text(json.dumps(summary, indent=1))
