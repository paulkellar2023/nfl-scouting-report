"""Edge scoring, card selection, headlines, charts and rule-based keys for team templates."""
import numpy as np
import pandas as pd

from . import stats as S
from .clean import GAP_ORDER
from .config import GAP_MAX_PENALTY, MAX_CARDS_PER_PHASE, SOFT_SCORE_FLOOR
from .templates_team import SRC_FTN, SRC_PART, SRC_PBP
from .text import fmt, ordinal, possessive as poss, rank_phrase as rp

QUADS = {
    "early_down": ("RUNS MORE, PASSES WELL", "THROWS MORE, PASSES WELL", "RUNS MORE, PASSES POORLY", "THROWS MORE, PASSES POORLY"),
    "play_action": ("RARE PLAY ACTION, IT WORKS", "HEAVY PLAY ACTION, IT WORKS", "RARE PLAY ACTION, STRUGGLES", "HEAVY PLAY ACTION, STRUGGLES"),
    "motion": ("LITTLE MOTION, IT WORKS", "LOTS OF MOTION, IT WORKS", "LITTLE MOTION, STRUGGLES", "LOTS OF MOTION, STRUGGLES"),
    "blitz": ("RARELY BLITZES, IT WORKS", "BLITZES A LOT, IT WORKS", "RARELY BLITZES, GETS BURNED", "BLITZES A LOT, GETS BURNED"),
    "four_man": ("FINISHES THE PRESSURE IT GETS", "PRESSURES AND FINISHES", "LITTLE PRESSURE, FEW SACKS", "PRESSURES, BUT CAN'T FINISH"),
    "short_yd": ("RUNS WELL, RARELY RUNS", "RUNS WELL, RUNS A LOT", "STRUGGLES, RARELY RUNS", "STRUGGLES, RUNS A LOT"),
}
SHELL_NAME = {"COVER_0": "Cover 0", "COVER_1": "Cover 1", "COVER_2": "Cover 2", "COVER_2_MAN": "2-Man",
              "2_MAN": "2-Man", "COVER_3": "Cover 3", "COVER_4": "Cover 4", "COVER_6": "Cover 6",
              "COVER_9": "Cover 9", "PREVENT": "Prevent"}
GAP_PHRASE = {"L END": "outside left", "L TACKLE": "off left tackle", "L GUARD": "inside left",
              "MIDDLE": "up the middle", "R GUARD": "inside right", "R TACKLE": "off right tackle",
              "R END": "outside right"}


def _r(v, k=4):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), k)


def _pts(tab):
    return [{"team": t, "v": _r(v)} for t, v in tab["value_s"].dropna().items()]


def _xy(tx, ty):
    j = pd.concat([tx["value_s"].rename("x"), ty["value_s"].rename("y")], axis=1).dropna()
    return [{"team": t, "x": _r(r.x), "y": _r(r.y)} for t, r in j.iterrows()]


def _med(points, k):
    vals = [p[k] for p in points if p.get(k) is not None]
    return _r(float(np.median(vals))) if vals else None


def _n(tab, team):
    try:
        return int(tab.loc[team, "n"])
    except KeyError:
        return 0


def _count(tab):
    return int(tab["value_s"].notna().sum())


def _val(tab, team):
    try:
        return float(tab.loc[team, "value_s"])
    except KeyError:
        return np.nan


# ---------- generic templates ----------

