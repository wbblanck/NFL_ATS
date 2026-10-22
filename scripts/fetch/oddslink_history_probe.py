"""OddsLink history discovery (research branch; run through oddslink-probe.yml, workflow_dispatch only).

Question: can OddsLink return NFL week 6 (2026-10-18) lines near each lock time? /odds lists only fixtures that
have not started, so this looks for the History endpoint family. Step 1 reads the public OpenAPI file and the
History guide (no key). Step 2 makes two authenticated calls (/events, then the plan) to see the fixture shape and
the allowance headers. The key comes only from env ODDSLINK_API_KEY and is never printed or saved.
Saves under docs/evidence/probe/<stamp>/oddslink_history_*.
"""
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

import requests

HOST = "https://oddslink.app"
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "evidence" / "probe" / dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
LOG = []
UA = {"User-Agent": "nfl-ats-engine/0.1"}


def log(s=""):
    print(s)
    LOG.append(s)


def public(path):
    try:
        r = requests.get(f"{HOST}{path}", headers=UA, timeout=60)
    except Exception as e:
        log(f"GET {path} failed: {type(e).__name__}")
        return None
    log(f"GET {path} -> HTTP {r.status_code}, {len(r.content)} bytes, {r.headers.get('content-type')}")
    return r if r.status_code == 200 else None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    log(f"# OddsLink history probe {OUT.name}\n")
    spec = None
    for p in ("/openapi.json", "/v1/openapi.json", "/api/openapi.json", "/openapi.yaml", "/v1/openapi.yaml"):
        r = public(p)
        if r is not None:
            (OUT / ("oddslink_history_openapi" + Path(p).suffix)).write_text(r.text[:3_000_000])
            try:
                spec = r.json()
            except ValueError:
                pass
            break
    if spec:
        for path, ops in (spec.get("paths") or {}).items():
            for verb, op in ops.items():
                if isinstance(op, dict):
                    log(f"  {verb.upper()} {path} :: {(op.get('summary') or '')[:90]} :: "
                        f"{[x.get('name') for x in op.get('parameters') or [] if isinstance(x, dict)]}")
    for p in ("/docs/guides/history/", "/docs/guides/history"):
        r = public(p)
        if r is not None:
            txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))
            (OUT / "oddslink_history_guide.txt").write_text(txt[:200_000])
            for m in re.finditer(r"(/v1/[A-Za-z0-9_{}/\-]+)", txt):
                log(f"  guide mentions {m.group(1)}")
            break
    key = os.environ.get("ODDSLINK_API_KEY", "")
    if key:
        hd = {"X-API-Key": key, "Accept": "application/json", **UA}
        for name, path, params in (
                ("usage", "/v1/account/usage", {}),
                ("hist_events", "/v1/historical/sports/nfl/events",
                 {"commenceTimeFrom": "2026-10-18T00:00:00.000Z", "commenceTimeTo": "2026-10-19T12:00:00.000Z", "limit": 25})):
            r = requests.get(f"{HOST}{path}", params=params, headers=hd, timeout=60)
            hdr = {k: v for k, v in r.headers.items() if any(w in k.lower() for w in ("remaining", "used", "plan"))}
            log(f"GET {path} -> HTTP {r.status_code}, {len(r.content)} bytes; headers {hdr}")
            log(f"  body: {r.text[:600]}")
            (OUT / f"oddslink_history_{name}.json").write_text(r.text[:500_000])
    else:
        log("ODDSLINK_API_KEY not set: skipped the authenticated calls")
    (OUT / "oddslink_history_summary.md").write_text("\n".join(LOG) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
