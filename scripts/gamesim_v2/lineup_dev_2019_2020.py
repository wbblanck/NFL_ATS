"""Gamesim v2: development diagnostics for the pregame lineup signal on 2019-2020 (docs/gamesim_v2/PREREGISTRATION_lineup_dev_2019_2020.md).
Developmental, not confirmatory. Never loads seasons after 2020. Writes data/gamesim_v2/manifests/lineup_dev_2019_2020.json.
Usage: python scripts/gamesim_v2/lineup_dev_2019_2020.py"""
from __future__ import annotations

import itertools
import json
import math
from pathlib import Path

import numpy as np
import polars as pl

from engine.gamesim_v2.plays import passing as PS

ROOT = Path(__file__).resolve().parents[2]
FEAT, MAN = ROOT / "data/gamesim_v2/features", ROOT / "data/gamesim_v2/manifests"
LAST, SEASONS, SEED = 2020, (2019, 2020), 7
THIN = {"pressure": 300, "completion": 150}
OUTC = {"epa": "n_db", "press": "n_db", "comp": "n_att"}


def load():
    d = pl.read_parquet(FEAT / "dropbacks.parquet").filter(pl.col("has_part"), pl.col("season").is_between(2018, LAST))
    d = d.with_columns((pl.col("was_pressure").fill_null(False) | pl.col("sack")).cast(pl.Float64).alias("press"))
    att = d.filter(pl.col("attempt"), ~pl.col("sack"), ~pl.col("scramble"))
    g = d.group_by("game_id", "game_date", "season", "week", "posteam", "defteam").agg(
        pl.col("epa").mean().alias("epa"), pl.col("press").mean().alias("press"), pl.len().alias("n_db"))
    a = att.group_by("game_id", "posteam").agg(pl.col("complete").cast(pl.Float64).mean().alias("comp"), pl.len().alias("n_att"))
    return d, g.join(a, on=["game_id", "posteam"], how="left").sort("game_date", "game_id")


def form(g, o, hl, k):
    rows = g.select("game_date", "posteam", "defteam", o).to_dicts()
    off, dfn, allv = {}, {}, []
    fo, fd = np.zeros(len(rows)), np.zeros(len(rows))
    by_date = {}
    for j, r in enumerate(rows):
        by_date.setdefault(r["game_date"], []).append((j, r))
    for dt in sorted(by_date):
        mu = float(np.mean(allv)) if allv else 0.0

        def est(h):
            n = len(h)
            if not n:
                return mu
            w = 0.5 ** ((n - 1 - np.arange(n)) / hl)
            return float((w @ np.array(h) + k * mu) / (w.sum() + k))
        for j, r in by_date[dt]:
            fo[j], fd[j] = est(off.get(r["posteam"], [])) - mu, est(dfn.get(r["defteam"], [])) - mu
        for j, r in by_date[dt]:
            v = r[o]
            if v is not None and v == v:
                off.setdefault(r["posteam"], []).append(v)
                dfn.setdefault(r["defteam"], []).append(v)
                allv.append(v)
    return fo, fd


def wls(X, y, w):
    s = np.sqrt(w)
    return np.linalg.lstsq(X * s[:, None], y * s, rcond=None)[0]


def cluster_se(X, y, w, b, clusters_list):
    """Two-way cluster-robust (Cameron-Gelbach-Miller): V = V_a + V_b - V_ab, no small-sample factor."""
    e = y - X @ b
    bread = np.linalg.inv(X.T @ (X * w[:, None]))
    sc = X * (w * e)[:, None]

    def meat(cl):
        M = np.zeros((X.shape[1],) * 2)
        for u in np.unique(cl):
            s = sc[cl == u].sum(0)
            M += np.outer(s, s)
        return M
    a, b_ = clusters_list
    ab = np.array([f"{x}|{y_}" for x, y_ in zip(a, b_)])
    V = bread @ (meat(a) + meat(b_) - meat(ab)) @ bread
    return np.sqrt(np.maximum(np.diag(V), 1e-18))


def loo_week_mse(X, y, w, blocks):
    err = np.zeros(len(y))
    for bk in np.unique(blocks):
        te, tr = blocks == bk, blocks != bk
        err[te] = (y[te] - X[te] @ wls(X[tr], y[tr], w[tr])) ** 2
    return err


