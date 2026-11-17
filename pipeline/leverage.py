"""Monte Carlo of the rest of the regular season. Leverage of a game = sum over its two teams of
|P(playoffs | win) - P(playoffs | loss)|. Tiebreakers are approximate: wins, then division wins,
then a coin flip."""
import numpy as np
import pandas as pd
from scipy.stats import norm

from .config import FUTURE_RATING_REGRESS, HFA_PTS, MARGIN_SD, N_SIMS, PLAYS_PER_GAME


def ratings(off_tab, def_tab):
    mu = off_tab.attrs.get("mu", 0.0)
    r = PLAYS_PER_GAME * ((off_tab["value_s"] - mu) - (def_tab["value_s"].reindex(off_tab.index) - mu))
    return r.fillna(0).to_dict()


def simulate(sched, meta, target_week, rate, seed=7):
    rng = np.random.default_rng(seed)
    teams = sorted(meta)
    ix = {t: i for i, t in enumerate(teams)}
    reg = sched[(sched["game_type"] == "REG") & sched["home_team"].isin(ix) & sched["away_team"].isin(ix)]
    div = {t: meta[t]["division"] for t in teams}
    wins = np.zeros((N_SIMS, len(teams)))
    dwins = np.zeros_like(wins)
    played = reg[reg["result"].notna() & (reg["week"] < target_week)]
    for _, g in played.iterrows():
        h, a = ix[g.home_team], ix[g.away_team]
        hw = 1.0 if g.result > 0 else (0.5 if g.result == 0 else 0.0)
        wins[:, h] += hw
        wins[:, a] += 1 - hw
        if div[g.home_team] == div[g.away_team]:
            dwins[:, h] += hw
            dwins[:, a] += 1 - hw
    rem = reg[reg["result"].isna() | (reg["week"] >= target_week)].reset_index(drop=True)
    if not len(rem):
        return {}
    mu = []
    for _, g in rem.iterrows():
        if g.week == target_week and not np.isnan(g.get("spread_line", np.nan)):
            mu.append(float(g.spread_line))
        else:
            mu.append(FUTURE_RATING_REGRESS * (rate.get(g.home_team, 0) - rate.get(g.away_team, 0)) + HFA_PTS)
    p = norm.cdf(np.array(mu) / MARGIN_SD)
    hw = rng.random((N_SIMS, len(rem))) < p
    hi = rem["home_team"].map(ix).values
    ai = rem["away_team"].map(ix).values
    isdiv = np.array([div[h] == div[a] for h, a in zip(rem.home_team, rem.away_team)])
    for j in range(len(rem)):
        wins[:, hi[j]] += hw[:, j]
        wins[:, ai[j]] += ~hw[:, j]
        if isdiv[j]:
            dwins[:, hi[j]] += hw[:, j]
            dwins[:, ai[j]] += ~hw[:, j]
    key = wins + 0.01 * dwins + 1e-4 * rng.random(wins.shape)
    po = np.zeros(wins.shape, dtype=bool)
    for conf in {meta[t]["conf"] for t in teams}:
        cidx = np.array([ix[t] for t in teams if meta[t]["conf"] == conf])
        k = key[:, cidx].copy()
        win_mask = np.zeros_like(k, dtype=bool)
        for d in {div[t] for t in teams if meta[t]["conf"] == conf}:
            didx = np.array([j for j, c in enumerate(cidx) if div[teams[c]] == d])
            best = didx[np.argmax(k[:, didx], axis=1)]
            win_mask[np.arange(N_SIMS), best] = True
        k2 = np.where(win_mask, -np.inf, k)
        wc = np.argsort(-k2, axis=1)[:, :3]
        win_mask[np.arange(N_SIMS)[:, None], wc] = True
        po[:, cidx] = win_mask
    outcomes = _outcomes(rng, teams, ix, meta, div, key, wins, rate)
    n_games = {t: int(((reg["home_team"] == t) | (reg["away_team"] == t)).sum()) for t in teams}
    # This week's games are simulated for leverage even if already played; projected records use the real result.
    corr = {t: 0.0 for t in teams}
    for j, g in rem.iterrows():
        if g.week == target_week and pd.notna(g.get("result")):
            act = 1.0 if g.result > 0 else (0.5 if g.result == 0 else 0.0)
            corr[g.home_team] += act - float(p[j])
            corr[g.away_team] -= act - float(p[j])
    out = {"_teams": {t: round(float(po[:, ix[t]].mean()), 3) for t in teams},
           "_proj": {t: [round(float(wins[:, ix[t]].mean()) + corr[t], 1), round(n_games[t] - float(wins[:, ix[t]].mean()) - corr[t], 1)]
                     for t in teams}, "_outcomes": outcomes}
    for j, g in rem.iterrows():
        h, a = hi[j], ai[j]
        w = hw[:, j]
        lev = 0.0
        team_lev = {}
        for t, won in ((h, w), (a, ~w)):
            if won.all() or (~won).all():
                continue
            d = po[won, t].mean() - po[~won, t].mean()
            team_lev[teams[t]] = round(float(d), 3)
            lev += abs(d)
        out[g.game_id] = {"leverage": round(lev, 3), "by_team": team_lev,
                          "p_playoffs": {teams[h]: round(float(po[:, h].mean()), 3), teams[a]: round(float(po[:, a].mean()), 3)}}
    return out


