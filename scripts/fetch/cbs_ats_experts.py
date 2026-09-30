"""Fetch CBS's expert against-the-spread pages for 2026 weeks 1-4 (a candidate source of the pool's lines;
checked against the recorded week 3-4 pool lines before use). Saves raw HTML under docs/evidence/probe/."""
import datetime as dt
import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "evidence" / "probe" / dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT.mkdir(parents=True, exist_ok=True)
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
summary = []
for week in (1, 2, 3, 4):
    url = f"https://www.cbssports.com/nfl/picks/experts/against-the-spread/{week}/"
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept": "text/html"}, timeout=45)
        (OUT / f"cbs_ats_2026_w{week}.html").write_text(r.text)
        summary.append({"url": url, "status": r.status_code, "bytes": len(r.content), "final_url": r.url})
    except Exception as e:
        summary.append({"url": url, "error": repr(e)})
    print(summary[-1])
(OUT / "summary.json").write_text(json.dumps(summary, indent=1))