def components(g, d, pos):
    snap = {s: pl.read_parquet(ROOT / f"data/gamesim_v2/snapshots/pregame_players_{s}.parquet").filter(pl.col("p_active") >= 0.5).partition_by("game_id", "team", as_dict=True) for s in SEASONS}
    ab = {}
    for k in ("pressure", "completion"):
        t = pl.read_parquet(FEAT / f"abilities_{k}.parquet").filter(pl.col("season").is_in(SEASONS) & pl.col("key").str.contains(":"))
        for s, w, key, b, se, nr in zip(t["season"], t["week"], t["key"], t["beta"], t["se"], t["n_raw"]):
            ab.setdefault((k, s, w), {})[key] = (b, se, nr)
    pos_d = d.select("game_id", "posteam", "defteam", "qb", "offense_players", "defense_players", "season").partition_by("game_id", "posteam", as_dict=True)
    out, slots = [], []
    for r in g.filter(pl.col("season").is_in(SEASONS)).iter_rows(named=True):
        s, w, gid = r["season"], r["week"], r["game_id"]
        so, sd = snap[s].get((gid, r["posteam"])), snap[s].get((gid, r["defteam"]))
        if so is None or sd is None:
            continue
        Pt, Ct = ab.get(("pressure", s, w), {}), ab.get(("completion", s, w), {})
        top = lambda x, grp, col, n: x.filter(pl.col("pos_grp") == grp).sort(col, descending=True).head(n)["uid"].to_list()
        L = {"ol": top(so, "OL", "off_share_active", 5), "dl": top(sd, "DL", "def_share_active", 4), "lbp": top(sd, "LB", "def_share_active", 3),
             "qb": top(so, "QB", "off_share_active", 1), "db": top(sd, "DB", "def_share_active", 4), "lbc": top(sd, "LB", "def_share_active", 3)}
        ts = PS.target_shares(d.filter(pl.col("game_date") < r["game_date"]), r["posteam"], r["game_date"], 8)
        act = set(so.filter(pl.col("pos_grp").is_in(["WR", "TE", "RB"]))["uid"].to_list())
        sh = {u: x for u, x in ts.items() if u in act}
        tot = sum(sh.values())
        rw = {u: x / tot for u, x in sh.items()} if tot else {}
        def val(tab, key, thr_kind, filt):
            b, se, nr = tab.get(key, (0.0, 0.0, 0))
            known = key in tab
            ev = known and nr >= THIN[thr_kind]
            return (b if (not filt or ev) else 0.0), se, known, ev
        rec = {"game_id": gid, "season": s, "week": w, "posteam": r["posteam"], "defteam": r["defteam"], "n_db": r["n_db"], "n_att": r["n_att"],
               "epa": r["epa"], "press": r["press"], "comp": r["comp"]}
        sl = []
        for filt in (False, True):
            tag = "_ev" if filt else ""
            comp = {}
            for name, kind, tab, pref, ids, sign in (("ol", "pressure", Pt, "OL:", L["ol"], -1), ("rushdl", "pressure", Pt, "DL:", L["dl"], -1), ("rushlb", "pressure", Pt, "LB:", L["lbp"], -1),
                                                      ("qb", "completion", Ct, "QB:", L["qb"], 1), ("db", "completion", Ct, "DB:", L["db"], 1), ("lbc", "completion", Ct, "LB:", L["lbc"], 1)):
                v, var = 0.0, 0.0
                for u in ids:
                    b, se, known, ev = val(tab, pref + u, kind, filt)
                    v += sign * b
                    var += se * se if (b != 0.0 or not filt) and known else 0.0
                    if not filt:
                        sl.append((name, known, ev, se if known else float("nan"), tab.get(pref + u, (0, 0, 0))[2]))
                comp[name] = (v, var)
            rv, rvar = 0.0, 0.0
            for u, wt in rw.items():
                b, se, known, ev = val(Ct, "R:" + u, "completion", filt)
                rv += wt * b
                rvar += (wt * se) ** 2 if known else 0.0
                if not filt:
                    sl.append(("recv", known, ev, se if known else float("nan"), Ct.get("R:" + u, (0, 0, 0))[2]))
            rec["ol" + tag], rec["rush" + tag] = comp["ol"][0], comp["rushdl"][0] + comp["rushlb"][0]
            rec["qb" + tag], rec["recv" + tag], rec["cov" + tag] = comp["qb"][0], rv, comp["db"][0] + comp["lbc"][0]
            if not filt:
                rec["sd_pres"] = math.sqrt(comp["ol"][1] + comp["rushdl"][1] + comp["rushlb"][1]) or float("nan")
                rec["sd_comp"] = math.sqrt(comp["qb"][1] + rvar + comp["db"][1] + comp["lbc"][1]) or float("nan")
        rec["ev_share"] = float(np.mean([x[2] for x in sl])) if sl else float("nan")
        # actual lineup (upper bound): share of the game's dropbacks each player was on the field
        pg = pos_d.get((gid, r["posteam"]))
        if pg is not None and pg.height:
            n = pg.height
            cnt_o, cnt_d, qbc = {}, {}, {}
            for op, dp, q in zip(pg["offense_players"], pg["defense_players"], pg["qb"]):
                for p in (op or "").split(";"):
                    if p:
                        cnt_o[p] = cnt_o.get(p, 0) + 1
                for p in (dp or "").split(";"):
                    if p:
                        cnt_d[p] = cnt_d.get(p, 0) + 1
                if q:
                    qbc[q] = qbc.get(q, 0) + 1
            gp = lambda p: pos.get((s, p))
            rec["ol_act"] = -sum(c / n * Pt.get("OL:" + p, (0,))[0] for p, c in cnt_o.items() if gp(p) == "OL")
            rec["rush_act"] = -sum(c / n * Pt.get(f"{gp(p)}:{p}", (0,))[0] for p, c in cnt_d.items() if gp(p) in ("DL", "LB"))
            rec["qb_act"] = sum(c / n * Ct.get("QB:" + p, (0,))[0] for p, c in qbc.items())
            rec["cov_act"] = sum(c / n * Ct.get(f"{gp(p)}:{p}", (0,))[0] for p, c in cnt_d.items() if gp(p) in ("DB", "LB"))
            ra = {u: x for u, x in ts.items() if cnt_o.get(u, 0) > 0}
            tt = sum(ra.values())
            rec["recv_act"] = sum(x / tt * Ct.get("R:" + u, (0,))[0] for u, x in ra.items()) if tt else 0.0
        out.append(rec)
        slots += [(s, *x) for x in sl]
    return pl.DataFrame(out), pl.DataFrame(slots, schema=["season", "group", "known", "evidenced", "se", "n_raw"], orient="row")


