"""Refresh the checkout right before a waiting lock run picks.

A lock run with `wait` true checks out the branch when it starts, then sleeps up to an hour before it picks. Pool lines
merged during that wait were not in the checkout, so on 2026-11-26 PHI@DAL was picked with no pool line (it fell back to
the CBS open, -1.5, instead of the real -8.5). This pulls the latest branch just before the pick.

Safety rules, because this runs inside the live pick path:
  * It never raises and never blocks a pick: every failure becomes a printed status and the pick goes ahead as before.
  * It only fast-forwards, and only when everything that changed upstream is data, docs or site files. If code, a
    workflow, or the packaging changed, it leaves the checkout alone (modules are loaded lazily, so code that changes
    under a running process could mix old and new) and says so; the run's final pull/rebase picks it up afterwards.
  * It does nothing unless LOCK_RUN_SYNC_REF names the branch (the workflow sets it), so local runs are unchanged.
"""
from __future__ import annotations

import os
import subprocess

ENV_REF = "LOCK_RUN_SYNC_REF"
SAFE_PREFIXES = ("data/", "docs/", "site/")
TIMEOUT_S = 60


def _git(*args: str, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT_S)


def sync_before_pick(ref: str | None = None, cwd=None) -> str:
    """Fast-forward the checkout to the latest origin/<ref> when that cannot touch code. Returns a one-line status."""
    ref = ref or os.environ.get(ENV_REF)
    if not ref:
        return "SYNC off (no LOCK_RUN_SYNC_REF)"
    try:
        f = _git("fetch", "--quiet", "origin", ref, cwd=cwd)
        if f.returncode:
            return f"SYNC skipped: fetch failed ({f.stderr.strip()[:120]})"
        if _git("merge-base", "--is-ancestor", "HEAD", "FETCH_HEAD", cwd=cwd).returncode == 0:
            changed = _git("diff", "--name-only", "HEAD", "FETCH_HEAD", cwd=cwd).stdout.split()
            if not changed:
                return "SYNC ok: already up to date"
            code = [p for p in changed if not p.startswith(SAFE_PREFIXES)]
            if code:
                return (f"SYNC skipped: {len(code)} code/workflow file(s) changed upstream "
                        f"(e.g. {code[0]}); pool lines may be stale")
            m = _git("merge", "--ff-only", "--quiet", "FETCH_HEAD", cwd=cwd)
            if m.returncode:
                return f"SYNC skipped: fast-forward refused ({m.stderr.strip()[:120]})"
            lines = [p for p in changed if p.startswith("data/lines/")]
            return f"SYNC ok: fast-forwarded {len(changed)} file(s), {len(lines)} under data/lines"
        return "SYNC skipped: local commits not on origin yet"
    except Exception as e:   # never block a pick
        return f"SYNC skipped: {type(e).__name__}: {e}"
