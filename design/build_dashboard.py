"""Render design/dashboard.html from the data embedded in site/dashboard.html.

The live dashboard (built by engine.picks.dashboard) embeds its data as
`const D={...};`. This takes that same payload and drops it into the
scoreboard template, so the design can be reviewed on real data without
touching the pick pipeline.

    python design/build_dashboard.py
"""
import base64
import html
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "site" / "dashboard.html"
TEMPLATE = ROOT / "design" / "dashboard.template.html"
OUT = ROOT / "design" / "dashboard.html"
LOGOS = ROOT / "design" / "logos"


def main() -> None:
    m = re.search(r"const D=(\{.*?\});\n", SRC.read_text(), re.S)
    if not m:
        raise SystemExit(f"no data payload found in {SRC}")
    data = json.loads(m.group(1))
    logos = {p.stem: "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode() for p in sorted(LOGOS.glob("*.png"))}
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    page = TEMPLATE.read_text().replace("__DATA__", payload).replace("__LOGOS__", json.dumps(logos, separators=(",", ":"))).replace(
        "__TITLE__", html.escape(f"Week {data['week']} · Bonsai ATS"))
    OUT.write_text(page)
    print(f"wrote {OUT.relative_to(ROOT)} (week {data['week']}, record {data['record']})")


if __name__ == "__main__":
    main()