def evaluate(t, a, b):
    za, zb = S.zscore(t.off, a, t.sign), S.zscore(t.deff, b, t.sign)
    if np.isnan(za) or np.isnan(zb):
        return None
    e, zf, rf, nf = za + zb, None, None, None
    if t.kind == "tendency":
        ch = a if t.chooser == "off" else b
        zf = S.zscore(t.freq, ch)
        zf = 0.0 if np.isnan(zf) else zf
        e *= float(np.clip(0.75 + 0.25 * zf, 0.25, 1.5))
        rf, nf = S.rank(t.freq, ch, 1), _count(t.freq)
    clash = min(za, -zb) if (za > 0 and zb < 0) else 0.0
    ra, rb = S.rank(t.off, a, t.sign), S.rank(t.deff, b, -t.sign)
    na, nb = _count(t.off), _count(t.deff)
    extreme = ra in (1, na) or rb in (1, nb) or (rf is not None and rf in (1, nf))
    score = t.weight * (max(abs(e), 0.75 * clash) + (0.25 if extreme else 0.0))
    return {"tpl": t, "id": t.id, "phase": t.phase, "a": a, "b": b, "edge": t.weight * e, "za": za, "zb": zb,
            "zf": zf, "ra": ra, "rb": rb, "rf": rf, "na": na, "nb": nb, "nf": nf, "clash": clash,
            "score": score, "owner": a if e >= 0 else b}


def _head_unit(c, M):
    t, a, b = c["tpl"], c["a"], c["b"]
    A, B = M[a]["label"], M[b]["label"]
    ra, rb, na, nb = c["ra"], c["rb"], c["na"], c["nb"]
    sA, wA, sB, wB = ra <= 8, ra > na - 8, rb <= 8, rb > nb - 8
    if c["owner"] == a:
        if sA and wB:
            return f"{A} has the {rp(ra, na)} {t.unit_off}.", f"{B} has the {rp(rb, nb)} {t.unit_def}."
        if sA and sB:
            return f"{A} has the {rp(ra, na)} {t.unit_off}.", f"{poss(B)} {t.unit_def} is {rp(rb, nb)}. Something gives."
        if sA:
            return f"{A} has the {rp(ra, na)} {t.unit_off}.", f"{poss(B)} {t.unit_def} ranks {ordinal(rb)}."
        if wB:
            return f"{B} has the {rp(rb, nb)} {t.unit_def}.", f"That's {poss(A)} opening."
        return f"{poss(A)} {t.unit_off} has the edge.", f"{A} ranks {ordinal(ra)}. {B} ranks {ordinal(rb)} defending it."
    if sB and wA:
        return f"{B} has the {rp(rb, nb)} {t.unit_def}.", f"{A} has the {rp(ra, na)} {t.unit_off}."
    if sB and sA:
        return f"{B} has the {rp(rb, nb)} {t.unit_def}.", f"{poss(A)} {t.unit_off} is {rp(ra, na)}. Something gives."
    if sB:
        return f"{B} has the {rp(rb, nb)} {t.unit_def}.", f"{poss(A)} {t.unit_off} ranks {ordinal(ra)}."
    if wA:
        return f"{A} has the {rp(ra, na)} {t.unit_off}.", f"{B} can lean on that."
    return f"{poss(B)} {t.unit_def} has the edge.", f"{B} ranks {ordinal(rb)}. {A} ranks {ordinal(ra)}."


def _head_tend(c, M):
    t, a, b = c["tpl"], c["a"], c["b"]
    A, B = M[a]["label"], M[b]["label"]
    ra, rb, na, nb, rf, nf = c["ra"], c["rb"], c["na"], c["nb"], c["rf"], c["nf"]
    sA, wA, sB, wB = ra <= 8, ra > na - 8, rb <= 8, rb > nb - 8
    if 4 < rf <= nf - 4:
        return _head_unit(c, M)
    if t.chooser == "off":
        if rf == 1:
            l1 = f"No team {t.more} than {A}."
        elif rf <= 4:
            l1 = f"{A} {t.more} than almost anyone."
        elif rf > nf - 4:
            l1 = f"{A} rarely {t.verb}."
        else:
            l1 = f"{A} ranks {ordinal(rf)} in {t.freq_label}."
        if c["owner"] == a:
            l2 = f"And {B} can't stop it." if wB else ("And it works." if sA else f"{B} ranks {ordinal(rb)} defending it.")
        else:
            l2 = f"{B} is built to stop it." if sB else ("It isn't working." if wA else f"{B} ranks {ordinal(rb)} defending it.")
        return l1, l2
    if rf == 1:
        l1 = f"No defense {t.more} than {B}."
    elif rf <= 4:
        l1 = f"{B} {t.more} than almost anyone."
    elif rf > nf - 4:
        l1 = f"{B} rarely {t.verb}."
    else:
        l1 = f"{B} ranks {ordinal(rf)} in {t.freq_label}."
    if c["owner"] == a:
        l2 = f"{A} feasts on it." if sA else (f"And it isn't working for {B}." if wB else f"{A} ranks {ordinal(ra)} against it.")
    else:
        l2 = "And it works." if sB else (f"{A} struggles against it." if wA else f"{A} ranks {ordinal(ra)} against it.")
    return l1, l2


