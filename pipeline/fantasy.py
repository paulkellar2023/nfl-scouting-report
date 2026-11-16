"""Fantasy tab: usage vs. production cards from nflverse expected fantasy points (PPR), weekly player stats
(WOPR) and ESPN QBR. Each card points at players likely to score more or less than they have so far."""
import numpy as np
import pandas as pd

from .context import short_name
from .extras import SRC_FF, SRC_PS, SRC_QBR
from .templates_player import Cards, _r, _rank, _z
from .text import ordinal, possessive as poss

SRC_SNAP = "NFLVERSE SNAP COUNTS (PRO FOOTBALL REFERENCE)"
POS_NAME = {"QB": "quarterbacks", "RB": "running backs", "WR": "wide receivers", "TE": "tight ends"}
MAX_CARDS = 6


def _most(r, n):
    if r == 1:
        return "the most in the NFL"
    if r == n:
        return "the fewest in the NFL"
    return f"{ordinal(r)}-most" if r <= (n + 1) / 2 else f"{ordinal(n + 1 - r)}-fewest"


class Fantasy(Cards):
    def all(self, a, b):
        return [c for c in (self.fpoe(a, b), self.td_luck(a, b), self.volume(a, b), self.matchup(a, b),
                            self.wopr(a, b), self.qbr(a, b), self.snaps(a, b)) if c]

    def snaps(self, a, b):
        tab = self.T.get("snap")
        if tab is None:
            return None
        sub = tab[tab["team"].isin([a, b]) & ((tab["recent"] >= 0.25) | (tab["prior"] >= 0.25))]
        if len(sub) < 3:
            return None
        sub = sub.reindex(sub["delta"].abs().sort_values(ascending=False).index)[:10]
        own = sub.index[0]
        x = sub.loc[own]
        if abs(x["delta"]) < 0.08:
            return None
        nm = x["name"]
        l1 = (f"{nm}'s snap share jumped from {round(100 * x['prior'])}% to {round(100 * x['recent'])}% over his last 3 games." if x["delta"] > 0 else
              f"{nm}'s snap share fell from {round(100 * x['prior'])}% to {round(100 * x['recent'])}% over his last 3 games.")
        l2 = "Usage moves before fantasy points do." if x["delta"] > 0 else "Less time on the field usually means fewer points."
        rows = [{"id": i, "name": r["name"], "short": short_name(r["name"]), "team": r["team"], "v": _r(100 * r["delta"], 1),
                 "hl": i == own, "img": None} for i, r in sub.sort_values("delta", ascending=False).iterrows()]
        return self._card(f"snaps:{own}", x["team"], 0.8 * abs(x["delta"]) / 0.12, l1, l2,
                          f"Offensive snap share, last 3 games minus earlier games, RBs, WRs and TEs, {self.game['span']}.",
                          {"type": "pbars", "fmt": "yds", "axis": "SNAP SHARE CHANGE (PERCENTAGE POINTS)", "rows": rows},
                          f"{nm}: {int(x['n'])} games played", SRC_SNAP)

    def _players(self, a, b, k=6):
        ff = self.T.get("ff")
        if ff is None:
            return None, []
        ids = []
        for t in (a, b):
            sub = ff[(ff["team"] == t) & (ff["xfp_g"] >= 3)]
            ids += list(sub.sort_values("xfp_g", ascending=False).index[:k])
        return ff, ids

    def _row(self, pid, v, hl):
        return {"id": pid, "name": self._name(pid), "short": short_name(self._name(pid)), "team": self.ctx["team"].get(pid),
                "v": _r(v, 2), "hl": hl, "img": self._img(pid) if hl else None}

    def _opp(self, pid, a, b):
        t = self.ctx["team"].get(pid)
        return t, (b if t == a else a)

    def fpoe(self, a, b):
        ff, ids = self._players(a, b)
        if len(ids) < 4:
            return None
        lg = ff[ff["xfp_g"] >= 5]["fpoe_g"]
        sd = float(lg.std()) or 1.0
        own = max(ids, key=lambda p: abs(ff.loc[p, "fpoe_g"]))
        v = float(ff.loc[own, "fpoe_g"])
        t, _ = self._opp(own, a, b)
        nm = self._name(own)
        l1 = f"{nm} scores {abs(v):.1f} PPR points per game {'more' if v > 0 else 'fewer'} than his usage predicts."
        l2 = ("Gaps this big usually shrink, so expect a step back." if v > 0 else
              "Gaps this big usually close, so more points should come.")
        rows = [self._row(p, ff.loc[p, "fpoe_g"], p == own) for p in sorted(ids, key=lambda p: -ff.loc[p, "fpoe_g"])]
        return self._card(f"fpoe:{own}", t, abs(v) / sd, l1, l2,
                          f"Fantasy points per game minus expected, top players on both teams, {self.game['span']}.",
                          {"type": "pbars", "fmt": "yds", "axis": "PPR POINTS PER GAME OVER EXPECTED", "rows": rows},
                          f"Expected points come from each player's targets, carries, depth and field position · {short_name(nm)}: {int(ff.loc[own, 'g'])} games",
                          SRC_FF)

    def td_luck(self, a, b):
        ff, ids = self._players(a, b)
        if len(ids) < 4 or ff["xtd"].isna().all():
            return None
        diff = {p: float(ff.loc[p, "td"] - ff.loc[p, "xtd"]) for p in ids if ff.loc[p, "pos"] != "QB"}
        if len(diff) < 3:
            return None
        own = max(diff, key=lambda p: abs(diff[p]) / np.sqrt(ff.loc[p, "xtd"] + 1))
        v, td, xtd = diff[own], int(ff.loc[own, "td"]), float(ff.loc[own, "xtd"])
        t, _ = self._opp(own, a, b)
        nm = self._name(own)
        l1 = f"{nm} has {td} touchdown{'s' if td != 1 else ''} on {xtd:.1f} expected."
        l2 = ("Touchdowns run hot and cold: expect fewer from here." if v > 0 else
              "His usage says more touchdowns are coming.")
        rows = [self._row(p, diff[p], p == own) for p in sorted(diff, key=lambda p: -diff[p])]
        return self._card(f"td_luck:{own}", t, 0.9 * abs(v) / np.sqrt(xtd + 1), l1, l2,
                          f"Rushing + receiving touchdowns minus expected, {self.game['span']}.",
                          {"type": "pbars", "fmt": "yds", "axis": "TOUCHDOWNS OVER EXPECTED", "rows": rows},
                          "Expected TDs from where and how often each player gets the ball", SRC_FF)

    def volume(self, a, b):
        ff, ids = self._players(a, b, k=2)
        if len(ids) < 2:
            return None
        lg = ff[ff["xfp_g"] >= 5]
        own = max(ids, key=lambda p: ff.loc[p, "xfp_g"])
        t, o = self._opp(own, a, b)
        v, n = float(ff.loc[own, "xfp_g"]), len(lg)
        r = int((lg["xfp_g"] > v).sum()) + 1
        nm, pos = self._name(own), ff.loc[own, "pos"]
        fp = float(ff.loc[own, "fp_g"])
        l2 = f"He is scoring {fp:.1f} per game ({fp - v:+.1f} vs. expected)."
        l1 = f"{nm} gets {v:.1f} expected PPR points per game, {ordinal(r)} of {n}."
        pts = [{**self._row(p, None, p in ids), "x": _r(x, 2), "y": _r(y, 2)} for p, x, y in zip(lg.index, lg["xfp_g"], lg["fp_g"])]
        return self._card(f"volume:{own}", t, 0.15 * (n - r) / max(n, 1) * 6, l1, l2,
                          f"Every player with 5+ expected PPR points per game, {self.game['span']}. Above the line = scoring more than usage.",
                          {"type": "pscatter", "pts": pts, "fmt_x": "num1", "fmt_y": "num1", "diag": "ACTUAL = EXPECTED",
                           "x_label": "EXPECTED PPR POINTS PER GAME", "x_sub": "from usage",
                           "y_label": "ACTUAL PPR POINTS PER GAME", "y_sub": ""},
                          "Opportunity = expected points from targets, carries, air yards and field position", SRC_FF)

    def matchup(self, a, b):
        ff, ids = self._players(a, b)
        dd = self.T.get("ff_def")
        if dd is None or not ids:
            return None
        best = None
        for p in ids:
            t, o = self._opp(p, a, b)
            pos = ff.loc[p, "pos"]
            if (o, pos) not in dd.index:
                continue
            sub = dd.xs(pos, level=1)["fp_g"]
            if len(sub) < 20 or sub.std() == 0:
                continue
            z = (sub[o] - sub.mean()) / sub.std()
            cand = (abs(z) * min(1.0, ff.loc[p, "xfp_g"] / 12), p, t, o, pos, sub, z)
            if best is None or cand[0] > best[0]:
                best = cand
        if best is None:
            return None
        sc, p, t, o, pos, sub, z = best
        r = int((sub > sub[o]).sum()) + 1
        nm = self._name(p)
        l1 = f"{poss(self.M[o]['label'])} defense allows {sub[o]:.1f} PPR points per game to {POS_NAME[pos]}, {_most(r, len(sub))}."
        l2 = (f"Good spot for {nm} ({ff.loc[p, 'xfp_g']:.1f} expected per game)." if z > 0 else
              f"Tough spot for {nm} ({ff.loc[p, 'xfp_g']:.1f} expected per game).")
        srt = sub.sort_values(ascending=False)
        return self._card(f"matchup:{p}", t, sc, l1, l2,
                          f"PPR points allowed per game to {POS_NAME[pos]}, every defense, {self.game['span']}.",
                          {"type": "bars", "fmt": "num1", "pts": [{"team": k, "v": _r(v, 2)} for k, v in srt.items()],
                           "hl": [o], "med": _r(float(sub.median()), 2), "y_label": f"PPR POINTS ALLOWED TO {pos}S"},
                          "Not opportunity-adjusted for the offenses each defense faced", SRC_FF)

    def wopr(self, a, b):
        tab = self.T.get("wopr")
        if tab is None or len(tab) < 8:
            return None
        pr = [(p, t) for t in (a, b) for p in self.ctx["tgt"].get(t, [])[:3] if p in tab.index]
        if not pr:
            return None
        own, t = max(pr, key=lambda x: _z(tab, x[0]))
        v, n, r = float(tab.loc[own, "value"]), int(tab["value"].notna().sum()), _rank(tab, own)
        nm = self._name(own)
        l1 = f"{nm} has a {v:.2f} WOPR, {ordinal(r)} of {n}." if r > 1 else f"No one has a bigger role than {nm} (WOPR {v:.2f})."
        l2 = f"He gets {round(100 * tab.loc[own, 'ts'])}% of targets and {round(100 * tab.loc[own, 'ash'])}% of air yards."
        return self._card(f"wopr:{own}", t, max(_z(tab, own), 0) * 0.9 + (0.2 if r <= 5 else 0), l1, l2,
                          f"Every receiver with 4+ games, {self.game['span']}.",
                          {"type": "pstrip", "pts": [self._pt(p, p in {x for x, _ in pr}, v=val) for p, val in tab["value"].dropna().items()],
                           "fmt": "num1", "axis": "WEIGHTED OPPORTUNITY RATING (WOPR)", "avg": _r(float(tab["value"].mean()))},
                          "WOPR = 1.5 × target share + 0.7 × air-yard share", SRC_PS)

    def qbr(self, a, b):
        tab = self.T.get("qbr")
        if tab is None or len(tab) < 8:
            return None
        found = []
        for t in (a, b):
            pid = self.ctx["qb"].get(t)
            nm = self._name(pid) if pid else None
            if not isinstance(nm, str):
                continue
            hit = tab[(tab.index == nm) & (tab["team"] == t)]
            if not len(hit):
                last = nm.split()[-1]
                hit = tab[(tab["team"] == t) & tab.index.str.endswith(last)]
            if len(hit):
                found.append((pid, t, hit.index[0], float(hit["value"].iloc[0])))
        if not found:
            return None
        vals = tab["value"]
        n = len(vals)
        rk = lambda v: int((vals > v).sum()) + 1
        z = lambda v: (v - vals.mean()) / (vals.std() or 1)
        found.sort(key=lambda x: -abs(z(x[3])))
        pid, t, key, v = found[0]
        nm = self._name(pid)
        l1 = f"{nm} has a {v:.1f} QBR, {ordinal(rk(v))} of {n}."
        l2 = (f"{self._name(found[1][0])} is {ordinal(rk(found[1][3]))} ({found[1][3]:.1f})." if len(found) > 1 else "")
        hl = {f[2] for f in found}
        pts = [{"id": k, "name": k, "short": short_name(k), "team": tm, "hl": k in hl, "v": _r(val, 2),
                "img": self._img(next(f[0] for f in found if f[2] == k)) if k in hl else None}
               for k, tm, val in zip(tab.index, tab["team"], vals)]
        return self._card(f"qbr:{pid}", t, 0.8 * abs(z(v)), l1, l2,
                          f"Every QB with 100+ plays, {self.game['span']}.",
                          {"type": "pstrip", "pts": pts, "fmt": "num1", "axis": "ESPN QBR (0-100, weighted by plays)",
                           "avg": _r(float(vals.mean()))},
                          "QBR credits passing, rushing, sacks and penalties, adjusted for game situation", SRC_QBR)


