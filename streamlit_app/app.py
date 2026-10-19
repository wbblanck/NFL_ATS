"""Private viewer for the picks dashboard on Streamlit Community Cloud.

The page itself is built by GitHub Actions (publish-dashboard.yml) and committed as site/dashboard.html after every
group of picks and on the score schedule; this app displays the latest committed copy, plus a live-scores strip
fetched from ESPN on each page load (live.py)."""
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="NFL ATS picks", page_icon="🏈", layout="wide")
st.markdown("<style>.block-container{padding:0.25rem 0.25rem 0;max-width:100%}"
            "header[data-testid='stHeader']{display:none}</style>", unsafe_allow_html=True)

import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
import live  # noqa: E402  (streamlit_app/live.py: live scores on each page load)


@st.cache_data(ttl=20, show_spinner=False)
def _live_strip() -> str:
    try:
        return live.render(live.cards(live.live_games(live.fetch_scoreboard()), live.load_picks()))
    except Exception:            # live scores are a nice-to-have: never break the dashboard
        return ""


site = Path(__file__).resolve().parent.parent / "site"
view = "Classic"
if (site / "terminal.html").exists():
    view = st.radio("View", ["Classic", "Terminal (new)"], horizontal=True, label_visibility="collapsed")
if view != "Classic":                 # the redesigned page (engine/picks/terminal_page.py); a full document of its own
    components.html((site / "terminal.html").read_text(encoding="utf-8"), height=2600, scrolling=True)
    st.stop()
page = site / "dashboard.html"
if page.exists():
    doc = ("<!doctype html><html><head><meta charset='utf-8'>"
           "<meta name='viewport' content='width=device-width,initial-scale=1'></head><body>"
           + live.inject(page.read_text(encoding="utf-8"), _live_strip()) + "</body></html>")
    components.html(doc, height=2600, scrolling=True)
else:
    st.error("The dashboard has not been built yet: run the 'Publish dashboard' workflow on GitHub.")