def _chart(c, M):
    t, a, b, own = c["tpl"], c["a"], c["b"], c["owner"]
    A, B = M[a]["label"], M[b]["label"]
    if t.chart == "duel":
        allp = _pts(t.off) + _pts(t.deff)
        return {"type": "duel", "fmt": t.fmt, "axis": t.label.upper(), "better_off": "right" if t.sign > 0 else "left",
                "avg": _r(float(np.mean([p["v"] for p in allp]))),
                "rows": [{"label": f"{A} {t.unit_off}".upper(), "side": "off", "hl": a, "pts": _pts(t.off)},
                         {"label": f"{B} {t.unit_def}".upper(), "side": "def", "hl": b, "pts": _pts(t.deff)}]}
    if t.chart == "scatter_off":
        pts = _xy(t.freq, t.off)
        return {"type": "scatter", "pts": pts, "hl": [a], "fmt_x": t.freq_fmt, "fmt_y": t.fmt,
                "x_label": t.freq_label.upper(), "x_sub": "share of plays" if t.freq_fmt == "pct" else "vs. expected, neutral script",
                "y_label": t.label.upper(), "y_sub": "every offense", "med": [_med(pts, "x"), _med(pts, "y")],
                "quad": QUADS.get(t.id)}
    if t.chart == "scatter_def":
        pts = _xy(t.freq, t.deff)
        return {"type": "scatter", "pts": pts, "hl": [b], "fmt_x": "pct", "fmt_y": t.fmt, "invert_y": True,
                "x_label": t.freq_label.upper(), "x_sub": "share of dropbacks", "y_label": "EPA ALLOWED WHEN THEY DO",
                "y_sub": "per dropback, up = better defense", "med": [_med(pts, "x"), _med(pts, "y")],
                "quad": QUADS.get(t.id)}
    if t.chart == "scatter_depth":
        pts = _xy(t.extra["adot_dev"], t.extra["epa_att_def"])
        return {"type": "scatter", "pts": pts, "hl": [b], "fmt_x": "yds", "fmt_y": "epa",
                "x_label": "AIR YARDS VS. NORMAL", "x_sub": "opponents' aDOT vs. their season average",
                "y_label": "EPA ALLOWED", "y_sub": "per pass attempt", "med": [0, _med(pts, "y")]}
    if t.chart == "scatter_yac":
        if own == a:
            pts = _xy(t.extra["adot"], t.off)
            return {"type": "scatter", "pts": pts, "hl": [a], "fmt_x": "num1", "fmt_y": "yds",
                    "x_label": "AVERAGE DEPTH OF TARGET", "x_sub": "air yards per attempt",
                    "y_label": "YAC OVER EXPECTED", "y_sub": "per completion", "med": [_med(pts, "x"), 0]}
        pts = _xy(t.extra["adot_dev"], t.deff)
        return {"type": "scatter", "pts": pts, "hl": [b], "fmt_x": "yds", "fmt_y": "yds",
                "x_label": "AIR YARDS VS. NORMAL", "x_sub": "opponents' aDOT vs. their season average",
                "y_label": "YAC OVER EXPECTED", "y_sub": "allowed per completion", "med": [0, 0]}
    if t.chart == "scatter_mz":
        pts = _xy(t.extra["zone"], t.off)
        return {"type": "scatter", "pts": pts, "hl": [a], "fmt_x": "epa", "fmt_y": "epa",
                "x_label": "EPA VS. ZONE", "x_sub": "per attempt", "y_label": "EPA VS. MAN", "y_sub": "per attempt",
                "med": [_med(pts, "x"), _med(pts, "y")], "diag": "same vs. man and zone"}
    if t.chart == "four_man":
        pts = _xy(t.deff, t.extra["sack4"])
        xs = np.array([p["x"] for p in pts])
        ys = np.array([p["y"] for p in pts])
        sl, ic = np.polyfit(xs, ys, 1) if len(pts) > 3 else (0, 0)
        return {"type": "scatter", "pts": pts, "hl": [b], "fmt_x": "pct", "fmt_y": "pct1",
                "x_label": "PRESSURE RATE, 4 OR FEWER RUSHERS", "x_sub": "share of those dropbacks",
                "y_label": "SACK RATE, 4 OR FEWER RUSHERS", "y_sub": "share of those dropbacks",
                "med": [_med(pts, "x"), _med(pts, "y")], "quad": QUADS["four_man"],
                "line": {"slope": _r(sl), "intercept": _r(ic), "label": "league trend"}}
    if t.chart == "short_yd" and own == a:
        pts = _xy(t.extra["run_rate"], t.off)
        return {"type": "scatter", "pts": pts, "hl": [a], "fmt_x": "pct", "fmt_y": "pct",
                "x_label": "SHORT-YARDAGE RUN RATE", "x_sub": "% of 2nd & 1-6 / 3rd & 1-3 snaps that are runs",
                "y_label": "RUN SUCCESS RATE", "y_sub": "% of those runs with positive EPA",
                "med": [_med(pts, "x"), _med(pts, "y")], "quad": QUADS["short_yd"]}
    side_tab, hl = (t.off, a) if own == a else (t.deff, b)
    pts = sorted(_pts(side_tab), key=lambda p: -p["v"])
    return {"type": "bars", "pts": pts, "hl": [hl], "fmt": t.fmt, "med": _med(pts, "v"),
            "y_label": (t.label if own == a else f"{t.label} allowed").upper()}


