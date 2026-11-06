"""Vectorized snap-by-snap game engine (nfl-betting-model docs/gamesim_preregistration.md).

Simulates many games at once: every array has one entry per (game, simulation). Team factors arrive as arrays
indexed [element, side] with side 0 = home, 1 = away. Timeouts are not tracked one by one; their average effect on
the clock is inside the league seconds-per-snap table (disclosed in the report).
"""
from __future__ import annotations

import numpy as np

from . import league as L

FACTORS = ("sack", "scr", "int", "comp", "ypc", "ypr", "proe")


def _logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _sig(x):
    return 1 / (1 + np.exp(-x))


class Tables:
    """League tables as numpy arrays, plus per-season kickoff start positions and extra-point rates."""

    def __init__(self, T: dict):
        self.pass_prob = np.array(T["pass_prob"])
        self.pass_yl = np.array(T["pass_yl_shift"])
        self.db = np.array(T["db_outcome"])
        self.comp_y = [np.array(x, float) for x in T["comp_yards"]]
        self.scr_y = [np.array(x, float) for x in T["scr_yards"]]
        self.run_y = [np.array(x, float) for x in T["run_yards"]]
        self.sack_y = np.array(T["sack_yards"], float)
        self.int_net = np.array(T["int_net"], float)
        self.int_td, self.fum = T["int_td"], (T["fumble_comp"], T["fumble_sack"], T["fumble_run"])
        self.fum_td, self.kick_td = T["fumble_td"], T["kick_td"]
        self.pen = (T["pen_rate"], T["pen_def_share"], T["pen_def_first"])
        self.pen_def_y, self.pen_off_y = np.array(T["pen_def_yards"], float), np.array(T["pen_off_yards"], float)
        self.fourth = np.array(T["fourth"])
        self.fg = np.array(T["fg_make"])
        self.punt = [np.array(x, float) for x in T["punt_recv"]]
        self.punt_td = T["punt_td"]
        self.two_go, self.two_ok = np.array(T["two_go"]), T["two_success"]
        self.secs = np.array(T["secs"])


def _draw(rng, pools, bucket):
    """One value per element from pools[bucket[i]]."""
    out = np.empty(len(bucket))
    for b in np.unique(bucket):
        m = bucket == b
        pool = pools[b]
        out[m] = pool[rng.integers(0, len(pool), m.sum())]
    return out


