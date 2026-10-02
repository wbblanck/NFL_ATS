"""Private viewer for the picks dashboard on Streamlit Community Cloud.

The page itself is built by GitHub Actions (publish-dashboard.yml) and committed as site/dashboard.html after every
group of picks and on the score schedule; this app only displays the latest committed copy."""
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="NFL ATS picks", page_icon="🏈", layout="wide")
st.markdown("<style>.block-container{padding:0.25rem 0.25rem 0;max-width:100%}"
            "header[data-testid='stHeader']{display:none}</style>", unsafe_allow_html=True)

page = Path(__file__).resolve().parent.parent / "site" / "dashboard.html"
if page.exists():
    doc = ("<!doctype html><html><head><meta charset='utf-8'>"
           "<meta name='viewport' content='width=device-width,initial-scale=1'></head><body>"
           + page.read_text(encoding="utf-8") + "</body></html>")
    components.html(doc, height=2600, scrolling=True)
else:
    st.error("The dashboard has not been built yet: run the 'Publish dashboard' workflow on GitHub.")