def render(c, M, game):
    t = c["tpl"]
    l1, l2 = (_head_unit if t.kind == "unit" else _head_tend)(c, M)
    who = "offense and defense" if t.kind == "unit" else ("offense" if t.chooser == "off" else "defense")
    if t.chart == "bars":
        who = "offense" if c["owner"] == c["a"] else "defense"
    sub = f"Every {who}, {game['span']}."
    if c["clash"] > 1.0 and abs(c["edge"]) < 1.0:
        sub += " Strength on strength."
    own_tab = t.off if c["owner"] == c["a"] else t.deff
    return {"id": f"{t.id}:{c['a']}", "kind": "team", "phase": t.phase, "owner": c["owner"], "score": _r(c["score"], 3),
            "edge": _r(c["edge"], 3), "t1": l1, "t2": l2, "sub": sub, "chart": _chart(c, M),
            "source": " · ".join(t.sources), "note": f"{t.note} · {c['owner']}: n={_n(own_tab, c['owner'])} {t.n_label}"}


def key_line(c, team, M):
    t, a, b = c["tpl"], c["a"], c["b"]
    good = (c["edge"] >= 0) == (team == a)
    if team == a:
        phrase = t.keys[0] if good else t.keys[1]
        detail = (f"{M[a]['label']} ranks {ordinal(c['ra'])} in {t.label} ({fmt(_val(t.off, a), t.fmt)}). "
                  f"{poss(M[b]['label'])} defense ranks {ordinal(c['rb'])} ({fmt(_val(t.deff, b), t.fmt)} {t.def_word}).")
    else:
        phrase = t.keys[2] if good else t.keys[3]
        detail = (f"{poss(M[b]['label'])} defense ranks {ordinal(c['rb'])} in {t.label} ({fmt(_val(t.deff, b), t.fmt)} {t.def_word}). "
                  f"{M[a]['label']} ranks {ordinal(c['ra'])} ({fmt(_val(t.off, a), t.fmt)}).")
    return {"phrase": phrase, "detail": detail, "favorable": bool(good), "id": t.id}


