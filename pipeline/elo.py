"""Our own Elo ratings from game results only (538-style): K=20, home field 48 Elo points, margin-of-victory
multiplier with autocorrelation correction, and one third regression to the mean between seasons."""
import numpy as np
import pandas as pd

K, HFA, MEAN, REVERT = 20.0, 48.0, 1505.0, 1 / 3


def _p(diff):
    return 1.0 / (1.0 + 10 ** (-diff / 400.0))


class Elo:
    def __init__(self, sched, season, week):
        s = sched[sched["result"].notna() | (sched["season"] == season)].copy()
        s = s.sort_values(["season", "week", "gameday", "game_id"], na_position="last")
        self.r, self.pre, self.hist = {}, {}, {}
        cur = None
        for _, g in s.iterrows():
            if g.season != cur:
                cur = g.season
                self.r = {t: MEAN * REVERT + v * (1 - REVERT) for t, v in self.r.items()}
            if g.season > season or (g.season == season and g.week >= week and g.game_type == "REG"):
                continue
            if pd.isna(g.get("result")):
                continue
            h, a = g.home_team, g.away_team
            eh, ea = self.r.get(h, MEAN), self.r.get(a, MEAN)
            hfa = 0.0 if str(g.get("location", "Home")) == "Neutral" else HFA
            ph = _p(eh + hfa - ea)
            self.pre[g.game_id] = ph
            res = float(g.result)
            out = 1.0 if res > 0 else 0.0 if res < 0 else 0.5
            if res != 0:
                wdiff = (eh + hfa - ea) if res > 0 else (ea - eh - hfa)
                mult = np.log(abs(res) + 1) * 2.2 / (wdiff * 0.001 + 2.2)
            else:
                mult = 1.0
            shift = K * mult * (out - ph)
            self.r[h], self.r[a] = eh + shift, ea - shift
            if g.season == season and g.game_type == "REG":
                for t in (h, a):
                    self.hist.setdefault(t, []).append([int(g.week), round(self.r[t], 1)])

    def p_home(self, h, a, neutral=False):
        return round(_p(self.r.get(h, MEAN) + (0.0 if neutral else HFA) - self.r.get(a, MEAN)), 4)

    def card_data(self, h, a, neutral=False):
        return {"p_home": self.p_home(h, a, neutral), "now": {t: round(self.r.get(t, MEAN), 1) for t in (h, a)},
                "hist": {t: self.hist.get(t, []) for t in (h, a)}}