def zs(x):
    return (x - x.mean()) / x.std()


def main():
    d, g = load()
    pos = {(s, p_): grp for s, p_, grp in pl.read_parquet(FEAT / "position_lookup.parquet").filter(pl.col("season") <= LAST).iter_rows()}
    T, slots = components(g, d, pos)
    T = T.filter(pl.col("epa").is_not_null() & pl.col("comp").is_not_null())
    res = {"note": "developmental; 2019 cleaner than 2020 (2020 tuned the player models)", "team_games": {str(s): int(T.filter(pl.col("season") == s).height) for s in SEASONS}}
    # ---- form calibration on 2019 form-only
    idx_all = g.with_row_index("i")
    keys = T.select("game_id", "posteam").join(idx_all.select("game_id", "posteam", "i"), on=["game_id", "posteam"])
    ii = keys["i"].to_numpy()
    s_arr, wk = T["season"].to_numpy(), T["week"].to_numpy()
    chosen, forms = {}, {}
    res["form_grid_2019"] = {}
    for o, wc in OUTC.items():
        y, w = T[o].to_numpy(), T[wc].to_numpy().astype(float)
        m19 = s_arr == 2019
        best = None
        grid = {}
        for hl, k in itertools.product((3, 6, 12, 24), (2, 4, 8)):
            fo, fd = form(g, o, hl, k)
            X = np.column_stack([np.ones(len(ii)), fo[ii], fd[ii]])
            e = loo_week_mse(X[m19], y[m19], w[m19], wk[m19])
            mse = float((w[m19] * e).sum() / w[m19].sum())
            grid[f"{hl}_{k}"] = mse
            if best is None or mse < best[0]:
                best = (mse, hl, k)
        chosen[o] = (best[1], best[2])
        res["form_grid_2019"][o] = {"mse": grid, "chosen_half_life": best[1], "chosen_k": best[2]}
        forms[o] = {"cal": form(g, o, *chosen[o]), "apriori": form(g, o, 6, 4)}
    # ---- predictors
    sd_p, sd_c = T["sd_pres"].to_numpy(), T["sd_comp"].to_numpy()
    comp_shift = T["qb"].to_numpy() + T["recv"].to_numpy() + T["cov"].to_numpy()
    pres_shift = T["ol"].to_numpy() + T["rush"].to_numpy()
    comp_ev = T["qb_ev"].to_numpy() + T["recv_ev"].to_numpy() + T["cov_ev"].to_numpy()
    pres_ev = T["ol_ev"].to_numpy() + T["rush_ev"].to_numpy()
    S = zs(comp_shift) + zs(pres_shift)
    ok = ~(np.isnan(sd_p) | np.isnan(sd_c))
    St = np.where(ok, zs(np.nan_to_num(comp_shift / sd_c, nan=0.0)) + zs(np.nan_to_num(pres_shift / sd_p, nan=0.0)), S)
    Sev = zs(comp_ev) + zs(pres_ev)
    Sact = zs(T["qb_act"].to_numpy() + T["recv_act"].to_numpy() + T["cov_act"].to_numpy()) + zs(T["ol_act"].to_numpy() + T["rush_act"].to_numpy())
    # share of evidenced slots per team-game (for D5 split) from the slot table is season-level; use component availability proxy instead:
    preds = [  # (id, label, x, outcomes)
        ("D1", "S combined", S, ["epa"]), ("D2", "completion shift", comp_shift, ["epa", "comp"]), ("D3", "pressure shift", pres_shift, ["epa", "press"]),
        ("D4", "S uncertainty-weighted", St, ["epa"]), ("D5", "S evidenced-only", Sev, ["epa"]),
        ("D6", "OL only", T["ol"].to_numpy(), ["press", "epa"]), ("D7", "QB only", T["qb"].to_numpy(), ["comp", "epa"]),
        ("D8", "receivers only", T["recv"].to_numpy(), ["comp", "epa"]), ("D9a", "opp rush only", T["rush"].to_numpy(), ["press", "epa"]),
        ("D9b", "opp coverage only", T["cov"].to_numpy(), ["comp", "epa"]), ("D10", "S actual lineup (upper bound)", Sact, ["epa"])]
    rng = np.random.default_rng(SEED)
    gid = T["game_id"].to_numpy()
    ug = np.unique(gid)
    cl = {u: np.where(gid == u)[0] for u in ug}
    boots = [np.concatenate([cl[u] for u in rng.choice(ug, len(ug))]) for _ in range(1000)]
    team, blocks = T["posteam"].to_numpy(), np.array([f"{s}-{w}" for s, w in zip(s_arr, wk)])
    rows = []
    for pid, label, x, outs in preds:
        for o in outs:
            y, w = T[o].to_numpy(), T[OUTC[o]].to_numpy().astype(float)
            for fname in ("cal", "apriori"):
                fo, fd = forms[o][fname][0][ii], forms[o][fname][1][ii]
                for scope, m in (("2019", s_arr == 2019), ("2020", s_arr == 2020), ("pooled", np.ones(len(y), bool))):
                    if fname == "apriori" and scope != "pooled":
                        continue
                    xs = (x[m] - x[m].mean()) / x[m].std()
                    X0 = np.column_stack([np.ones(m.sum()), fo[m], fd[m]])
                    X1 = np.column_stack([X0, xs])
                    b = wls(X1, y[m], w[m])
                    se2 = cluster_se(X1, y[m], w[m], b, [team[m], blocks[m]])[-1]
                    z = b[-1] / se2
                    p = math.erfc(abs(z) / math.sqrt(2))
                    e0, e1 = loo_week_mse(X0, y[m], w[m], blocks[m]), loo_week_mse(X1, y[m], w[m], blocks[m])
                    dw = w[m] * (e1 - e0)
                    if scope == "pooled":
                        mi = np.where(m)[0]
                        mp = {u: k for k, u in enumerate(mi)}
                        dbs = [dw[ii2].sum() / w[m][ii2].sum() for ii2 in (np.array([mp[t] for t in bt if t in mp]) for bt in boots[:300])]
                        ci = [float(v) for v in np.percentile(dbs, [2.5, 97.5])]
                    else:
                        ci = None
                    resid = y[m] - X0 @ wls(X0, y[m], w[m])
                    rows.append({"id": pid, "label": label, "outcome": o, "form": fname, "scope": scope, "n": int(m.sum()),
                                 "coef_per_sd": float(b[-1]), "se_two_way": float(se2), "z": float(z), "p": float(p),
                                 "cv_mse_change": float(dw.sum() / w[m].sum()), "cv_mse_change_ci95_boot": ci,
                                 "corr_with_form_residual": float(np.corrcoef(xs, resid)[0, 1])})
    # Holm over pooled, calibrated-form tests
    fam = [r for r in rows if r["scope"] == "pooled" and r["form"] == "cal"]
    order = sorted(range(len(fam)), key=lambda i: fam[i]["p"])
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (len(fam) - rank) * fam[i]["p"]))
        fam[i]["p_holm"] = run
    res["tests"] = rows
    res["holm_family_size"] = len(fam)
    # D5 split: S coefficient in team-games with above vs below median share of evidenced lineup slots (EPA, calibrated form, per scope pooled)
    evs = T["ev_share"].to_numpy()
    med = float(np.median(evs))
    res["D5_split"] = {"median_evidenced_share": med}
    y, w = T["epa"].to_numpy(), T["n_db"].to_numpy().astype(float)
    fo, fd = forms["epa"]["cal"][0][ii], forms["epa"]["cal"][1][ii]
    for name, m in (("above_median", evs >= med), ("below_median", evs < med)):
        xs = (S[m] - S[m].mean()) / S[m].std()
        X1 = np.column_stack([np.ones(m.sum()), fo[m], fd[m], xs])
        b = wls(X1, y[m], w[m])
        se2 = cluster_se(X1, y[m], w[m], b, [team[m], blocks[m]])[-1]
        res["D5_split"][name] = {"n": int(m.sum()), "coef_per_sd": float(b[-1]), "se_two_way": float(se2), "z": float(b[-1] / se2)}
    # ---- reporting block
    sl = slots
    rep = {}
    for grp in sl["group"].unique().to_list():
        x = sl.filter(pl.col("group") == grp)
        rep[grp] = {"slots": x.height, "unseen_share": float((~x["known"]).mean()), "thin_share": float((x["known"] & ~x["evidenced"]).mean()),
                    "evidenced_share": float(x["evidenced"].mean()), "se_quantiles_known": [float(v) for v in x.filter(pl.col("known"))["se"].quantile(0.5).to_frame().row(0)] if False else
                    [float(x.filter(pl.col("known"))["se"].quantile(q)) for q in (0.1, 0.5, 0.9)],
                    "n_raw_quantiles_known": [float(x.filter(pl.col("known"))["n_raw"].quantile(q)) for q in (0.1, 0.5, 0.9)]}
    res["slots_by_group"] = rep
    res["slot_totals"] = {"slots": sl.height, "unseen_share": float((~sl["known"]).mean()), "evidenced_share": float(sl["evidenced"].mean())}
    res["players_with_effect_in_lineups_by_season"] = {}
    for s in SEASONS:
        u = set()
        for k in ("pressure", "completion"):
            t = pl.read_parquet(FEAT / f"abilities_{k}.parquet").filter((pl.col("season") == s) & pl.col("key").str.contains(":") & (pl.col("n_raw") >= THIN[k]))
            u |= set(t["key"].to_list())
        res["players_with_effect_in_lineups_by_season"][str(s)] = len(u)
    var_s = float(np.nanvar(comp_shift / sd_c)) if True else 0
    res["reliability"] = {"completion_shift": float(np.var(comp_shift) / (np.var(comp_shift) + np.nanmean(sd_c ** 2))),
                          "pressure_shift": float(np.var(pres_shift) / (np.var(pres_shift) + np.nanmean(sd_p ** 2))),
                          "sd_completion_shift": float(np.std(comp_shift)), "mean_se_completion_shift": float(np.nanmean(sd_c)),
                          "sd_pressure_shift": float(np.std(pres_shift)), "mean_se_pressure_shift": float(np.nanmean(sd_p))}
    res["corr_components"] = {k: float(np.corrcoef(T[k].to_numpy(), T[k + "_act"].to_numpy())[0, 1]) for k in ("ol", "rush", "qb", "cov", "recv")}
    (MAN / "lineup_dev_2019_2020.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps({k: res[k] for k in ("team_games", "slot_totals", "players_with_effect_in_lineups_by_season", "reliability", "corr_components")}, indent=1))
    for r in rows:
        if r["scope"] == "pooled" and r["form"] == "cal":
            print(r["id"], r["outcome"], f'coef/sd {r["coef_per_sd"]:+.4f} z {r["z"]:+.2f} p {r["p"]:.3f} holm {r.get("p_holm", float("nan")):.2f} cv {r["cv_mse_change"]:+.6f} ci {r["cv_mse_change_ci95_boot"]}')


if __name__ == "__main__":
    main()
