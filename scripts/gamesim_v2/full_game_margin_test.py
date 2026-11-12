"""Full-game development test, stage 2: pregame lineup margin shift (passing and running, both sides) against the closing line and team form,
2019-2021 (docs/gamesim_v2/PREREGISTRATION_full_game_dev.md and AMENDMENT1). Seasons after 2021 are never loaded.
Usage: python scripts/gamesim_v2/full_game_margin_test.py            (primary, ridge 3,000)
       G2_FULL_LAM=100 python scripts/gamesim_v2/full_game_margin_test.py   (original preregistered ridge, secondary)"""
from __future__ import annotations
import json, os
from pathlib import Path
import numpy as np
import polars as pl
from engine.gamesim_v2.data.identity import FRANCHISE
from engine.gamesim_v2.players.abilities_full import OFF, DEF

ROOT = Path(__file__).resolve().parents[2]
FEAT, MAN = ROOT / "data/gamesim_v2/features", ROOT / "data/gamesim_v2/manifests"
SEASONS = (2019, 2020, 2021)
RIDGE = int(float(os.environ.get("G2_FULL_LAM", "3000")))
SUFFIX = "" if RIDGE == 3000 else f"_lam{RIDGE}"
NBOOT, SEED = 10000, 20261112


def ratings(kind):
    t = pl.read_parquet(FEAT / f"abilities_full_{kind}{SUFFIX}.parquet").filter(pl.col("key").str.contains(":"))
    out = {}
    for s, w, k, b, se, nr in t.select("season", "week", "key", "beta", "se", "n_raw").iter_rows():
        out.setdefault((s, w), {})[k] = (b, se, nr)
    return out


def team_shift(players, tab, side, pos_s, s):
    """players: list of (uid, pos_grp, weight). Returns (sum weight*beta, weight on unrated, weight on no-position, slot rows)."""
    groups = OFF if side == "O" else DEF
    v, unrated, nopos, slots = 0.0, 0.0, 0.0, []
    for uid, g, wt in players:
        if wt is None or wt <= 0:
            continue
        if g not in groups:
            if g is None:
                nopos += wt
            continue
        key = f"{side}_{g}:{uid}"
        r = tab.get(key)
        if r is None:
            g2 = pos_s.get((s, uid))
            r = tab.get(f"{side}_{g2}:{uid}") if g2 in groups else None
        if r is None:
            unrated += wt
            slots.append((wt, None))
            continue
        v += wt * r[0]
        slots.append((wt, r[1]))
    return v, unrated, nopos, slots


def ols(X, y):
    return np.linalg.lstsq(X, y, rcond=None)[0]


def boot_coef(X, y, clusters, rng, n=NBOOT):
    u = np.unique(clusters); idx = {c: np.where(clusters == c)[0] for c in u}
    bs = np.empty(n)
    for i in range(n):
        ix = np.concatenate([idx[c] for c in rng.choice(u, len(u))])
        bs[i] = ols(X[ix], y[ix])[-1]
    return [float(v) for v in np.percentile(bs, [2.5, 97.5])]


def lowo(X0, X1, y, blocks):
    e0, e1 = np.zeros(len(y)), np.zeros(len(y))
    for b in np.unique(blocks):
        te, tr = blocks == b, blocks != b
        e0[te] = (y[te] - X0[te] @ ols(X0[tr], y[tr])) ** 2
        e1[te] = (y[te] - X1[te] @ ols(X1[tr], y[tr])) ** 2
    return e1 - e0


def boot_mean_by_block(dv, blocks, rng, n=NBOOT):
    u = np.unique(blocks); sums = np.array([dv[blocks == b].sum() for b in u]); cnt = np.array([(blocks == b).sum() for b in u])
    bs = np.empty(n)
    for i in range(n):
        k = rng.integers(0, len(u), len(u)); bs[i] = sums[k].sum() / cnt[k].sum()
    return [float(v) for v in np.percentile(bs, [2.5, 97.5])]


def form_margin(sched, hl=6.0, k=2.0):
    """Exponentially weighted margin form per team before each game (games-ago half-life, prior weight k toward 0), from 2016 on."""
    hist, f = {}, {}
    for gid, h, a, m in sched.sort("gameday", "game_id").select("game_id", "home_team", "away_team", "result").iter_rows():
        def est(t):
            x = hist.get(t, [])
            if not x:
                return 0.0
            w = 0.5 ** ((len(x) - 1 - np.arange(len(x))) / hl)
            return float(w @ np.array(x) / (w.sum() + k))
        f[gid] = est(h) - est(a)
        hist.setdefault(h, []).append(m); hist.setdefault(a, []).append(-m)
    return f