def simulate(tb: Tables, off: dict, dfn: dict, kick: tuple, xp: np.ndarray, season: np.ndarray, hfa: float,
             seed: int = 0, clock_mult: float = 1.0, max_steps: int = 600, stats: dict | None = None,
             counts: dict | None = None, roster: dict | None = None,
             cover: dict | None = None):
    """off[f] / dfn[f]: arrays (N, 2) of log-odds shifts (sack, scr, int, comp, proe) or log yard scales (ypc, ypr)
    for each element's home (0) and away (1) team. kick: (pools, ids): kickoff start pools (yardline_100 of the
    receiving team) and each element's pool index; xp: (N,) extra-point rate. Returns home and away points, arrays (N,).

    roster (optional, docs/gamesim_players_preregistration.md): per element and side,
      tcum (N, 2, K) cumulative target shares, cshift (N, 2, K) catch log-odds shift, yscale (N, 2, K) catch-yard scale,
      rcum (N, 2, Kc) cumulative designed-run shares (slot 0 = the passer), rscale (N, 2, Kc) run-yard scale.
    Every throw is credited to a receiver slot and every designed run to a rusher slot; scrambles and kneels go to
    slot 0. Player stats are returned in roster['out']. With `cover`, roster may also carry tcum_m / tcum_z (cumulative
    shares on man / zone dropbacks) and ymul (N, 2, K, 2) yard multipliers by coverage.

    cover (optional, docs/gamesim_coverage_preregistration.md): m (N, 2) man rate of each side's defense, and
      sp (N, 2, 2, 4) each side's offense deviations [coverage man/zone][comp, int, sack, ypc]. Each dropback draws
      man with the defense's rate and shifts the offense's pass factors by its split."""
    rng = np.random.default_rng(seed)
    N = len(xp)
    ar = np.arange(N)
    score = np.zeros((N, 2))
    sec = np.full(N, 3600.0)
    recv1 = rng.integers(0, 2, N)
    pos = recv1.copy()
    half2 = np.zeros(N, bool)
    ot = np.zeros(N, bool)
    ot_poss = np.zeros(N, int)
    done = np.zeros(N, bool)
    kpools, kid = [np.asarray(k, float) for k in kick[0]], np.asarray(kick[1])
    yl = _draw(rng, kpools, kid)
    down = np.ones(N, int)
    togo = np.full(N, 10.0)
    ot_len = np.where(season <= 2016, 900.0, 600.0)
    both_poss = season >= 2025

    ret_td = np.zeros(N, bool)
    npos = np.zeros(1)
    rz = np.zeros(N, bool)
    rzc = np.zeros(2)

    def kickoff(m, to):            # elements m: team `to` receives; a return TD is scored at the next step
        pos[m] = to[m] if isinstance(to, np.ndarray) else to
        yl[m] = _draw(rng, kpools, kid)[m]
        down[m] = 1
        togo[m] = 10.0
        ret_td[m] = rng.random(m.sum()) < tb.kick_td
        npos[0] += m.sum(); rz[m] = False

    def change(m, new_yl):         # possession changes on elements m, new offense at new_yl
        pos[m] = 1 - pos[m]
        yl[m] = np.clip(new_yl[m], 1, 99)
        down[m] = 1
        togo[m] = np.minimum(10.0, yl[m])
        ot_poss[m & ot] += 1
        npos[0] += m.sum(); rz[m] = False

    def check_ot(m_score, scorer):
        """After a score on elements m_score in overtime: decide whether the game ends."""
        m = m_score & ot & ~done
        lead = score[ar, scorer] > score[ar, 1 - scorer]
        first = ot_poss == 1
        end = m & ((~first & (score[:, 0] != score[:, 1]) & ~both_poss)
                   | (first & ~both_poss & tdflag)
                   | ((ot_poss == 2) & lead)
                   | ((ot_poss >= 3) & (score[:, 0] != score[:, 1])))
        done[end] = True

    def check_ot_change(m):
        """Possession just changed on m in overtime: second team's possession over with a lead decided -> end."""
        mm = m & ot & ~done & (ot_poss >= 3) & (score[:, 0] != score[:, 1])
        done[mm] = True

    c_att = np.zeros((N, 2), np.int16)
    c_car = np.zeros((N, 2), np.int16)
    q_sc = np.zeros((N, 4, 2), np.int16)
    tdflag = np.zeros(N, bool)
    if roster is not None:
        K, Kc = roster["tcum"].shape[2], roster["rcum"].shape[2]
        P_ = {k: np.zeros((N, 2, K), np.int16) for k in ("tgt", "rec", "ryd")}
        P_.update({k: np.zeros((N, 2, Kc), np.int16) for k in ("car", "uyd")})
        P_.update({k: np.zeros((N, 2), np.int16) for k in ("cmp", "pyd")})
    st_ = {k: 0.0 for k in ('snap', 'd3', 'c3', 'yds', 'td', 'fg', 'fga', 'punt', 'int', 'fum', 'sack', 'comp', 'inc', 'run', 'scr', 'pen', 'tod')}
    for _ in range(max_steps):
        act = ~done
        if not act.any():
            break
        # ---- period transitions
        h2 = act & ~ot & ~half2 & (sec <= 1800)
        if h2.any():
            half2[h2] = True
            kickoff(h2, 1 - recv1)
        endreg = act & ~ot & (sec <= 0)
        if endreg.any():
            q_sc[endreg, 3] = score[endreg]
            fin = endreg & (score[:, 0] != score[:, 1])
            done[fin] = True
            st = endreg & ~fin
            ot[st] = True
            sec[st] = ot_len[st]
            ot_poss[st] = 1
            kickoff(st, rng.integers(0, 2, N))
        endot = act & ot & (sec <= 0)
        done[endot] = True
        act = ~done
        if not act.any():
            break
        p = pos
        sdiff = score[ar, p] - score[ar, 1 - p]
        qtr = np.where(ot, 5, np.clip(4 - ((sec - 1) // 900).astype(int), 1, 4))
        half_sec = np.where(sec > 1800, sec - 1800, sec)
        gsec = np.where(ot, np.minimum(sec, 300), sec)
        tm = L.b_time(gsec, half_sec, np.minimum(qtr, 4))
        tdflag[:] = False
        o = {f: off[f][ar, p] + dfn[f][ar, 1 - p] for f in FACTORS}
        home_off = p == 0
        yscale = np.where(home_off, np.exp(hfa), np.exp(-hfa))
        # ---- choose the play
        is4 = act & (down == 4)
        ch = np.zeros(N, int)            # 0 scrimmage, 1 punt, 2 field goal
        if is4.any():
            pr = tb.fourth[L.b_yl4(yl), L.b_togo(togo), L.b_sit4(sdiff, gsec, np.minimum(qtr, 4))]
            u = rng.random(N)
            ch = np.where(is4, np.where(u < pr[:, 0], 0, np.where(u < pr[:, 0] + pr[:, 1], 1, 2)), 0)
            ch = np.where(is4 & (yl > 60) & (ch == 2), 1, ch)       # no 78+ yard field goals
        # end of a half: kick a field goal on any down when in range and it matters
        last = act & (half_sec <= 20) & (yl <= 40) & (((qtr == 2) & ~ot) | ((qtr >= 4) & (sdiff >= -3) & (sdiff <= 0)))
        ch = np.where(last, 2, ch)
        # victory formation: leading in the last 2 minutes of the 4th quarter or overtime
        kneel = act & (qtr >= 4) & (gsec <= 120) & (sdiff > 0) & (down < 4) & ~last
        stopped = np.zeros(N, bool)
        scored_td = np.zeros(N, bool)
        rtd = act & ret_td
        ret_td[:] = False
        if rtd.any():
            scored_td |= rtd
            ch = np.where(rtd, -1, ch)
        if kneel.any():
            ch = np.where(kneel, -2, ch)
            yl[kneel] += 1
            togo[kneel] += 1
            down[kneel] += 1
            if roster is not None:
                P_["car"][ar[kneel], p[kneel], 0] += 1
                P_["uyd"][ar[kneel], p[kneel], 0] -= 1
        changed = np.zeros(N, bool)
        new_yl = yl.copy()
        # ---- field goals
        fgm = act & (ch == 2)
        if fgm.any():
            dist = yl + 18
            make = rng.random(N) < tb.fg[np.clip(np.searchsorted(L.FGD, dist), 0, len(tb.fg) - 1)]
            good = fgm & make
            score[ar[good], p[good]] += 3
            stopped |= fgm
            tdflag[:] = False
            check_ot(good, p)
            kickoff(good & ~done, 1 - p)
            changed |= good
            ot_poss[good & ot & ~done] += 1
            miss = fgm & ~make
            new_yl[miss] = np.minimum(80, 100 - (yl[miss] + 7))
            change(miss, new_yl)
            check_ot_change(miss)
            changed |= miss
        # ---- punts
        pm = act & (ch == 1)
        if pm.any():
            ptd = pm & (rng.random(N) < tb.punt_td)
            r = _draw(rng, tb.punt, np.searchsorted(L.PUNTYL, yl))
            normal = pm & ~ptd
            new_yl[normal] = r[normal]
            change(normal, new_yl)
            check_ot_change(normal)
            changed |= pm
            stopped |= pm
            if ptd.any():
                pos[ptd] = 1 - pos[ptd]
                ot_poss[ptd & ot] += 1
                scored_td |= ptd
        # ---- scrimmage snaps
        sm = act & (ch == 0)
        yards = np.zeros(N)
        turnover = np.zeros(N, bool)
        pen = sm & (rng.random(N) < tb.pen[0])
        if pen.any():
            dpen = pen & (rng.random(N) < tb.pen[1])
            opn = pen & ~dpen
            dy = _draw(rng, [tb.pen_def_y], np.zeros(N, int))
            dy = np.minimum(dy, np.ceil(yl / 2))
            auto = dpen & ((rng.random(N) < tb.pen[2]) | (dy >= togo))
            yl[dpen] -= dy[dpen]
            togo[dpen] -= dy[dpen]
            down[auto] = 1
            togo[auto] = np.minimum(10.0, yl[auto])
            oy = _draw(rng, [tb.pen_off_y], np.zeros(N, int))
            oy = np.minimum(oy, np.floor((100 - yl) / 2))
            yl[opn] += oy[opn]
            togo[opn] += oy[opn]
            stopped |= pen
        play = sm & ~pen
        down_pre, togo_pre = down.copy(), togo.copy()
        if play.any():
            dn = np.clip(down - 1, 0, 2)
            pp = tb.pass_prob[dn, L.b_togo(togo), L.b_sdiff(sdiff), tm]
            isp = play & (rng.random(N) < _sig(_logit(pp) + tb.pass_yl[dn, L.b_yard(yl)] + o["proe"]))
            run = play & ~isp
            yb = L.b_yard(yl)
            base = tb.db[yb]
            dv = np.zeros((N, 4))
            if cover is not None:
                man = rng.random(N) < cover["m"][ar, 1 - p]
                cz = np.where(man, 0, 1)
                dv = cover["sp"][ar, p, cz]
            ps = _sig(_logit(base[:, 0]) + o["sack"] + dv[:, 2])
            rest = 1 - base[:, 0]
            pscr = _sig(_logit(base[:, 1] / rest) + o["scr"])
            att = (base[:, 2] + base[:, 3] + base[:, 4])
            pint = _sig(_logit(base[:, 2] / att) + o["int"] + dv[:, 1])
            pcomp = _sig(_logit(base[:, 3] / (base[:, 3] + base[:, 4])) + o["comp"] + dv[:, 0])
            if roster is not None:
                tc = roster["tcum"][ar, p]
                if cover is not None and "tcum_m" in roster:
                    tc = np.where(man[:, None], roster["tcum_m"][ar, p], roster["tcum_z"][ar, p])
                ri = np.minimum((rng.random(N)[:, None] > tc).sum(1), K - 1)
                ci = np.minimum((rng.random(N)[:, None] > roster["rcum"][ar, p]).sum(1), Kc - 1)
                pcomp = _sig(_logit(pcomp) + roster["cshift"][ar, p, ri])
            u1, u2, u3, u4 = rng.random((4, N))
            sack = isp & (u1 < ps)
            scr = isp & ~sack & (u2 < pscr)
            thr = isp & ~sack & ~scr
            intc = thr & (u3 < pint)
            comp = thr & ~intc & (u4 < pcomp)
            inc = thr & ~intc & ~comp
            c_att[ar[thr], p[thr]] += 1
            rs = run | scr
            c_car[ar[rs], p[rs]] += 1
            pb_ = L.b_pool(yl)
            cy = _draw(rng, tb.comp_y, pb_)
            sy = _draw(rng, tb.scr_y, pb_)
            ry = _draw(rng, tb.run_y, pb_)
            ky = _draw(rng, [tb.sack_y], np.zeros(N, int))
            sc_c = np.exp(o["ypc"] + dv[:, 3]) * yscale
            sc_r = np.exp(o["ypr"]) * yscale
            sc_d = sc_r
            if roster is not None:
                sc_c = sc_c * roster["yscale"][ar, p, ri]
                if cover is not None and "ymul" in roster:
                    sc_c = sc_c * roster["ymul"][ar, p, ri, cz]
                sc_d = sc_r * roster["rscale"][ar, p, ci]
            coded = (comp & (cy == L.TD_CODE)) | (scr & (sy == L.TD_CODE)) | (run & (ry == L.TD_CODE))
            yards = np.where(comp, np.where(cy > 0, np.round(cy * sc_c), cy),
                     np.where(scr, np.where(sy > 0, np.round(sy * sc_r), sy),
                     np.where(run, np.where(ry > 0, np.round(ry * sc_d), ry),
                     np.where(sack, ky, 0.0))))
            yards = np.where(play & ~intc & ~inc, yards, 0.0)
            yards = np.where(coded, yl, np.where((pb_ < 20) & (yards >= yl) & ~sack, yl - 1, yards))
            if roster is not None:
                yi = yards.astype(np.int16)
                for m_, k_, slot in ((thr, "tgt", ri), (comp, "rec", ri)):
                    P_[k_][ar[m_], p[m_], slot[m_]] += 1
                P_["ryd"][ar[comp], p[comp], ri[comp]] += yi[comp]
                P_["cmp"][ar[comp], p[comp]] += 1
                P_["pyd"][ar[comp], p[comp]] += yi[comp]
                P_["car"][ar[run], p[run], ci[run]] += 1
                P_["uyd"][ar[run], p[run], ci[run]] += yi[run]
                P_["car"][ar[scr], p[scr], 0] += 1
                P_["uyd"][ar[scr], p[scr], 0] += yi[scr]
            # fumbles lost
            fum = (comp & (rng.random(N) < tb.fum[0])) | (sack & (rng.random(N) < tb.fum[1])) \
                | ((run | scr) & (rng.random(N) < tb.fum[2]))
            # interceptions
            if intc.any():
                pick6 = intc & (rng.random(N) < tb.int_td)
                net = _draw(rng, [tb.int_net], np.zeros(N, int))
                spot = yl - net
                ny = np.where(spot <= 0, 80.0, 100 - spot)
                normal = intc & ~pick6
                new_yl[normal] = ny[normal]
                change(normal, new_yl)
                check_ot_change(normal)
                if pick6.any():
                    pos[pick6] = 1 - pos[pick6]
                    ot_poss[pick6 & ot] += 1
                    scored_td |= pick6
                turnover |= intc
            td = play & ~intc & ~inc & (yards >= yl) & ~fum
            safety = play & ~intc & (yl - yards >= 100)
            # fumble: other team at the spot
            fm = fum & ~td & ~safety
            if fm.any():
                spot = np.clip(yl - yards, 1, 99)
                new_yl[fm] = 100 - spot[fm]
                change(fm, new_yl)
                check_ot_change(fm)
                turnover |= fm
                scored_td |= fm & ~done & (rng.random(N) < tb.fum_td)   # recovering team (now pos) returns it
            scored_td |= td
            if safety.any():
                score[ar[safety], 1 - p[safety]] += 2
                tdflag[:] = False
                check_ot(safety, 1 - p)
                # free kick: the team that conceded kicks; approximate with a kickoff to the scoring team
                kickoff(safety & ~done, 1 - p)
                ot_poss[safety & ot & ~done] += 1
            reg = play & ~intc & ~td & ~safety & ~fm
            yl[reg] -= yards[reg]
            first = reg & (yards >= togo)
            down[first] = 1
            togo[first] = np.minimum(10.0, yl[first])
            nf = reg & ~first
            down[nf] += 1
            togo[nf] -= yards[nf]
            tod = nf & (down > 4)
            if tod.any():
                new_yl[tod] = 100 - yl[tod]
                change(tod, new_yl)
                check_ot_change(tod)
                turnover |= tod
            stopped |= inc | td | turnover | safety
        newrz = act & ~rz & (yl <= 20)
        rzc[0] += newrz.sum(); rz |= newrz
        rzc[1] += (scored_td & rz).sum()
        # ---- touchdowns and tries (offense = pos at this point for scored_td elements)
        if scored_td.any():
            s_team = pos
            score[ar[scored_td], s_team[scored_td]] += 6
            after = score[ar, s_team] - score[ar, 1 - s_team]
            q4 = (qtr >= 4).astype(int)
            go2 = rng.random(N) < tb.two_go[np.clip(after.astype(int), -15, 15) + 15, q4]
            ok = np.where(go2, rng.random(N) < tb.two_ok, rng.random(N) < xp)
            pts = np.where(go2, 2.0, 1.0) * ok
            score[ar[scored_td], s_team[scored_td]] += pts[scored_td]
            tdflag[:] = scored_td
            check_ot(scored_td, s_team)
            nxt = scored_td & ~done
            kickoff(nxt, 1 - s_team)
            ot_poss[nxt & ot] += 1
            stopped |= scored_td
        # ---- clock
        if stats is not None:
            st_['d3'] += (play & (down_pre == 3)).sum() if play.any() else 0; st_['c3'] += (play & (down_pre == 3) & ((yards >= togo_pre) | td)).sum() if play.any() else 0; st_['yds'] += yards[play].sum() if play.any() else 0
            st_['snap'] += sm.sum(); st_['fga'] += fgm.sum(); st_['punt'] += pm.sum(); st_['td'] += scored_td.sum(); st_['pen'] += pen.sum()
            if fgm.any(): st_['fg'] += good.sum()
            if play.any():
                for k, v in (('int', intc), ('fum', fm), ('sack', sack), ('comp', comp), ('inc', inc), ('run', run), ('scr', scr), ('tod', nf & (down > 4))):
                    st_[k] += v.sum()
        sit = np.where((qtr == 2) & (half_sec <= 120), 3, np.where((qtr >= 4) & (gsec <= 300), np.where(sdiff < 0, 1, 2), 0))
        dt = tb.secs[stopped.astype(int), sit] * (0.75 + 0.5 * rng.random(N)) * clock_mult
        dt = np.where(kneel, 40.0, dt)
        new = sec - np.where(act, dt, 0)
        for bnd, qi in ((2700.0, 0), (1800.0, 1), (900.0, 2)):
            qm = ~ot & (sec > bnd) & (new <= bnd)
            q_sc[qm, qi] = score[qm]
        b1 = ~ot & (sec > 1800) & (new < 1800)
        new = np.where(b1, 1800.0, new)
        for w in (1920.0, 120.0):                 # two-minute warnings
            new = np.where(~ot & (sec > w) & (new < w), w, new)
        sec = np.maximum(new, 0.0)
    if roster is not None:
        roster["out"] = P_
    if counts is not None:
        counts['att'], counts['car'], counts['qscore'] = c_att, c_car, q_sc
    if stats is not None:
        stats.update({k: v / N for k, v in st_.items()}); stats['poss'] = npos[0] / N; stats['rz'] = rzc[0] / N; stats['rztd'] = rzc[1] / N
    return score[:, 0], score[:, 1]