def _seeds(key, cidx, div_of):
    """Per sim: conference seeds 1-7 as team indices (division winners 1-4 by key, then 3 wild cards)."""
    k = key[:, cidx]
    n = k.shape[0]
    winners = []
    for d in sorted(set(div_of)):
        didx = np.array([j for j, x in enumerate(div_of) if x == d])
        winners.append(didx[np.argmax(k[:, didx], axis=1)])
    winners = np.stack(winners, axis=1)  # n x 4, local indices
    wk = np.take_along_axis(k, winners, axis=1)
    top4 = np.take_along_axis(winners, np.argsort(-wk, axis=1), axis=1)
    k2 = k.copy()
    k2[np.arange(n)[:, None], winners] = -np.inf
    wc = np.argsort(-k2, axis=1)[:, :3]
    return cidx[np.concatenate([top4, wc], axis=1)]  # n x 7 global indices


def _outcomes(rng, teams, ix, meta, div, key, wins, rate):
    """End-of-season outcome odds per team: playoff path (seed, round reached, title) and, for teams that miss,
    draft slot bucket (non-playoff teams pick 1-18 by fewest wins). Playoff games use the same regressed ratings
    as the regular-season sims: higher seed at home, Super Bowl neutral."""
    n, T = wins.shape
    r = np.array([FUTURE_RATING_REGRESS * rate.get(t, 0.0) for t in teams])
    beat = lambda h, a, home: rng.random(len(h)) < norm.cdf((r[h] - r[a] + (HFA_PTS if home else 0.0)) / MARGIN_SD)
    best = np.zeros((n, T), dtype=np.int8)  # 0 out, 1 lost WC, 2 lost DIV, 3 lost CONF, 4 lost SB, 5 won SB
    seed = np.zeros((n, T), dtype=np.int8)
    champs = []
    rows = np.arange(n)
    for conf in sorted({meta[t]["conf"] for t in teams}):
        cidx = np.array([ix[t] for t in teams if meta[t]["conf"] == conf])
        S = _seeds(key, cidx, [div[teams[c]] for c in cidx])
        for j in range(7):
            seed[rows, S[:, j]] = j + 1
            best[rows, S[:, j]] = 1
        alive = [S[:, 0]]  # seed 1 has a bye
        for hs, as_ in ((1, 6), (2, 5), (3, 4)):
            h, a = S[:, hs], S[:, as_]
            alive.append(np.where(beat(h, a, True), h, a))
        alive = np.stack(alive, axis=1)
        sd = seed[rows[:, None], alive]
        alive = np.take_along_axis(alive, np.argsort(sd, axis=1), axis=1)  # reseed: 1 plays the lowest seed left
        for t_ in alive.T:
            best[rows, t_] = 2
        w1 = np.where(beat(alive[:, 0], alive[:, 3], True), alive[:, 0], alive[:, 3])
        w2 = np.where(beat(alive[:, 1], alive[:, 2], True), alive[:, 1], alive[:, 2])
        best[rows, w1], best[rows, w2] = 3, 3
        hi = np.where(seed[rows, w1] < seed[rows, w2], w1, w2)
        lo = np.where(hi == w1, w2, w1)
        champ = np.where(beat(hi, lo, True), hi, lo)
        best[rows, champ] = 4
        champs.append(champ)
    sb = np.where(beat(champs[0], champs[1], False), champs[0], champs[1])
    best[rows, sb] = 5
    # Draft order for teams that miss: fewest wins first (key carries the random tie-break), picks 1-18.
    out_key = np.where(best == 0, key, np.inf)
    order = np.argsort(out_key, axis=1)
    pick = np.zeros((n, T), dtype=np.int8)
    for j in range(18):
        pick[rows, order[:, j]] = j + 1
    res = {}
    for t in teams:
        i = ix[t]
        b, sdd, pk = best[:, i], seed[:, i], pick[:, i]
        f = lambda m: round(float(m.mean()), 4)
        res[t] = {"po": f(b > 0), "bye": f(sdd == 1), "div": f((sdd >= 2) & (sdd <= 4)), "wc": f(sdd >= 5),
                  "r_wc": f(b == 1), "r_div": f(b == 2), "r_conf": f(b == 3), "r_sb": f(b == 4), "champ": f(b == 5),
                  "top3": f((b == 0) & (pk >= 1) & (pk <= 3)), "p4_10": f((b == 0) & (pk >= 4) & (pk <= 10)),
                  "p11_18": f((b == 0) & (pk >= 11))}
    return res
