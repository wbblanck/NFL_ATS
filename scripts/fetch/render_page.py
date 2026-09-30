"""Render a JavaScript page (e.g. a Streamlit app) in headless Chromium on a GitHub runner and save its visible
text and full-page screenshots under docs/evidence/probe/<stamp>/. URL list in RENDER_URLS (one per line)."""
import datetime as dt
import os
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "evidence" / "probe" / dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT.mkdir(parents=True, exist_ok=True)
urls = [u.strip() for u in os.environ["RENDER_URLS"].splitlines() if u.strip()]
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1400, "height": 1000})
    for i, url in enumerate(urls):
        name = f"render_{i}_" + re.sub(r"[^A-Za-z0-9]+", "_", url)[-60:]
        try:
            pg.goto(url, wait_until="networkidle", timeout=90_000)
            pg.wait_for_timeout(20_000)                      # Streamlit renders after the websocket connects
            for fr in pg.frames:                              # Streamlit Cloud serves the app in an iframe
                if fr != pg.main_frame and "streamlit" in (fr.url or ""):
                    try:
                        fr.wait_for_selector("[data-testid='stAppViewContainer'], .main", timeout=30_000)
                    except Exception:
                        pass
            texts = []
            for fr in pg.frames:
                try:
                    texts.append(f"--- frame {fr.url}\n" + fr.evaluate("document.body ? document.body.innerText : ''"))
                except Exception as e:
                    texts.append(f"--- frame {fr.url} ERROR {e!r}")
            (OUT / f"{name}.txt").write_text("\n".join(texts))
            pg.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
            print(url, "ok", sum(len(t) for t in texts), "chars")
        except Exception as e:
            (OUT / f"{name}.txt").write_text(f"ERROR {e!r}")
            print(url, "ERROR", e)
    b.close()
