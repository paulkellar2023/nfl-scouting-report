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
                     for t in teams}}
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
