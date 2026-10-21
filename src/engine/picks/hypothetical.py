"""What the engine would have picked for live games it never picked (or picked with no market line).

HYPOTHETICAL. Nothing here is written to predictions.csv, the live record, the dashboard or any grade: the rule is
"never write, edit, or backfill picks after the fact". Output goes to data/hypothetical/ and docs/, labelled as such.

Pre-registered before any data was fetched (owner request 2026-10-20):
  Groups   no_row     live games (week >= 3, finished) with no pick row at all
           no_market  picks recorded with market_at_lock UNAVAILABLE (Parlay API outage, 2026-10-18)
           check      picks recorded with a Pinnacle market (known answers for the method)
  Method   Pinnacle's most balanced active full-game spread, from OddsPapi /historical-odds, as of kickoff - 20 min
           (the engine picks 5 min before the lock, lock = kickoff - 15); pool line from league_lines.csv; the
           engine's own model fit on games that had finished before then (final.fit_total_dist, else fit_dist, with
           the schedule's total); final.decide() for the pick; graded against the pool line like live.py.
  Check    for the `check` group, report how often the OddsPapi line equals the recorded market_at_lock and how often
           the pick matches. Reported as agreement, not gated; a low agreement means the history cannot stand in
           for the live capture and the hypothetical picks should not be trusted.
  Limits   A game with no Pinnacle snapshot by the cutoff gets no hypothetical pick (status says why).
           Small n: this says what the picks would have been, nothing about skill.
"""
from __future__ import annotations

import csv
import datetime as dt
import sys
from pathlib import Path

from engine import config
from engine.data import league_lines, nflverse, oddspapi
from engine.picks import final
from engine.picks.grading import Result, grade_league
from engine.teams import UnknownTeam, to_canonical

PICK_LEAD = dt.timedelta(minutes=20)
# A game's result was only available to a pick once the game had ended: games that kicked off in the hours before the
# pick were still being played. Checked on every 2026 pick with a market: 41 of 44 reproduce the recorded cover chance.
FINISHED_AFTER = dt.timedelta(hours=4)
FIELDS = ["group", "game_id", "kickoff_utc", "as_of_utc", "status", "pinnacle_home_spread", "first_snapshot_utc",
          "n_lines", "hold", "league_line", "drift", "p_home_cover", "pick_team", "flags", "final_score", "result",
          "recorded_market", "recorded_pick", "same_line", "same_pick"]


def groups(sched_rows: list[dict], preds: dict[str, dict], first_week: int = 3) -> dict[str, list[dict]]:
    out = {"no_row": [], "no_market": [], "check": []}
    for g in sched_rows:
        if g["season"] != 2026 or g["week"] < first_week or g.get("result") is None:
            continue
        p = preds.get(g["game_id"])
        if p is None:
            out["no_row"].append(g)
        elif p["market_at_lock"] in ("", "UNAVAILABLE"):
            out["no_market"].append(g)
        elif p.get("feature_version") == "market:pinnacle":
            out["check"].append(g)
    return out


def reconstruct(g: dict, group: str, pinnacle_hist: dict | None, smap: dict, league_line: float | None,
                tdist, mdist, pred: dict | None = None) -> dict:
    """One game's hypothetical pick row (pure: no network, no files)."""
    t = g["kickoff_utc"] - PICK_LEAD
    row = {k: "" for k in FIELDS}
    row.update(group=group, game_id=g["game_id"], kickoff_utc=g["kickoff_utc"].isoformat(), as_of_utc=t.isoformat(),
               league_line="" if league_line is None else league_line,
               final_score=f"{g['away_score']}-{g['home_score']}")
    if pred:
        row["recorded_market"], row["recorded_pick"] = pred["market_at_lock"], pred["pick_team"]
    if league_line is None:
        row["status"] = "no pool line in league_lines.csv"
        return row
    m = oddspapi.main_spread_at(pinnacle_hist or {}, smap, t) if pinnacle_hist else None
    if not m:
        row["status"] = "no active Pinnacle full-game spread by the cutoff" if pinnacle_hist else "no history returned"
        return row
    total = g.get("total_line")
    use_t = tdist is not None and total is not None
    prob = (lambda a, b, T=total: tdist.cover_probs(a, b, T)) if use_t else mdist
    d = final.decide(league_line, m["home_spread"], None, prob)
    pick = g["home_team"] if d["pick"] == "home" else g["away_team"]
    res = grade_league(g["home_score"], g["away_score"], league_line)
    won = (d["pick"] == "home") == (res is Result.HOME_COVER)
    flags = [f for f in d["flags"].split(";") if f] + ["HYPOTHETICAL", "MARKET_ODDSPAPI_HISTORY"]
    if not use_t:
        flags.append("NO_TOTAL_SHIFTED_FALLBACK")
    else:
        flags.append("TOTAL_FROM_SCHEDULE")
    row.update(status="ok", pinnacle_home_spread=m["home_spread"], first_snapshot_utc=m.get("first_seen") or "",
               n_lines=m.get("n_lines", ""), hold=m["hold"], drift=d["drift"], p_home_cover=round(d["p_home"], 4),
               pick_team=pick, flags=";".join(flags), result="W" if won else "L")
    if pred and group == "check":
        row["same_line"] = int(abs(float(pred["market_at_lock"]) - m["home_spread"]) < 1e-9)
        row["same_pick"] = int(pred["pick_team"] == pick)
    return row


