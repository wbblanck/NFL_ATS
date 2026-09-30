"""Point-by-point explanation of a projected score.

Both projection models are multiplicative: a team's expected touchdowns and field goals are each
exp(sum of terms), where the terms are the league intercept, home field, the team's offense rating, minus the
opponent's defense rating, and (proj-players-v3 only) beta times each player/context feature. So the gap between a
league-average team and this team's projection can be split exactly among the terms: each term gets the share of
the gap equal to its share of the summed log terms (a log-share split; the pieces add up to the total). Expected
points are 6*TD + (p_xp + 2*p_2)*TD + 3*FG, the same scoring the model uses.
"""
from __future__ import annotations

import math

# (key, label) groups of v3 features, in display order
GROUPS = [
    ("qb", "Starting quarterback", ("qb_delta",)),
    ("own_inj", "Injuries on offense", ("ol", "skill")),
    ("opp_inj", "Opponent's defensive injuries", ("opp_dl", "opp_lb", "opp_db")),
    ("sched", "Rest and travel", ("rest_diff", "short_week", "off_bye", "tz_shift")),
    ("other", "Division game, roof, and calibration", ("division", "dome")),
]


def _split(total_gap: float, terms: dict[str, float]) -> dict[str, float]:
    """Share `total_gap` among terms in proportion to their log contributions (exact: shares sum to the gap)."""
    s = sum(terms.values())
    if abs(s) < 1e-12:
        return {k: 0.0 for k in terms}
    return {k: total_gap * v / s for k, v in terms.items()}


def team(rt, team_code: str, opp_code: str, home: int, feat: dict | None = None, model: dict | None = None,
         shown: float | None = None) -> dict:
    """Breakdown for one team. rt: projection.Ratings. feat/model: the v3 feature row and frozen model, or None
    for the team-only model. `shown` is the projected score displayed elsewhere (the mean of the exact score
    distribution, which differs from the formula's expected value by a few hundredths because the distribution is
    truncated); the pieces are scaled so they add up to it. Returns {'baseline', 'items', 'total'}."""
    n = len(rt.teams)
    i, j = rt.teams.index(team_code), rt.teams.index(opp_code)
    per_td = 6 + rt.p_xp + 2 * rt.p_2
    scale = {"td": per_td, "fg": 3.0}
    coefs = {"td": rt.td, "fg": rt.fg}
    parts: dict[str, float] = {}
    baseline = total = 0.0
    for kind in ("td", "fg"):
        b = coefs[kind]
        terms = {"off": float(b[2 + i]), "def": float(-b[2 + n + j]), "home": float(b[1] * home)}
        if feat is not None and model is not None:
            beta = model["beta"]
            terms["other"] = float(beta["intercept"][kind])
            for key, _, feats in GROUPS:
                terms[key] = terms.get(key, 0.0) + sum(float(beta[f][kind]) * float(feat[f]) for f in feats)
        base = scale[kind] * math.exp(float(b[0]))
        pts = base * math.exp(sum(terms.values()))
        baseline += base
        total += pts
        for k, v in _split(pts - base, terms).items():
            parts[k] = parts.get(k, 0.0) + v
    if shown is not None and abs(total - baseline) > 1e-6:
        k = (shown - baseline) / (total - baseline)
        parts = {key: v * k for key, v in parts.items()}
        total = shown
    labels = {"off": f"{team_code} offense", "def": f"{opp_code} defense", "home": "Home field",
              **{k: lab for k, lab, _ in GROUPS}}
    notes = _notes(team_code, opp_code, feat) if feat is not None else {}
    order = ["off", "def", "home"] + [k for k, _, _ in GROUPS]
    items = [{"key": k, "label": labels[k], "pts": round(parts[k], 2), "note": notes.get(k, "")}
             for k in order if k in parts and (k != "home" or home)]
    return {"baseline": round(baseline, 2), "items": items, "total": round(total, 2)}


def _signed(v: float, digits: int = 3) -> str:
    return ("+" if v > 0 else "−" if v < 0 else "") + f"{abs(v):.{digits}f}"


def _notes(team_code: str, opp_code: str, f: dict) -> dict[str, str]:
    """Plain facts behind each v3 adjustment, from the feature row."""
    out = {}
    starter = f.get("starter_name") or f.get("starter") or "the depth-chart starter"
    qd = f.get("qb_delta")
    if qd is not None:
        out["qb"] = f"{starter}: {_signed(qd)} EPA per dropback vs {team_code}'s usual passer" + (
            " (QB1 listed out)" if f.get("qb1_out") else "")
    own = [(lab, f.get(k)) for lab, k in (("line", "ol"), ("skill players", "skill")) if f.get(k)]
    out["own_inj"] = ("Expected missing snap share: " + ", ".join(f"{lab} {v:.2f}" for lab, v in own)) if own else \
        "No meaningful injuries reported"
    opp = [(lab, f.get(k)) for lab, k in (("DL", "opp_dl"), ("LB", "opp_lb"), ("DB", "opp_db")) if f.get(k)]
    out["opp_inj"] = (f"{opp_code} missing snap share: " + ", ".join(f"{lab} {v:.2f}" for lab, v in opp)) if opp else \
        f"No meaningful {opp_code} defensive injuries reported"
    bits = []
    if f.get("rest_diff"):
        bits.append(f"{f['rest_diff']:+.0f} days of rest vs opponent")
    if f.get("short_week"):
        bits.append("short week")
    if f.get("off_bye"):
        bits.append("coming off a bye")
    if f.get("tz_shift"):
        bits.append(f"{f['tz_shift']:.0f} time zone{'s' if abs(f['tz_shift']) != 1 else ''} of travel")
    out["sched"] = ", ".join(bits) if bits else "Normal rest, no travel across time zones"
    other = []
    if f.get("division"):
        other.append("division game")
    if f.get("dome") is not None:
        other.append("dome or closed roof" if f["dome"] else "open air")
    out["other"] = ", ".join(other).capitalize() if other else ""
    return out


def game(rt, home: str, away: str, fh: dict | None = None, fa: dict | None = None, model: dict | None = None,
         shown: tuple[float, float] | None = None) -> dict:
    """Both teams' breakdowns. Use v3 terms only when both feature rows are given. shown = (home, away) projected
    points as displayed."""
    v3 = fh is not None and fa is not None and model is not None
    sh, sa = shown if shown else (None, None)
    return {"home": team(rt, home, away, 1, fh if v3 else None, model if v3 else None, sh),
            "away": team(rt, away, home, 0, fa if v3 else None, model if v3 else None, sa),
            "model": "proj-players-v3" if v3 else "proj-poisson-v1"}
