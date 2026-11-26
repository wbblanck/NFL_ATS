"""Tracked-model comparison family (docs/tracked_models_preregistration.md).

Read-only analysis of the live record: for each tracked model (v1, v3, Hybrid, Key-number), on the games where it
picked a different side than the Official pick, did it win more than half of them? One-sided exact binomial test per
model, Holm-corrected over the family of 4, with a minimum of 100 differing games before any test counts.
Nothing here changes a pick, a grade, or the live record.

    python -m engine.backtest.tracked_family --since 2026-11-26T18:00:00+00:00
"""
from __future__ import annotations

import argparse
import datetime as dt
import math

MIN_DIFFERING = 100
ALPHA = 0.05
FAMILY = ("proj-poisson-v1", "proj-players-v3", "hybrid", "keynum")
LABELS = {"proj-poisson-v1": "Team-only projection (v1)", "proj-players-v3": "Player projection (v3)",
          "hybrid": "Hybrid", "keynum": "Key-number"}


def exact_upper_tail(k: int, n: int) -> float:
    """P(X >= k) for X ~ Binomial(n, 1/2), exact."""
    if n == 0:
        return 1.0
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n


def holm(pvals: dict[str, float], alpha: float = ALPHA) -> dict[str, dict]:
    """Holm step-down over the whole family. Returns each key's threshold and pass flag (a pass needs every smaller
    p-value before it to have passed too)."""
    order = sorted(pvals, key=lambda k: pvals[k])
    m, out, stop = len(order), {}, False
    for i, k in enumerate(order):
        thr = alpha / (m - i)
        ok = (not stop) and pvals[k] <= thr
        stop = stop or not ok
        out[k] = {"p": pvals[k], "threshold": thr, "pass": ok}
    return out


def differing(rows: list[dict], key: str) -> tuple[int, int]:
    """(model right, official right) on the rows where the model's pick differs from the Official pick."""
    mr = orr = 0
    for r in rows:
        pick, res = _model_pick(r, key)
        if pick is None or pick == r["pick"]:
            continue
        mr += res == "W"
        orr += res != "W"
    return mr, orr


def _model_pick(r: dict, key: str) -> tuple[str | None, str | None]:
    """(team picked, 'W'/'L' for that team) for one graded row, or (None, None) when the model has no pick."""
    if key == "keynum":
        return (r.get("shadow_pick") or None), (r.get("shadow_result") or None)
    cell = r.get("hybrid") if key == "hybrid" else r.get(f"proj_{key}")
    if not cell:
        return None, None
    team, _, res = cell.rpartition(" ")
    return team, res


def evaluate(rows: list[dict]) -> dict:
    res, pv = {}, {}
    for key in FAMILY:
        mr, orr = differing(rows, key)
        n = mr + orr
        res[key] = {"label": LABELS[key], "differing": n, "model_right": mr, "official_right": orr,
                    "p": exact_upper_tail(mr, n), "enough": n >= MIN_DIFFERING}
        pv[key] = res[key]["p"]
    h = holm(pv)
    for key in FAMILY:
        res[key].update(threshold=h[key]["threshold"],
                        passes=bool(res[key]["enough"] and h[key]["pass"]))
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True, help="ISO UTC time: only picks created at or after it count")
    a = ap.parse_args()
    since = dt.datetime.fromisoformat(a.since)
    from engine.data import nflverse, store
    from engine.picks import final, live
    sched = nflverse.regular_season_schedule(save=False)[0]
    _, rows = live.compute(sched)
    made = {p["game_id"]: p["created_at"] for p in store.read_rows(final.predictions_path())}
    rows = [r for r in rows if dt.datetime.fromisoformat(made[r["game_id"]]) >= since]
    print(f"Games graded since {a.since}: {len(rows)}")
    out = evaluate(rows)
    for k, v in out.items():
        print(f"{v['label']:28s} differing {v['differing']:3d}: model right {v['model_right']}, Official right "
              f"{v['official_right']}; one-sided p {v['p']:.4f}, Holm bar {v['threshold']:.4f}; "
              + ("PASS" if v["passes"] else "no pass" + ("" if v["enough"] else f" (needs {MIN_DIFFERING} differing games)")))


if __name__ == "__main__":
    main()
