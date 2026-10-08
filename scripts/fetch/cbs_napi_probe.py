"""One-off test: is CBS Sports' data API (api.cbssports.com, as wrapped by sportsdataverse-js `cbs`) reachable from a
GitHub runner, do its odds carry opening lines, and does it serve public betting splits, including for games already
played? Saves raw responses under docs/evidence/probe/<stamp>/cbs_napi_*.json plus a summary. Nothing live reads this."""
import datetime as dt
import json
import re
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "evidence" / "probe" / dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
# CBS game ids from data/lines/cbs_open_captures.csv: two played games, this week's opener, a week-6 game
GAMES = {"w3_MIN@TB_played": "50029242", "w4_NE@BUF_played": "50029213", "w5_TB@DAL": "50029260",
         "w6_WAS@SF": "50029286"}
PREFIXES = ["https://api.cbssports.com/napi", "https://api.cbssports.com"]   # the wrapper's host has no /napi; try both

urls = {}
for pfx in PREFIXES:
    tag = "napi" if pfx.endswith("napi") else "root"
    urls[f"{tag}_registry"] = f"{pfx}/resource/endpoint/registry"
    for g, gid in GAMES.items():
        urls[f"{tag}_odds_{g}"] = f"{pfx}/resource/odds/{gid}"
        urls[f"{tag}_game_odds_{g}"] = f"{pfx}/resource/game/odds/{gid}"
        urls[f"{tag}_hq_odds_{g}"] = f"{pfx}/resource/game/odds/hq/{gid}"
        urls[f"{tag}_splits_{g}"] = f"{pfx}/resource/game/bettingSplits/{gid}"
        if g.startswith("w5"):        # undocumented `state` values: see which, if any, change the answer
            for st in ("open", "opening", "pre", "current", "closing"):
                urls[f"{tag}_game_odds_{g}_state_{st}"] = f"{pfx}/resource/game/odds/{gid}?state={st}"

OPEN_RX = re.compile(r'"[A-Za-z_]*(open|Open|OPEN)[A-Za-z_]*"\s*:')
summary = []
for name, url in urls.items():
    rec = {"name": name, "url": url}
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=30)
        rec.update(status=r.status_code, bytes=len(r.content), ctype=r.headers.get("content-type", ""))
        (OUT / f"cbs_napi_{name}.json").write_text(r.text[:2_000_000])
        rec["open_keys"] = sorted(set(m.group(0).split('"')[1] for m in OPEN_RX.finditer(r.text)))[:20]
        try:
            j = r.json()
            d = j.get("data", j) if isinstance(j, dict) else j
            rec["top_keys"] = sorted(d.keys())[:30] if isinstance(d, dict) else f"list[{len(d)}]"
        except ValueError:
            rec["top_keys"] = "not json"
    except Exception as e:  # noqa: BLE001 - a probe records every failure
        rec["error"] = repr(e)
    summary.append(rec)
    print(json.dumps(rec)[:400])
(OUT / "cbs_napi_summary.json").write_text(json.dumps(summary, indent=1))
