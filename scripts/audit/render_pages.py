"""Render JavaScript-built pages in headless Chromium and save their visible
text + HTML under docs/evidence/rendered/<UTC stamp>/ (audit evidence)."""
import datetime as dt
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
urls = [u.strip() for u in (ROOT / "scripts/audit/render_urls.txt").read_text().splitlines()
        if u.strip() and not u.startswith("#")]
out = ROOT / "docs/evidence/rendered" / dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page()
    for u in urls:
        name = re.sub(r"[^A-Za-z0-9]+", "_", u.split("//", 1)[1])[:120]
        try:
            page.goto(u, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(5000)
            text = page.inner_text("body")
            (out / f"{name}.txt").write_text(f"URL: {u}\nFINAL: {page.url}\n\n{text}")
            (out / f"{name}.html").write_text(page.content())
            print(u, "->", len(text), "chars")
        except Exception as e:
            (out / f"{name}.error.txt").write_text(repr(e))
            print(u, "ERROR", e)
    b.close()
