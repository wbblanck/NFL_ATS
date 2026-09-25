"""Download SBRO NFL season odds pages (2007-08 .. 2021-22) into data/raw/sbro/.
Raw HTML is kept verbatim; parsing lives in engine.data.sbro."""
import hashlib
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/raw/sbro"
OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
for y in range(2007, 2022):
    slug = f"nfl-odds-{y}-{str(y + 1)[2:]}"
    url = f"https://www.sportsbookreviewsonline.com/scoresoddsarchives/{slug}/"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    print(slug, r.status_code, len(r.content))
    if r.ok:
        (OUT / f"{slug}.html").write_bytes(r.content)
        with open(OUT / "manifest.tsv", "a") as f:
            f.write(f"{slug}\t{url}\t{r.status_code}\t{hashlib.sha256(r.content).hexdigest()}\t"
                    f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n")
    time.sleep(2)
