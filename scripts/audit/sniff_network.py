"""Load pages in headless Chromium and log every XHR/fetch request, with a
short body sample for JSON responses that mention spreads. Purpose: find
whether CBS Pick'em spreads are served by a public (no-login) endpoint.
Output: docs/evidence/network/<UTC stamp>/requests.jsonl (+ matched bodies)."""
import datetime as dt
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
PAGES = [u.strip() for u in (ROOT / "scripts/audit/sniff_urls.txt").read_text().splitlines()
         if u.strip() and not u.startswith("#")]
out = ROOT / "docs/evidence/network" / dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
out.mkdir(parents=True, exist_ok=True)
log = open(out / "requests.jsonl", "w")
hits = 0
KEY = re.compile(r"spread|winningMargin|pointSpread|line", re.I)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    page = ctx.new_page()

    def on_response(r):
        global hits
        req = r.request
        if req.resource_type not in ("xhr", "fetch"):
            return
        rec = {"page": page.url, "method": req.method, "url": r.url, "status": r.status,
               "ctype": r.headers.get("content-type", ""), "post": (req.post_data or "")[:2000]}
        try:
            body = r.text()
        except Exception:
            body = ""
        rec["bytes"] = len(body)
        if "json" in rec["ctype"] and KEY.search(body):
            hits += 1
            (out / f"hit_{hits:03d}.json").write_text(json.dumps({**rec, "body": body[:200000]}))
            rec["hit_file"] = f"hit_{hits:03d}.json"
        log.write(json.dumps(rec) + "\n")

    page.on("response", on_response)
    for u in PAGES:
        try:
            page.goto(u, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(8000)
            (out / (re.sub(r"[^A-Za-z0-9]+", "_", u.split("//", 1)[1])[:100] + ".txt")).write_text(
                f"URL: {u}\nFINAL: {page.url}\n\n" + page.inner_text("body"))
            print(u, "->", page.url)
        except Exception as e:
            print(u, "ERROR", e)
    b.close()
log.close()
print("json hits:", hits)