def main():
    rg = json.loads((MAN / f"full_game_ratings{SUFFIX}.json").read_text())
    n_pass, n_run = rg["plays_per_team_game_2016_2018"]["pass"], rg["plays_per_team_game_2016_2018"]["run"]
    RP, RR = ratings("pass"), ratings("run")
    pos_s = {(s, g): p for s, g, p in pl.read_parquet(FEAT / "position_lookup.parquet").filter(pl.col("season") <= 2021).iter_rows()}
    sched = pl.read_parquet(Path(os.environ.get("G2_SCHEDULES", "/tmp/gamesim_cache/schedules.parquet"))).filter(
        pl.col("game_type") == "REG", pl.col("season").is_between(2016, 2021), pl.col("result").is_not_null()).with_columns(
        pl.col("home_team").replace(FRANCHISE), pl.col("away_team").replace(FRANCHISE))
    form = form_margin(sched)
    snaps = {}
    for s in SEASONS:
        sn = pl.read_parquet(ROOT / f"data/gamesim_v2/snapshots/pregame_players_{s}.parquet")
        for (gid, team), x in sn.partition_by("game_id", "team", as_dict=True).items():
            snaps[(gid, team)] = list(zip(x["uid"], x["pos_grp"], x["expected_share"]))
    # actual on-field shares (upper bound)
    db = pl.read_parquet(FEAT / "dropbacks.parquet").filter(pl.col("has_part"), pl.col("season").is_in(SEASONS))
    ru = pl.read_parquet(FEAT / "runs.parquet").filter(pl.col("has_part"), pl.col("season").is_in(SEASONS))
    def actual(tab):
        out = {}
        for (gid, team), x in tab.partition_by("game_id", "posteam", as_dict=True).items():
            n = x.height; co, cd = {}, {}
            for op, dp in zip(x["offense_players"], x["defense_players"]):
                for p in (op or "").split(";"):
                    if p: co[p] = co.get(p, 0) + 1
                for p in (dp or "").split(";"):
                    if p: cd[p] = cd.get(p, 0) + 1
            defteam = x["defteam"][0]
            out[(gid, team, "O")] = {p: c / n for p, c in co.items()}
            out[(gid, defteam, "D")] = {p: c / n for p, c in cd.items()}
        return out
    ACT = {"pass": actual(db), "run": actual(ru)}
    rows, slot_rows, excl = [], [], {"no_snapshot": 0, "no_ratings": 0}
    for r in sched.filter(pl.col("season").is_in(SEASONS)).iter_rows(named=True):
        s, w, gid, H, A_ = r["season"], r["week"], r["game_id"], r["home_team"], r["away_team"]
        if (gid, H) not in snaps or (gid, A_) not in snaps:
            excl["no_snapshot"] += 1; continue
        if (s, w) not in RP or (s, w) not in RR:
            excl["no_ratings"] += 1; continue
        val = {}
        for team in (H, A_):
            pl_ = snaps[(gid, team)]
            for kind, tab in (("pass", RP[(s, w)]), ("run", RR[(s, w)])):
                for side in ("O", "D"):
                    v, un, nopos, sl = team_shift(pl_, tab, side, pos_s, s)
                    val[(team, kind, side)] = v
                    val[(team, kind, side, "unrated")] = un; val[(team, kind, side, "nopos")] = nopos
                    slot_rows += [(s, kind, side, wt, se) for wt, se in sl]
                    act = ACT[kind].get((gid, team, side), {})
                    va = 0.0
                    for p, sh in act.items():
                        g = pos_s.get((s, p))
                        kk = f"{side}_{g}:{p}"
                        if kk in tab: va += sh * tab[kk][0]
                    val[(team, kind, side, "act")] = va
        def S(suffix=None, kinds=("pass", "run")):
            g = (lambda t, k, sd: val[(t, k, sd)]) if suffix is None else (lambda t, k, sd: val[(t, k, sd, suffix)])
            n = {"pass": n_pass, "run": n_run}
            return sum(n[k] * (g(H, k, "O") + g(A_, k, "D") - g(A_, k, "O") - g(H, k, "D")) for k in kinds)
        rows.append({"game_id": gid, "season": s, "week": w, "M": float(r["result"]), "C": float(r["spread_line"]), "F": form[gid],
                     "S": S(), "S_pass": S(kinds=("pass",)), "S_run": S(kinds=("run",)), "S_act": S("act"),
                     "nopos_weight": sum(val[(t, "pass", sd, "nopos")] for t in (H, A_) for sd in ("O", "D"))})
    T = pl.DataFrame(rows)
    T.write_parquet(FEAT / f"full_game_margin_rows{SUFFIX}.parquet")
    if os.environ.get("G2_DRYRUN"):  # sanity check of the shift before any margin is used: pregame quantities only
        print({"n_games": T.height, "excluded": excl, "n_pass": n_pass, "n_run": n_run, "S_sd": T["S"].std(), "S_mean": T["S"].mean(),
               "S_pass_sd": T["S_pass"].std(), "S_run_sd": T["S_run"].std(), "corr_S_close": float(np.corrcoef(T["S"], T["C"])[0, 1]),
               "corr_S_form": float(np.corrcoef(T["S"], T["F"])[0, 1]), "corr_S_act": float(np.corrcoef(T["S"], T["S_act"])[0, 1]),
               "nopos_weight_mean": T["nopos_weight"].mean()})
        return
    M, C, F_ = T["M"].to_numpy(), T["C"].to_numpy(), T["F"].to_numpy()
    blocks = np.array([f"{s}-{w}" for s, w in zip(T["season"], T["week"])]); games = T["game_id"].to_numpy()
    rng = np.random.default_rng(SEED)
    z = lambda x: x / x.std()
    one = np.ones(len(M))
    res = {"ridge": RIDGE, "n_games": int(T.height), "excluded": excl, "n_pass": n_pass, "n_run": n_run,
           "S_sd_points": float(T["S"].std()), "S_pass_sd": float(T["S_pass"].std()), "S_run_sd": float(T["S_run"].std()), "S_act_sd": float(T["S_act"].std()),
           "corr_S_with_close": float(np.corrcoef(T["S"], C)[0, 1]), "corr_S_with_form": float(np.corrcoef(T["S"], F_)[0, 1])}
    R_ = M - C
    X1 = np.column_stack([one, z(T["S"].to_numpy())])
    b = ols(X1, R_)[-1]
    p1 = {"coef_points_per_sd": float(b), "ci95_game": boot_coef(X1, R_, games, rng), "ci95_week": boot_coef(X1, R_, blocks, rng)}
    dv = lowo(one[:, None], X1, R_, blocks)
    p1["lowo_mse_change"] = float(dv.mean()); p1["lowo_mse_change_ci95_week"] = boot_mean_by_block(dv, blocks, rng)
    p1["pass"] = bool(b >= 0.5 and p1["ci95_game"][0] > 0 and p1["ci95_week"][0] > 0 and p1["lowo_mse_change"] < 0)
    res["primary_vs_close"] = p1
    sec = {}
    Xr = np.column_stack([one, T["S"].to_numpy()]); sec["raw_coef_on_S_vs_close"] = {"coef": float(ols(Xr, R_)[-1]), "ci95_game": boot_coef(Xr, R_, games, rng, 2000)}
    Xf0 = np.column_stack([one, F_]); Xf1 = np.column_stack([one, F_, z(T["S"].to_numpy())])
    dvf = lowo(Xf0, Xf1, M, blocks)
    sec["vs_team_form"] = {"coef_points_per_sd": float(ols(Xf1, M)[-1]), "ci95_game": boot_coef(Xf1, M, games, rng, 2000),
                           "form_coef": float(ols(Xf1, M)[1]), "lowo_mse_change": float(dvf.mean()), "lowo_ci95_week": boot_mean_by_block(dvf, blocks, rng, 2000)}
    for nm in ("S_pass", "S_run", "S_act"):
        Xc = np.column_stack([one, z(T[nm].to_numpy())])
        dvc = lowo(one[:, None], Xc, R_, blocks)
        sec[f"{nm}_vs_close"] = {"coef_points_per_sd": float(ols(Xc, R_)[-1]), "ci95_game": boot_coef(Xc, R_, games, rng, 2000),
                                 "lowo_mse_change": float(dvc.mean()), "lowo_ci95_week": boot_mean_by_block(dvc, blocks, rng, 2000)}
    for s in SEASONS:
        m = T["season"].to_numpy() == s
        Xs = np.column_stack([np.ones(m.sum()), z(T["S"].to_numpy()[m])])
        sec[f"season_{s}"] = {"n": int(m.sum()), "coef_points_per_sd": float(ols(Xs, R_[m])[-1]), "ci95_game": boot_coef(Xs, R_[m], games[m], rng, 2000)}
    sec["mse_close_only"] = float(((M - C - (M - C).mean()) ** 2).mean())
    res["secondary"] = sec
    SL = pl.DataFrame(slot_rows, schema=["season", "kind", "side", "weight", "se"], orient="row")
    ev = {}
    for s in SEASONS:
        x = SL.filter(pl.col("season") == s)
        tot = float(x["weight"].sum())
        ev[str(s)] = {"weight_share_unrated": float(x.filter(pl.col("se").is_null())["weight"].sum() / tot),
                      "se_quantiles_rated_slots": [float(x.filter(pl.col("se").is_not_null())["se"].quantile(q)) for q in (0.1, 0.5, 0.9)],
                      "players_rated_pass": int(len({k for wk, t in RP.items() if wk[0] == s for k in t})),
                      "players_rated_run": int(len({k for wk, t in RR.items() if wk[0] == s for k in t}))}
    res["evidence"] = ev
    res["nopos_weight_mean_per_game"] = float(T["nopos_weight"].mean())
    (MAN / f"full_game_margin_test{SUFFIX}.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