# ---------- special templates ----------

def shell_card(sh, a, b, M, game):
    if not sh or not sh["shells"]:
        return None
    use = {s: _val(sh["use"][s], b) for s in sh["shells"]}
    use = {s: v for s, v in use.items() if not np.isnan(v)}
    if not use:
        return None
    s = max(use, key=use.get)
    za, zb = S.zscore(sh["off"][s], a), S.zscore(sh["def"][s], b)
    zf = S.zscore(sh["use"][s], b)
    if any(np.isnan(x) for x in (za, zb)):
        return None
    e = (za + zb) * float(np.clip(0.75 + 0.25 * (0 if np.isnan(zf) else zf), 0.25, 1.5))
    rf, nf = S.rank(sh["use"][s], b, 1), _count(sh["use"][s])
    A, B = M[a]["label"], M[b]["label"]
    va = _val(sh["off"][s], a)
    l1 = f"{B} plays {SHELL_NAME.get(s, s)} on {fmt(use[s], 'pct')} of throws."
    if rf <= 3:
        l1 = f"{B} plays {SHELL_NAME.get(s, s)} more than almost anyone."
    l2 = f"{A} carves it up: {fmt(va, 'epa')} EPA per attempt." if e > 0 else f"{A} manages {fmt(va, 'epa')} EPA per attempt against it."
    panels = []
    for x in sh["shells"][:4]:
        panels.append({"title": SHELL_NAME.get(x, x).upper(), "sub": f"{b} uses it {fmt(_val(sh['use'][x], b), 'pct')}",
                       "rows": [{"label": A, "team": a, "v": _r(_val(sh["off"][x], a))},
                                {"label": "League", "team": None, "v": _r(sh["league"].get(x))}]})
    owner = a if e >= 0 else b
    return {"id": f"shell:{a}", "kind": "team", "phase": "coverage", "owner": owner,
            "score": _r(abs(e) + (0.25 if rf in (1, nf) else 0), 3), "edge": _r(e, 3), "t1": l1, "t2": l2,
            "sub": f"{A} EPA per attempt by coverage shell, {game['span']}.",
            "chart": {"type": "splits", "fmt": "epa", "panels": panels},
            "source": f"{SRC_PBP} · {SRC_PART}", "note": f"Shrunk to league mean · {a}: n={_n(sh['off'][s], a)} vs {SHELL_NAME.get(s, s)}",
            "_key": {a: ("Beat " + SHELL_NAME.get(s, s) if e >= 0 else "Find answers vs " + SHELL_NAME.get(s, s),
                         f"{A} averages {fmt(va, 'epa')} EPA per attempt vs {SHELL_NAME.get(s, s)}; {B} plays it {fmt(use[s], 'pct')} of the time."),
                     b: ("Live in " + SHELL_NAME.get(s, s) if e < 0 else "Disguise the " + SHELL_NAME.get(s, s),
                         f"{B} plays {SHELL_NAME.get(s, s)} on {fmt(use[s], 'pct')} of throws; {A} averages {fmt(va, 'epa')} EPA against it.")}}


