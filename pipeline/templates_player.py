"""Player-level cards: QBs, lead RBs and top targets for both teams in a matchup."""
import numpy as np

from . import stats as S
from .context import short_name
from .extras import SRC_NGS
from .templates_team import SRC_FTN, SRC_PART, SRC_PBP
from .text import fmt, ordinal, possessive as poss


def build_tables(plays, flags, X=None):
    e = plays[plays["eff"]]
    db = e[e["dropback"] & e["qb_id"].notna()]
    att = e[e["attempt"] & e["passer_player_id"].notna()]
    ru = e[e["designed_run"] & e["rusher_player_id"].notna()]
    T = {"qb_epa": S.eb(S.agg(db, "qb_id", "epa"), 120),
         "qb_sack": S.eb(S.agg(db, "qb_id", "sack"), 120),
         "qb_cpoe": S.eb(S.agg(att[att["cpoe"].notna()], "passer_player_id", "cpoe"), 100),
         "qb_adot": S.eb(S.agg(att, "passer_player_id", "air_yards"), 100),
         "rb_epa": S.eb(S.agg(ru, "rusher_player_id", "epa"), 50),
         "rb_stuff": S.eb(S.agg(ru, "rusher_player_id", "stuffed"), 50),
         "rec_yacoe": S.eb(S.agg(att[att["yacoe"].notna()], "receiver_player_id", "yacoe"), 20)}
    T["qb_prate"] = S.eb(S.agg(db, "qb_id", "pressure"), 120)
    T["qb_clean"] = S.eb(S.agg(db[db["pressure"] == 0], "qb_id", "epa"), 80)
    if flags["coverage"]:
        T["qb_man"] = S.eb(S.agg(att[att["man"] == 1], "passer_player_id", "epa"), 40)
        T["qb_zone"] = S.eb(S.agg(att[att["man"] == 0], "passer_player_id", "epa"), 60)
    a = plays[plays["attempt"] & plays["receiver_player_id"].notna()].copy()
    a["wa"] = a["w"] * a["air_yards"].clip(lower=0)
    g = a.groupby(["posteam", "receiver_player_id"]).agg(tw=("w", "sum"), aw=("wa", "sum"), n=("w", "size")).reset_index()
    tot = g.groupby("posteam")[["tw", "aw"]].transform("sum")
    g["tgt_share"] = g["tw"] / tot["tw"]
    g["air_share"] = g["aw"] / tot["aw"]
    g["wopr"] = 1.5 * g["tgt_share"] + 0.7 * g["air_share"]
    T["shares"] = g[g["n"] >= 30].set_index("receiver_player_id")
    for k in ("qb_ttt", "qb_aggr", "rb_ryoe", "wr_sep", "wr_cush"):
        if X and k in X and len(X[k]) >= 8:
            T[k] = X[k]
    return T


def _z(tab, pid, col="value_s"):
    s = tab[col].dropna()
    raw = tab.loc[s.index, "value"]
    if pid not in s.index or len(s) < 8 or raw.std() == 0:
        return np.nan
    return (s[pid] - s.mean()) / raw.std()


def _rank(tab, pid, high_good=True, col="value_s"):
    s = tab[col].dropna()
    return int(s.rank(ascending=not high_good, method="min")[pid]) if pid in s.index else None


def _r(v, k=4):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), k)


