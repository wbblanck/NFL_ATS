"""Loss review for the dashboard: every official loss with the pick's cover margin through the game (from nflverse
play-by-play), where it stood with 5:00 left in regulation, turnovers, and plain tags for what kind of loss it was.
Wins are read too, only to count the late swings that went our way (luck runs both directions).

Cover margin = the picked team's points minus the opponent's plus the pick's pool line (LAC +7.5 down 8 = -0.5).
Descriptive only: nothing here feeds the pick (late-score and turnover luck failed as pick inputs,
docs/turnover_luck_report.md)."""
from __future__ import annotations

import polars as pl

LATE_MIN = 55.0          # 5:00 left in regulation, in minutes elapsed
TAGS = {"late": "Lost in last 5:00", "hook": "By the hook", "close": "Within a FG", "far": "Not close",
        "never": "Never covered", "to_lost": "Lost turnovers", "to_won": "Won turnovers", "ot": "Overtime"}


def _elapsed(qtr: float, qsr: float) -> float:
    """Minutes since kickoff; overtime periods are 10 minutes."""
    q = int(qtr)
    return round(((q - 1) * 900 + 900 - qsr) / 60, 2) if q <= 4 else round((3600 + (q - 5) * 600 + 600 - qsr) / 60, 2)


def game_paths(pbp: pl.DataFrame) -> dict[str, dict]:
    """game_id -> {'pts': [[min, home, away], ...] at kickoff and every score change, 'end': min,
    'to': [[min, team], ...] for interceptions and lost fumbles (the team that gave the ball away)}."""
    p = pbp.select("game_id", "play_id", "qtr", "quarter_seconds_remaining", "total_home_score", "total_away_score",
                   "interception", "fumble_lost", "fumbled_1_team", "posteam") \
        .drop_nulls(["qtr", "quarter_seconds_remaining", "total_home_score", "total_away_score"]) \
        .sort("game_id", "play_id")
    out: dict[str, dict] = {}
    for gid, g in p.group_by("game_id", maintain_order=True):
        gid = gid[0]
        pts, tos, last, end = [[0.0, 0, 0]], [], (0, 0), 0.0
        for r in g.iter_rows(named=True):
            t = _elapsed(r["qtr"], r["quarter_seconds_remaining"])
            end = max(end, t)
            s = (int(r["total_home_score"]), int(r["total_away_score"]))
            if s != last:
                pts.append([t, s[0], s[1]])
                last = s
            if r["interception"] == 1 and r["posteam"]:
                tos.append([t, r["posteam"]])
            elif r["fumble_lost"] == 1 and r["fumbled_1_team"]:
                tos.append([t, r["fumbled_1_team"]])
        out[gid] = {"pts": pts, "end": max(end, 60.0), "to": tos}
    return out


def _cov(home_margin: float, pick_is_home: bool, home_line: float) -> float:
    s = 1 if pick_is_home else -1
    return s * (home_margin + home_line)


def build(graded: list[dict], preds: list[dict], sched: pl.DataFrame, paths: dict[str, dict]) -> dict:
    """{'losses': [...], 'summary': {...}} over the season's graded official picks, newest week first."""
    pred_by = {p["game_id"]: p for p in preds if not p.get("supersedes")}
    sc = {r["game_id"]: r for r in sched.select("game_id", "home_team", "away_team", "home_score", "away_score")
          .iter_rows(named=True)}
    losses, won_late = [], 0
    for r in graded:
        gid, g, p = r["game_id"], sc.get(r["game_id"]), pred_by.get(r["game_id"])
        if g is None or p is None or g["home_score"] is None:
            continue
        home, away, ln = g["home_team"], g["away_team"], float(r["league_line"])
        ph = r["pick"] == home
        opp = away if ph else home
        fin = _cov(g["home_score"] - g["away_score"], ph, ln)
        path = paths.get(gid)
        flow, cov5, tos = None, None, [0, 0]
        if path:
            flow = [[t, _cov(h - a, ph, ln), a, h] for t, h, a in path["pts"]]
            if flow[-1][0] < path["end"]:
                flow.append([path["end"], flow[-1][1], flow[-1][2], flow[-1][3]])
            cov5 = [f[1] for f in flow if f[0] <= LATE_MIN][-1]
            tos = [sum(1 for _, tm in path["to"] if tm == r["pick"]), sum(1 for _, tm in path["to"] if tm == opp)]
        if r["result"] == "W":
            won_late += cov5 is not None and cov5 < 0 < fin
            continue
        tags = []
        if cov5 is not None and cov5 > 0 > fin:
            tags.append("late")
        if fin >= -1:
            tags.append("hook")
        elif fin >= -3:
            tags.append("close")
        if fin <= -7:
            tags.append("far")
        if flow and all(f[1] <= 0 for f in flow[1:]):                      # not covering at any point after the first score
            tags.append("never")
        if tos[0] - tos[1] >= 2:
            tags.append("to_lost")
        if tos[1] - tos[0] >= 2:
            tags.append("to_won")
        if path and path["end"] > 60:
            tags.append("ot")
        pl_line = ln if ph else -ln
        pk = (p.get("p_home_cover") if p.get("pick") == "home" else p.get("p_away_cover"))
        losses.append({
            "id": gid, "week": int(r["week"]), "away": away, "home": home, "pick": r["pick"], "opp": opp,
            "line": pl_line, "fin": fin, "cov5": cov5, "as": int(g["away_score"]), "hs": int(g["home_score"]),
            "drift": float(p["drift"]) if p.get("drift") not in (None, "", "UNAVAILABLE") else None,
            "p": float(pk) if pk not in (None, "", "UNAVAILABLE") else None, "to": tos, "tags": tags,
            "peak": max((f[1] for f in flow[1:]), default=None) if flow else None,
            "flow": flow, "tos": [[t, "pick" if tm == r["pick"] else "opp"] for t, tm in (path or {}).get("to", [])],
            "others": {k: (r.get(f) or "").strip()[-1:] or None for k, f in
                       (("hybrid", "hybrid"), ("v1", "proj_proj-poisson-v1"), ("v3", "proj_proj-players-v3"),
                        ("keynum", "shadow_result"))}})
    losses.sort(key=lambda x: (-x["week"], x["id"]))
    n = len(losses)
    count = lambda t: sum(t in x["tags"] for x in losses)
    return {"losses": losses, "summary": {
        "n": n, "late": count("late"), "fg": count("hook") + count("close"), "far": count("far"),
        "never": count("never"), "won_late": int(won_late), "to_lost": count("to_lost"),
        "to_gave": sum(x["to"][0] for x in losses), "to_took": sum(x["to"][1] for x in losses)}}