def gap_card(gp, a, b, M, game):
    best, be = None, 0.0
    for g in GAP_ORDER:
        za, zb = S.zscore(gp["off"][g], a), S.zscore(gp["def"][g], b)
        zf = S.zscore(gp["use"][g], a)
        if np.isnan(za) or np.isnan(zb):
            continue
        e = (za + zb) * float(np.clip(0.75 + 0.25 * (0 if np.isnan(zf) else zf), 0.25, 1.5))
        if abs(e) > abs(be):
            best, be = g, e
    if best is None:
        return None
    adj = max(abs(be) - GAP_MAX_PENALTY, 0.0)
    if adj == 0:
        return None
    A, B = M[a]["label"], M[b]["label"]
    va, vb = _val(gp["off"][best], a), _val(gp["def"][best], b)
    rb, nb = S.rank(gp["def"][best], b, -1), _count(gp["def"][best])
    if be >= 0:
        l1 = f"{A} can run {GAP_PHRASE[best]}."
        l2 = f"{B} allows {fmt(vb, 'epa')} EPA per run there, {rp(rb, nb)}."
    else:
        l1 = f"{B} walls off {GAP_PHRASE[best]}."
        l2 = f"{A} averages {fmt(va, 'epa')} EPA per run there."
    series = [{"team": a, "label": f"{A} offense", "vals": [_r(_val(gp['off'][g], a)) for g in GAP_ORDER]},
              {"team": b, "label": f"{B} defense allowed", "vals": [_r(_val(gp['def'][g], b)) for g in GAP_ORDER]}]
    return {"id": f"gap:{a}", "kind": "team", "phase": "rush", "owner": a if be >= 0 else b, "score": _r(adj, 3),
            "edge": _r(np.sign(be) * adj, 3), "t1": l1, "t2": l2, "sub": f"EPA per designed run by gap, {game['span']}.",
            "chart": {"type": "gaps", "fmt": "epa", "cats": GAP_ORDER, "series": series,
                      "league": [_r(gp["league"][g]) for g in GAP_ORDER], "y_label": "EPA PER RUN"},
            "source": SRC_PBP, "note": f"Shrunk to league mean · {a}: n={_n(gp['off'][best], a)} runs {GAP_PHRASE[best]}",
            "_key": {a: ("Run " + GAP_PHRASE[best] if be >= 0 else "Avoid running " + GAP_PHRASE[best],
                         f"{A} averages {fmt(va, 'epa')} EPA per run {GAP_PHRASE[best]}; {B} allows {fmt(vb, 'epa')} there."),
                     b: ("Own the " + GAP_PHRASE[best] + " gap" if be < 0 else "Seal " + GAP_PHRASE[best],
                         f"{B} allows {fmt(vb, 'epa')} EPA per run {GAP_PHRASE[best]}; {A} averages {fmt(va, 'epa')} there.")}}


def form_card(net, a, b, M, game):
    last = net["week"].max()
    g = net.groupby("team")
    season = g["net"].mean()
    l4 = net[net["week"] > last - 4].groupby("team")["net"].mean()
    diff = (l4 - season).dropna()
    z = (diff - diff.mean()) / diff.std()
    pick = max([a, b], key=lambda t: abs(z.get(t, 0)))
    zt = z.get(pick, 0)
    if abs(zt) < 1.0:
        return None
    T = M[pick]["label"]
    rank_l4 = int(l4.rank(ascending=False)[pick])
    l1 = (f"{T} is playing its best football." if zt > 0 and rank_l4 <= 5 else
          f"{T} is trending up." if zt > 0 else f"{T} is fading.")
    l2 = f"Net EPA per play: {season[pick]:+.2f} season, {l4[pick]:+.2f} last 4 weeks."
    weeks = sorted(net["week"].unique().tolist())
    series = []
    for t in (a, b):
        s = net[net["team"] == t].set_index("week")["net"].reindex(weeks)
        series.append({"team": t, "vals": [_r(v) for v in s.rolling(3, min_periods=1).mean()]})
    return {"id": f"form:{pick}", "kind": "team", "phase": "context", "owner": pick, "score": _r(0.7 * abs(zt), 3),
            "edge": None, "t1": l1, "t2": l2, "sub": f"Net EPA per play by week, 3-week rolling mean, {game['span']}.",
            "chart": {"type": "trend", "fmt": "epa", "weeks": weeks, "series": series, "y_label": "NET EPA PER PLAY"},
            "source": SRC_PBP, "note": "Offense EPA/play minus defense EPA/play allowed · garbage time removed"}