def _fixture_ids(games: list[dict], call_fn) -> dict[str, str]:
    """game_id -> OddsPapi fixtureId, from /fixtures per week (home = participant1, verified 2026-10-18)."""
    out, weeks = {}, {}
    for g in games:
        weeks.setdefault(g["week"], []).append(g)
    for wk, gs in sorted(weeks.items()):
        lo = min(g["kickoff_utc"] for g in gs) - dt.timedelta(hours=12)
        hi = max(g["kickoff_utc"] for g in gs) + dt.timedelta(hours=12)
        _, fx = call_fn("fixtures", tournamentId=oddspapi.NFL_TOURNAMENT,
                        **{"from": lo.strftime("%Y-%m-%dT%H:%M:%SZ"), "to": hi.strftime("%Y-%m-%dT%H:%M:%SZ")})
        names = {}
        for f in oddspapi.items_of(fx):
            try:
                names[(to_canonical(f.get("participant1Name") or ""), to_canonical(f.get("participant2Name") or ""))] = f["fixtureId"]
            except (UnknownTeam, KeyError):
                continue
        for g in gs:
            fid = names.get((g["home_team"], g["away_team"]))
            if fid:
                out[g["game_id"]] = fid
    return out


def run(call_fn=None, sched=None, out_dir: Path | None = None) -> list[dict]:
    call_fn = call_fn or oddspapi.call
    sched = sched if sched is not None else nflverse.regular_season_schedule(save=False)[0]
    rows_s = sched.filter(sched["season"] == 2026).to_dicts()
    preds = {r["game_id"]: r for r in csv.DictReader(open(final.predictions_path())) if not r.get("supersedes")}
    ll = {r["game_id"]: float(r["spread"]) for r in league_lines.load()}
    smap = oddspapi.load_spread_markets(config.path("lines") / oddspapi.SPREAD_MARKETS_FILE)
    gr = groups(rows_s, preds)
    allg = [(k, g) for k, gs in gr.items() for g in gs]
    print({k: len(v) for k, v in gr.items()}, file=sys.stderr)
    fids = _fixture_ids([g for _, g in allg], call_fn)
    models, out = {}, []
    for k, g in allg:
        t = g["kickoff_utc"] - PICK_LEAD
        when = t - FINISHED_AFTER
        key = int(sched.filter(sched["result"].is_not_null() & (sched["kickoff_utc"] < when)).height)
        if key not in models:
            models[key] = (final.fit_total_dist(sched, when), final.fit_dist(sched, when)[0])
        hist = None
        if g["game_id"] in fids:
            _, h = call_fn("historical-odds", pause=5.5, fixtureId=fids[g["game_id"]], bookmakers="pinnacle")
            hist = ((h or {}).get("bookmakers") or {}).get("pinnacle")
        row = reconstruct(g, k, hist, smap, ll.get(g["game_id"]), *models[key], pred=preds.get(g["game_id"]))
        if g["game_id"] not in fids:
            row["status"] = "game not found in OddsPapi fixtures"
        out.append(row)
        print(k, g["game_id"][5:], row["status"], row["pick_team"], row["result"], file=sys.stderr)
    out_dir = out_dir or Path(config.path("lines")).parent / "hypothetical"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "missed_picks_2026-10-20.csv"
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, FIELDS)
        w.writeheader()
        w.writerows(out)
    return out


def report(rows: list[dict]) -> str:
    ok = [r for r in rows if r["status"] == "ok"]
    L = ["# Missed picks, reconstructed (HYPOTHETICAL)", "",
         "Not part of the live record. Pinnacle from OddsPapi history as of 20 minutes before kickoff, the engine's own "
         "model and pick rule, graded against the pool line. Written 2026-10-20 from `data/hypothetical/missed_picks_2026-10-20.csv`.", ""]
    for k, title in (("check", "Known answers: picks that were made with Pinnacle"), ("no_row", "Games with no pick row"),
                     ("no_market", "Picks recorded with no market line")):
        g = [r for r in rows if r["group"] == k]
        o = [r for r in g if r["status"] == "ok"]
        L.append(f"## {title}")
        L.append(f"{len(o)} of {len(g)} games reconstructed" + ("" if len(o) == len(g) else
                 "; the rest: " + ", ".join(f"{r['game_id'][8:]} ({r['status']})" for r in g if r["status"] != "ok")))
        if k == "check" and o:
            sl, sp = sum(int(r["same_line"]) for r in o), sum(int(r["same_pick"]) for r in o)
            L.append(f"The OddsPapi line equals the recorded market line on **{sl} of {len(o)}**; the pick matches on **{sp} of {len(o)}**.")
        elif o:
            w = sum(r["result"] == "W" for r in o)
            L += ["", "| Game | Pinnacle (home) | Pool line (home) | Pick | Cover chance | Final | Result |", "|---|---|---|---|---|---|---|"]
            L += [f"| {r['game_id'][8:]} | {r['pinnacle_home_spread']} | {r['league_line']} | {r['pick_team']} | {float(r['p_home_cover']):.3f} home | {r['final_score']} (away-home) | {r['result']} |" for r in o]
            L.append(f"\nHypothetical record: {w}-{len(o) - w}. With {len(o)} games this says what the picks would have been, nothing about skill.")
        L.append("")
    return "\n".join(L)


def main() -> int:
    key = oddspapi.request_count()
    rows = run()
    after = oddspapi.request_count()
    Path(config.path("lines")).parent.joinpath("hypothetical").mkdir(exist_ok=True)
    doc = Path(__file__).resolve().parents[3] / "docs" / "missed_picks_report.md"
    doc.write_text(report(rows) + f"\nOddsPapi requests: {key[0]} -> {after[0]} of {after[1]}.\n")
    print(f"requests {key[0]} -> {after[0]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