class Cards:
    def __init__(self, T, ctx, M, team_tpls, game):
        self.T, self.ctx, self.M, self.game = T, ctx, M, game
        self.tt = {t.id: t for t in team_tpls}

    def _name(self, pid):
        return self.ctx["names"].get(pid, pid)

    def _img(self, pid):
        if pid in self.ctx["heads"]:
            self.ctx["need_heads"].add(pid)
            return f"assets/heads/{pid}.png"
        return None

    def _pt(self, pid, hl, **kv):
        return {"id": pid, "name": self._name(pid), "short": short_name(self._name(pid)),
                "team": self.ctx["team"].get(pid), "hl": hl, "img": self._img(pid) if hl else None,
                **{k: _r(v) for k, v in kv.items()}}

    def _xy(self, tx, ty, hl, x="value_s", y="value_s"):
        j = tx[[x]].rename(columns={x: "x"}).join(ty[[y]].rename(columns={y: "y"}), how="inner").dropna()
        return [self._pt(p, p in hl, x=r.x, y=r.y) for p, r in j.iterrows()]

    def _card(self, cid, owner, score, t1, t2, sub, chart, note, src=SRC_PBP):
        return {"id": cid, "kind": "player", "phase": cid.split(":")[0], "owner": owner, "score": _r(score, 3),
                "t1": t1, "t2": t2, "sub": sub, "chart": chart, "source": src, "note": note}

    def _team_rank(self, tid, team, side="def", sign=1):
        t = self.tt.get(tid)
        if t is None:
            return None, None
        tab = t.deff if side == "def" else t.off
        return S.rank(tab, team, -sign if side == "def" else sign), int(tab["value_s"].notna().sum())

    def watch(self, a, b, cards):
        """QB duel by EPA/dropback rank, plus the highest-scoring non-QB player card as the x-factor."""
        tab = self.T["qb_epa"]
        n = int(tab["value_s"].notna().sum())
        qbs = [{"team": self.M[t]["label"], "name": self._name(q), "rank": _rank(tab, q), "of": n}
               for q, t in self._pair(tab, a, b)]
        x = next((c for c in cards if not c["id"].startswith("qb_")), None)
        return {"qbs": qbs, "xfactor": {"team": self.M[x["owner"]]["label"], "headline": x["t1"], "detail": x["t2"]} if x else None}

    def all(self, a, b):
        out = []
        for f in (self.qb_epa, self.qb_pressure, self.qb_cpoe, self.qb_man, self.rb, self.wr_share, self.rec_yac,
                  self.qb_ttt, self.qb_aggr, self.rb_ryoe, self.wr_sep):
            try:
                c = f(a, b)
            except (KeyError, ValueError):
                c = None
            if c:
                out.append(c)
        return out

    def _pair(self, tab, a, b):
        qa, qb = self.ctx["qb"].get(a), self.ctx["qb"].get(b)
        valid = tab["value_s"].dropna().index
        return [(q, t) for q, t in ((qa, a), (qb, b)) if q in valid]

    def qb_epa(self, a, b):
        tab = self.T["qb_epa"]
        pr = self._pair(tab, a, b)
        if not pr:
            return None
        n = int(tab["value_s"].notna().sum())
        own, ot = max(pr, key=lambda x: abs(_z(tab, x[0])))
        r = _rank(tab, own)
        l1 = f"{self._name(own)} ranks {ordinal(r)} of {n} in EPA per dropback." if r > 1 else f"No QB is more efficient than {self._name(own)}."
        oth = [p for p in pr if p[0] != own]
        l2 = (f"{self._name(oth[0][0])} ranks {ordinal(_rank(tab, oth[0][0]))}." if oth else
              f"{self.M[b if ot == a else a]['label']} has no qualified starter.")
        hl = {p for p, _ in pr}
        pts = [self._pt(p, p in hl, v=v) for p, v in tab["value_s"].dropna().items()]
        sc = abs(_z(tab, own)) + (0.25 if r in (1, n) else 0)
        return self._card(f"qb_epa:{own}", ot, sc, l1, l2, f"Every QB with 120+ dropbacks ({n}), {self.game['span']}.",
                          {"type": "pstrip", "pts": pts, "fmt": "epa", "axis": "EPA PER DROPBACK",
                           "avg": _r(float(tab["value_s"].dropna().mean()))},
                          f"Shrunk to league mean · garbage time removed · {short_name(self._name(own))}: n={int(tab.loc[own, 'n'])} dropbacks")

    def qb_pressure(self, a, b):
        tc, tp = self.T["qb_clean"], self.T["qb_prate"]
        pr = [x for x in self._pair(tp, a, b) if x[0] in tc["value_s"].dropna().index]
        if not pr:
            return None
        own, ot = max(pr, key=lambda x: abs(_z(tc, x[0])) + abs(_z(tp, x[0])))
        zc, zp = _z(tc, own), _z(tp, own)
        nm = self._name(own)
        opp = b if ot == a else a
        rk, nk = self._team_rank("pressure", opp, "def", -1)
        if zc > 0.5 and zp > 0.5:
            l1, l2 = f"{nm} is good when clean.", "He's rarely clean."
        elif zc > 0.5:
            l1, l2 = f"{nm} is good when clean.", "And he usually is."
        elif zc < -0.5 and zp > 0.5:
            l1, l2 = f"{nm} struggles even when clean.", "And he's under fire."
        elif zc < -0.5:
            l1, l2 = f"{nm} struggles even from a clean pocket.", f"{poss(self.M[opp]['label'])} rush ranks {ordinal(rk)}." if rk else "Pressure isn't the problem."
        else:
            l1 = f"{nm} ranks {ordinal(_rank(tp, own, False))} in avoiding pressure."
            l2 = f"{poss(self.M[opp]['label'])} pass rush ranks {ordinal(rk)}." if rk else "His clean-pocket play is average."
        hl = {p for p, _ in pr}
        pts = self._xy(tp, tc, hl)
        plab = "PRESSURE RATE" if self.ctx["flags"]["pressure"] == "participation" else "QB HIT + SACK RATE"
        sc = max(abs(zc), abs(zp)) + (0.4 if (zc > 0.5 and zp > 0.5) else 0)
        src = f"{SRC_PBP} · {SRC_PART}" if self.ctx["flags"]["pressure"] == "participation" else SRC_PBP
        return self._card(f"qb_pressure:{own}", ot, sc, l1, l2, f"Every QB with 120+ dropbacks, {self.game['span']}. Dashed lines = QB median.",
                          {"type": "pscatter", "pts": pts, "fmt_x": "pct", "fmt_y": "epa", "x_label": plab,
                           "x_sub": "% of dropbacks", "y_label": "EPA FROM A CLEAN POCKET", "y_sub": "per dropback, no pressure",
                           "med": [_r(float(np.median([p['x'] for p in pts]))), _r(float(np.median([p['y'] for p in pts])))],
                           "quad": ("GOOD WHEN CLEAN, OFTEN CLEAN", "GOOD WHEN CLEAN, RARELY CLEAN",
                                    "STRUGGLES CLEAN, OFTEN CLEAN", "STRUGGLES CLEAN, RARELY CLEAN")},
                          f"Shrunk to league mean · {short_name(nm)}: n={int(tp.loc[own, 'n'])} dropbacks", src)

    def qb_cpoe(self, a, b):
        tc, ta = self.T["qb_cpoe"], self.T["qb_adot"]
        pr = [x for x in self._pair(tc, a, b) if x[0] in ta["value_s"].dropna().index]
        if not pr:
            return None
        n = int(tc["value_s"].notna().sum())
        own, ot = max(pr, key=lambda x: abs(_z(tc, x[0])))
        r = _rank(tc, own)
        nm = self._name(own)
        ad = _rank(ta, own)
        depth = "deep" if ad <= 8 else ("short" if ad > n - 8 else "")
        if r <= 5:
            l1 = f"{nm} is {ordinal(r)} in completion % over expected."
        elif r > n - 5:
            l1 = f"{nm} ranks {ordinal(r)} of {n} in completion % over expected."
        else:
            l1 = f"{nm}: {fmt(tc.loc[own, 'value_s'] / 100, 'pct_pm')} completion % over expected."
        l2 = (f"While throwing {depth}." if depth else f"On throws {ta.loc[own, 'value_s']:.1f} yards downfield on average.")
        hl = {p for p, _ in pr}
        pts = self._xy(ta, tc, hl)
        return self._card(f"qb_cpoe:{own}", ot, abs(_z(tc, own)) + (0.25 if r in (1, n) else 0), l1, l2,
                          f"Every QB with 100+ attempts, {self.game['span']}.",
                          {"type": "pscatter", "pts": pts, "fmt_x": "num1", "fmt_y": "num1", "x_label": "AVERAGE DEPTH OF TARGET",
                           "x_sub": "air yards per attempt", "y_label": "COMPLETION % OVER EXPECTED", "y_sub": "nflverse CPOE",
                           "med": [_r(float(np.median([p['x'] for p in pts]))), 0]},
                          f"Shrunk to league mean · {short_name(nm)}: n={int(tc.loc[own, 'n'])} attempts")

    def qb_man(self, a, b):
        if "qb_man" not in self.T:
            return None
        tm, tz = self.T["qb_man"], self.T["qb_zone"]
        pr = [x for x in self._pair(tm, a, b) if x[0] in tz["value_s"].dropna().index]
        if not pr:
            return None
        mz = self.tt.get("man_zone")

        def opp_man(t):
            o = b if t == a else a
            return S.zscore(mz.freq, o) if mz is not None else 0.0
        own, ot = max(pr, key=lambda x: abs(_z(tm, x[0])) * (1 + 0.3 * max(opp_man(x[1]), 0)))
        opp = b if ot == a else a
        nm = self._name(own)
        zm = _z(tm, own)
        rf = S.rank(mz.freq, opp, 1) if mz is not None else None
        l1 = f"{nm} {'shreds' if zm > 0.5 else 'struggles against' if zm < -0.5 else 'is average against'} man coverage."
        l2 = f"{self.M[opp]['label']} plays man {ordinal(rf)}-most." if rf else ""
        pts = self._xy(tz, tm, {p for p, _ in pr})
        return self._card(f"qb_man:{own}", ot, abs(zm) * (1 + 0.3 * max(opp_man(ot), 0)), l1, l2,
                          f"Every QB with 40+ attempts vs. man, {self.game['span']}.",
                          {"type": "pscatter", "pts": pts, "fmt_x": "epa", "fmt_y": "epa", "x_label": "EPA VS. ZONE",
                           "x_sub": "per attempt", "y_label": "EPA VS. MAN", "y_sub": "per attempt",
                           "med": [_r(float(np.median([p['x'] for p in pts]))), _r(float(np.median([p['y'] for p in pts])))],
                           "diag": "same vs. man and zone"},
                          f"Shrunk to league mean · {short_name(nm)}: n={int(tm.loc[own, 'n'])} attempts vs. man",
                          f"{SRC_PBP} · {SRC_PART}")

    def rb(self, a, b):
        te, ts = self.T["rb_epa"], self.T["rb_stuff"]
        valid = te["value_s"].dropna().index
        pr = [(self.ctx["rb"].get(t), t) for t in (a, b) if self.ctx["rb"].get(t) in valid]
        if not pr:
            return None

        def sc(x):
            return max(abs(_z(te, x[0])), abs(_z(ts, x[0])))
        own, ot = max(pr, key=sc)
        opp = b if ot == a else a
        nm = self._name(own)
        zs, ze = _z(ts, own), _z(te, own)
        n = int(te["value_s"].notna().sum())
        rs, ns = self._team_rank("stuff", opp, "def", -1)
        rr, nr = self._team_rank("rush_epa", opp, "def", 1)
        if zs > 0.8:
            l1, l2 = f"{nm} is running into a wall.", (f"{poss(self.M[opp]['label'])} run front ranks {ordinal(rs)} in stuffs." if rs else "")
        elif ze > 0.8:
            l1 = f"{nm} ranks {ordinal(_rank(te, own))} of {n} in EPA per carry."
            l2 = f"{poss(self.M[opp]['label'])} run defense ranks {ordinal(rr)}." if rr else ""
        elif ze < -0.8:
            l1, l2 = f"{nm} isn't creating much.", f"{ordinal(_rank(te, own))} of {n} in EPA per carry."
        else:
            l1, l2 = f"{nm} carries the load for {self.M[ot]['label']}.", f"{ordinal(_rank(te, own))} of {n} in EPA per carry."
        pts = self._xy(ts, te, {p for p, _ in pr})
        return self._card(f"rb:{own}", ot, sc((own, ot)), l1, l2, f"Every RB with 50+ designed runs, {self.game['span']}.",
                          {"type": "pscatter", "pts": pts, "fmt_x": "pct", "fmt_y": "epa", "x_label": "CARRIES STUFFED",
                           "x_sub": "0 yds or less", "y_label": "EPA PER CARRY", "y_sub": "designed runs",
                           "med": [_r(float(np.median([p['x'] for p in pts]))), _r(float(np.median([p['y'] for p in pts])))],
                           "trend": True},
                          f"Shrunk to league mean · {short_name(nm)}: n={int(te.loc[own, 'n'])} carries")

    def wr_share(self, a, b):
        sh = self.T["shares"]
        pr = [(p, t) for t in (a, b) for p in self.ctx["tgt"].get(t, [])[:1] if p in sh.index]
        if not pr:
            return None
        z = (sh["wopr"] - sh["wopr"].mean()) / sh["wopr"].std()
        own, ot = max(pr, key=lambda x: z.get(x[0], 0))
        nm = self._name(own)
        opp = b if ot == a else a
        rp_, np_ = self._team_rank("pass_epa", opp, "def", 1)
        l1 = f"{nm} gets {fmt(sh.loc[own, 'tgt_share'], 'pct')} of {poss(self.M[ot]['label'])} targets and {fmt(sh.loc[own, 'air_share'], 'pct')} of its air yards."
        l2 = f"{poss(self.M[opp]['label'])} pass defense ranks {ordinal(rp_)}." if rp_ else "The offense runs through him."
        hl = {p for p, _ in pr}
        pts = [self._pt(p, p in hl, x=r.tgt_share, y=r.air_share) for p, r in sh.iterrows()]
        return self._card(f"wr_share:{own}", ot, float(z.get(own, 0)), l1, l2,
                          f"Every receiver with 30+ targets, {self.game['span']}.",
                          {"type": "pscatter", "pts": pts, "fmt_x": "pct", "fmt_y": "pct", "x_label": "TARGET SHARE",
                           "x_sub": "recency-weighted", "y_label": "AIR YARDS SHARE", "y_sub": "recency-weighted",
                           "med": [_r(float(sh["tgt_share"].median())), _r(float(sh["air_share"].median()))]},
                          f"All game states · {short_name(nm)}: n={int(sh.loc[own, 'n'])} targets")

    def rec_yac(self, a, b):
        ty = self.T["rec_yacoe"]
        valid = ty["value_s"].dropna().index
        pr = [(p, t) for t in (a, b) for p in self.ctx["tgt"].get(t, []) if p in valid]
        if not pr:
            return None
        own, ot = max(pr, key=lambda x: abs(_z(ty, x[0])))
        opp = b if ot == a else a
        nm = self._name(own)
        v = ty.loc[own, "value_s"]
        n = int(ty["value_s"].notna().sum())
        ro, no = self._team_rank("yacoe", opp, "def", 1)
        l1 = (f"{nm} adds {v:+.1f} yards after the catch over expected." if v > 0 else
              f"{nm} gives back {abs(v):.1f} yards after the catch vs. expected.")
        l2 = f"{poss(self.M[opp]['label'])} defense ranks {ordinal(ro)} in YAC allowed over expected." if ro else ""
        hl = {p for p, _ in pr}
        pts = [self._pt(p, p in hl, v=x) for p, x in ty["value_s"].dropna().items()]
        return self._card(f"rec_yac:{own}", ot, abs(_z(ty, own)) + (0.25 if _rank(ty, own) in (1, n) else 0), l1, l2,
                          f"Every receiver with 20+ catches ({n}), {self.game['span']}.",
                          {"type": "pstrip", "pts": pts, "fmt": "yds", "axis": "YAC OVER EXPECTED PER CATCH", "avg": 0},
                          f"Shrunk to league mean · {short_name(nm)}: n={int(ty.loc[own, 'n'])} catches")


    # ---------- Next Gen Stats ----------
    def _strip(self, tab, own, hl, fmt_, axis):
        return {"type": "pstrip", "pts": [self._pt(p, p in hl, v=v) for p, v in tab["value_s"].dropna().items()],
                "fmt": fmt_, "axis": axis, "avg": _r(float(tab["value_s"].dropna().mean()))}

    def qb_ttt(self, a, b):
        tab = self.T.get("qb_ttt")
        pr = self._pair(tab, a, b) if tab is not None else []
        if not pr:
            return None
        rush = self.tt.get("pressure")

        def rz(t):
            z = S.zscore(rush.deff, b if t == a else a, 1) if rush is not None else np.nan
            return 0.0 if np.isnan(z) else z
        own, ot = max(pr, key=lambda x: abs(_z(tab, x[0])) * (1 + 0.3 * max(rz(x[1]), 0)))
        opp = b if ot == a else a
        nm, v, z, n = self._name(own), float(tab.loc[own, "value_s"]), _z(tab, own), int(tab["value_s"].notna().sum())
        r = _rank(tab, own)
        rk, _ = self._team_rank("pressure", opp, "def", -1)
        rush_txt = f"{poss(self.M[opp]['label'])} pass rush ranks {ordinal(rk)}." if rk else "Protection has to hold up."
        if z > 0.5:
            l1, l2 = f"{nm} holds the ball {v:.2f} seconds per throw, {ordinal(r)}-longest of {n}.", rush_txt
        elif z < -0.5:
            l1 = f"{nm} gets the ball out in {v:.2f} seconds, {ordinal(n + 1 - r)}-fastest of {n}."
            l2 = f"That blunts {poss(self.M[opp]['label'])} pass rush ({ordinal(rk)})." if rk else "Quick game first."
        else:
            l1, l2 = f"{nm} averages {v:.2f} seconds to throw.", rush_txt
        return self._card(f"qb_ttt:{own}", ot, abs(z) * (1 + 0.3 * max(rz(ot), 0)), l1, l2,
                          f"Every QB with 100+ attempts ({n}), {self.game['span']}.",
                          self._strip(tab, own, {p for p, _ in pr}, "sec", "AVERAGE TIME TO THROW (SECONDS)"),
                          f"Snap to throw · recency-weighted · {short_name(nm)}: n={int(tab.loc[own, 'n'])} attempts", SRC_NGS)

    def qb_aggr(self, a, b):
        tab = self.T.get("qb_aggr")
        pr = self._pair(tab, a, b) if tab is not None else []
        if not pr:
            return None
        own, ot = max(pr, key=lambda x: abs(_z(tab, x[0])))
        opp = b if ot == a else a
        nm, v, z, n = self._name(own), float(tab.loc[own, "value_s"]), _z(tab, own), int(tab["value_s"].notna().sum())
        r = _rank(tab, own)
        rp_, _ = self._team_rank("pass_epa", opp, "def", 1)
        l1 = (f"{nm} throws into tight windows on {fmt(v, 'pct')} of passes, {ordinal(r)}-most of {n}." if z >= 0 else
              f"{nm} throws into tight windows on just {fmt(v, 'pct')} of passes, {ordinal(n + 1 - r)}-fewest of {n}.")
        l2 = f"{poss(self.M[opp]['label'])} pass defense ranks {ordinal(rp_)}." if rp_ else ""
        return self._card(f"qb_aggr:{own}", ot, 0.85 * abs(z), l1, l2, f"Every QB with 100+ attempts ({n}), {self.game['span']}.",
                          self._strip(tab, own, {p for p, _ in pr}, "pct", "TIGHT-WINDOW THROW RATE (AGGRESSIVENESS)"),
                          f"Tight window = defender within 1 yard at the catch point · {short_name(nm)}: n={int(tab.loc[own, 'n'])} attempts", SRC_NGS)

    def rb_ryoe(self, a, b):
        tab = self.T.get("rb_ryoe")
        if tab is None:
            return None
        valid = tab["value_s"].dropna().index
        pr = [(self.ctx["rb"].get(t), t) for t in (a, b) if self.ctx["rb"].get(t) in valid]
        if not pr:
            return None
        own, ot = max(pr, key=lambda x: abs(_z(tab, x[0])))
        opp = b if ot == a else a
        nm, v, n = self._name(own), float(tab.loc[own, "value_s"]), int(tab["value_s"].notna().sum())
        r = _rank(tab, own)
        rr, _ = self._team_rank("rush_epa", opp, "def", 1)
        l1 = (f"{nm} gains {v:+.1f} rushing yards over expected per carry, {ordinal(r)} of {n}." if v >= 0 else
              f"{nm} runs {abs(v):.1f} yards per carry below expected, {ordinal(r)} of {n}.")
        l2 = f"{poss(self.M[opp]['label'])} run defense ranks {ordinal(rr)}." if rr else ""
        return self._card(f"rb_ryoe:{own}", ot, abs(_z(tab, own)) + (0.25 if r in (1, n) else 0), l1, l2,
                          f"Every RB with 50+ carries ({n}), {self.game['span']}.",
                          self._strip(tab, own, {p for p, _ in pr}, "yds", "RUSH YARDS OVER EXPECTED PER CARRY"),
                          f"Expected yards from player tracking at the handoff · {short_name(nm)}: n={int(tab.loc[own, 'n'])} carries", SRC_NGS)

    def wr_sep(self, a, b):
        ts, tc = self.T.get("wr_sep"), self.T.get("wr_cush")
        if ts is None or tc is None:
            return None
        valid = ts["value_s"].dropna().index.intersection(tc["value_s"].dropna().index)
        pr = [(p, t) for t in (a, b) for p in self.ctx["tgt"].get(t, [])[:3] if p in valid]
        if not pr:
            return None
        own, ot = max(pr, key=lambda x: _z(ts, x[0]))
        opp = b if ot == a else a
        nm, v, n = self._name(own), float(ts.loc[own, "value_s"]), int(ts["value_s"].notna().sum())
        r = _rank(ts, own)
        rp_, _ = self._team_rank("pass_epa", opp, "def", 1)
        l1 = f"{nm} averages {v:.1f} yards of separation, {ordinal(r)} of {n}." if r > 1 else f"No receiver gets open like {nm} ({v:.1f} yards)."
        l2 = f"{poss(self.M[opp]['label'])} pass defense ranks {ordinal(rp_)}." if rp_ else ""
        pts = self._xy(tc, ts, {p for p, _ in pr})
        return self._card(f"wr_sep:{own}", ot, max(_z(ts, own), 0) + (0.25 if r == 1 else 0), l1, l2,
                          f"Every receiver with 25+ targets, {self.game['span']}. Dashed lines = median.",
                          {"type": "pscatter", "pts": pts, "fmt_x": "num1", "fmt_y": "num1", "x_label": "CUSHION AT THE SNAP",
                           "x_sub": "yards to nearest defender", "y_label": "SEPARATION AT THE CATCH", "y_sub": "yards to nearest defender",
                           "med": [_r(float(np.median([p['x'] for p in pts]))), _r(float(np.median([p['y'] for p in pts])))]},
                          f"Recency-weighted · {short_name(nm)}: n={int(ts.loc[own, 'n'])} targets", SRC_NGS)


def select(cards, lo, hi, cap=10):
    """Default picks first (max 3 QB cards), then the rest by score. Returns (cards, default count)."""
    cards = sorted([c for c in cards if c and c.get("score") is not None], key=lambda c: -c["score"])
    top, qb = [], 0
    for c in cards:
        is_qb = c["id"].startswith("qb_")
        if is_qb and qb >= 3:
            continue
        top.append(c)
        qb += is_qb
        if len(top) >= hi:
            break
    rest = [c for c in cards if c not in top]
    return (top + rest)[:cap], len(top)