def luck_card(lk, a, b, M, game):
    if lk is None:
        return None
    z = (lk["luck"] - lk["luck"].mean()) / lk["luck"].std()
    pick = max([a, b], key=lambda t: abs(z.get(t, 0)))
    zt = z.get(pick, 0)
    if abs(zt) < 1.2:
        return None
    T, k = M[pick]["label"], lk.loc[pick, "luck"]
    if k > 0:
        l1, l2 = f"{T} has thrown {k:.0f} fewer INTs than expected.", "That kind of luck runs out."
    else:
        l1, l2 = f"{T} has thrown {-k:.0f} more INTs than expected.", "Expect fewer giveaways."
    pts = [{"team": t, "x": _r(r.worthy_rate), "y": _r(r.int_rate)} for t, r in lk.iterrows()]
    return {"id": f"luck:{pick}", "kind": "team", "phase": "context", "owner": pick, "score": _r(0.6 * abs(zt), 3),
            "edge": None, "t1": l1, "t2": l2, "sub": f"Every offense, {game['span']}. Line = league INT rate on INT-worthy throws.",
            "chart": {"type": "scatter", "pts": pts, "hl": [pick], "fmt_x": "pct1", "fmt_y": "pct1",
                      "x_label": "INTERCEPTION-WORTHY THROW RATE", "x_sub": "per attempt, FTN charting",
                      "y_label": "INTERCEPTION RATE", "y_sub": "per attempt",
                      "med": [_med(pts, "x"), _med(pts, "y")],
                      "line": {"slope": _r(lk.attrs["r"]), "intercept": 0, "label": "expected"}},
            "source": f"{SRC_PBP} · {SRC_FTN}", "note": f"All game states · {pick}: {int(lk.loc[pick, 'ints'])} INTs on {int(lk.loc[pick, 'worthy'])} INT-worthy throws"}


# ---------- selection ----------

def select(cards, lo, hi, teams):
    cards = sorted([c for c in cards if c], key=lambda c: -c["score"])
    out, per_phase, seen = [], {}, set()
    for c in cards:
        base = c["id"].split(":")[0]
        if base in seen or per_phase.get(c["phase"], 0) >= MAX_CARDS_PER_PHASE:
            continue
        if len(out) >= lo and c["score"] < SOFT_SCORE_FLOOR:
            break
        out.append(c)
        seen.add(base)
        per_phase[c["phase"]] = per_phase.get(c["phase"], 0) + 1
        if len(out) >= hi:
            break
    for t in teams:
        if out and not any(c["owner"] == t for c in out):
            bases = {x["id"].split(":")[0] for x in out}
            alt = next((c for c in cards if c["owner"] == t and c["id"].split(":")[0] not in bases
                        and c["score"] > 0.5), None)
            if alt:
                if len(out) < hi:
                    out.append(alt)
                else:
                    out[-1] = alt
    return out


def keys_for(team, cands, specials, M):
    rows = []
    for c in cands:
        if team in (c["a"], c["b"]):
            rows.append((abs(c["edge"]), c["id"], key_line(c, team, M)))
    for s in specials:
        if s and "_key" in s and team in s["_key"]:
            ph, det = s["_key"][team]
            fav = (s["owner"] == team)
            rows.append((abs(s["edge"] or 0), s["id"].split(":")[0], {"phrase": ph, "detail": det, "favorable": fav,
                                                                      "id": s["id"].split(":")[0]}))
    rows.sort(key=lambda r: -r[0])
    out, seen = [], set()
    for _, i, k in rows:
        if i in seen:
            continue
        seen.add(i)
        out.append(k)
        if len(out) == 3:
            break
    if out and not any(k["favorable"] for k in out):
        fav = next((k for e, i, k in rows if k["favorable"] and e > 0.5 and i not in {x["id"] for x in out}), None)
        if fav:
            out[-1] = fav
    return out