def snap_table(snaps, season, week):
    """Per player: offensive snap share in his last 3 games vs. his earlier games this season."""
    if snaps is None or not len(snaps) or not {"week", "team", "offense_pct", "player"} <= set(snaps.columns):
        return None
    d = snaps.copy()
    if "season" in d.columns:
        d = d[d["season"] == season]
    if "game_type" in d.columns:
        d = d[d["game_type"] == "REG"]
    d = d[d["week"] < week]
    if "position" in d.columns:
        d = d[d["position"].isin(["RB", "WR", "TE"])]
    d["pct"] = pd.to_numeric(d["offense_pct"], errors="coerce")
    d["pct"] = np.where(d["pct"] > 1.5, d["pct"] / 100, d["pct"])
    key = "pfr_player_id" if "pfr_player_id" in d.columns else "player"
    rows = {}
    for pid, g in d.sort_values("week").groupby(key):
        if len(g) < 5:
            continue
        rec, pri = g["pct"].iloc[-3:].mean(), g["pct"].iloc[:-3].mean()
        rows[pid] = {"name": g["player"].iloc[-1], "team": g["team"].iloc[-1], "recent": rec, "prior": pri,
                     "delta": rec - pri, "n": len(g)}
    return pd.DataFrame.from_dict(rows, orient="index") if rows else None


def select(cards):
    cards = sorted([c for c in cards if c and c.get("score") is not None], key=lambda c: -c["score"])
    return cards[:MAX_CARDS], min(len(cards), MAX_CARDS)
