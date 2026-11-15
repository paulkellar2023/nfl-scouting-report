"""Post-game recaps (did each key hold?) and the season track record (model vs. market)."""
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# template id -> (play filter on garbage-time-removed plays, column, min plays to grade)
GRADE = {
    "pass_epa": (lambda d: d["dropback"], "epa", 8),
    "rush_epa": (lambda d: d["designed_run"], "epa", 5),
    "explosive": (lambda d: d["dropback"] | d["designed_run"], "explosive", 15),
    "early_down": (lambda d: d["dropback"] & d["early"], "epa", 5),
    "depth": (lambda d: d["deep"] == 1, "epa", 2),
    "yacoe": (lambda d: d["yacoe"].notna(), "yacoe", 4),
    "pressure": (lambda d: d["dropback"], "pressure", 8),
    "stuff": (lambda d: d["designed_run"], "stuffed", 5),
    "short_yd": (lambda d: d["short_yd"] & d["designed_run"], "success", 2),
    "play_action": (lambda d: d["dropback"] & (d.get("pa", 0) == 1), "epa", 3),
    "motion": (lambda d: d["dropback"] & (d.get("motion", 0) == 1), "epa", 3),
    "blitz": (lambda d: d["dropback"] & (d.get("blitz", 0) == 1), "epa", 3),
    "four_man": (lambda d: d["dropback"] & (d.get("rushers", 9) <= 4), "pressure", 5),
    "man_zone": (lambda d: d["attempt"] & (d.get("man", 0) == 1), "epa", 3),
}


def _rz(plays):
    dr = plays.groupby(["game_id", "posteam", "fixed_drive"], observed=True).agg(
        rz=("yardline_100", lambda s: (s <= 20).any()), res=("fixed_drive_result", "first")).reset_index()
    dr = dr[dr["rz"]]
    return dr.assign(td=(dr["res"] == "Touchdown").astype(float))


def baselines(plays):
    e = plays[plays["eff"]]
    out = {}
    for tid, (f, col, _) in GRADE.items():
        try:
            v = e.loc[f(e), col].astype(float).dropna()
        except KeyError:
            continue
        if len(v):
            out[tid] = float(v.mean())
    out["red_zone"] = float(_rz(plays)["td"].mean())
    return out


def _game_value(tid, gp, off):
    if tid == "red_zone":
        d = _rz(gp)
        d = d[d["posteam"] == off]
        return (float(d["td"].mean()) if len(d) else np.nan), len(d), 1
    f, col, k = GRADE[tid]
    e = gp[gp["eff"] & (gp["posteam"] == off)]
    v = e.loc[f(e), col].astype(float).dropna()
    return (float(v.mean()) if len(v) else np.nan), len(v), k


def _side(k, info):
    if k.get("side"):
        return k["side"]
    if info:
        if k["phrase"] in info["keys"][:2]:
            return "off"
        if k["phrase"] in info["keys"][2:]:
            return "def"
    return None


def _pick(p_home, home, away):
    if p_home is None:
        return None
    return {"team": home if p_home >= 0.5 else away, "p": round(max(p_home, 1 - p_home), 3)}


def grade_doc(doc, g, gp, base, tinfo):
    h, a = doc["home"], doc["away"]
    hs, as_ = int(g["home_score"]), int(g["away_score"])
    win = h if hs > as_ else a if as_ > hs else None
    rec = {"final": {h: hs, a: as_}, "winner": win, "keys": {}, "keys_won": {}}
    m = doc.get("model") or {}
    for name, p in (("model", m.get("p_home")), ("market", (m.get("market") or {}).get("p_home"))):
        pk = _pick(p, h, a)
        if pk:
            pk["ok"] = None if win is None else pk["team"] == win
        rec[name] = pk
    for team, keys in doc.get("keys", {}).items():
        opp = h if team == a else a
        rows = []
        for k in keys:
            tid, info = k.get("id"), tinfo.get(k.get("id"))
            side = _side(k, info)
            if info is None or side is None or (tid not in GRADE and tid != "red_zone"):
                rows.append({"status": "na"})
                continue
            off = team if side == "off" else opp
            v, n, need = _game_value(tid, gp, off)
            row = {"label": info["label"], "fmt": info["fmt"], "off": off, "n": n,
                   "value": None if np.isnan(v) else round(v, 4), "avg": round(base.get(tid, np.nan), 4)}
            if n < need or np.isnan(v) or tid not in base:
                row["status"] = "low"
            else:
                off_won = info["sign"] * (v - base[tid]) > 0
                row["status"] = "won" if off_won == (side == "off") else "lost"
            rows.append(row)
        rec["keys"][team] = rows
        graded = [r for r in rows if r["status"] in ("won", "lost")]
        rec["keys_won"][team] = [sum(r["status"] == "won" for r in graded), len(graded)]
    return rec


def recap_text(rec, M):
    h_a = list(rec["final"].items())
    (t1, s1), (t2, s2) = sorted(h_a, key=lambda x: -x[1])
    first = f"{M[t1]['nick']} {s1}, {M[t2]['nick']} {s2}." if s1 != s2 else f"Tie, {s1}-{s2}."
    parts = [first]
    md = rec.get("model")
    if md and md["ok"] is not None:
        parts.append(f"The model had the {M[md['team']]['nick']} at {round(md['p'] * 100)}% ({'hit' if md['ok'] else 'miss'}).")
    kw = [f"{M[t]['nick']} won {w} of {n} keys" for t, (w, n) in rec["keys_won"].items() if n]
    if kw:
        parts.append(" · ".join(kw) + ".")
    return " ".join(parts)


def grade_weeks(site, season, target_week, sched, plays, tpls, M, synthetic):
    """Add a recap to every finished game in earlier weeks that does not have one yet. Returns count graded."""
    tinfo = {t.id: {"keys": t.keys, "label": t.extra.get("grade_label", t.label), "fmt": t.fmt, "sign": t.sign} for t in tpls}
    base = baselines(plays)
    s = sched.set_index("game_id")
    n = 0
    for wdir in sorted((Path(site) / "data" / str(season)).glob("wk*")):
        gj = wdir / "games.json"
        if not wdir.name[2:].isdigit() or int(wdir.name[2:]) >= target_week or not gj.exists():
            continue
        board = json.loads(gj.read_text())
        if bool(board.get("synthetic")) != bool(synthetic) or board.get("projected"):
            continue
        changed = False
        for tile in board["games"]:
            f = wdir / f"{tile['id']}.json"
            if tile.get("final") or not f.exists() or tile["id"] not in s.index:
                continue
            g = s.loc[tile["id"]]
            if pd.isna(g.get("result")) or pd.isna(g.get("home_score")):
                continue
            gp = plays[plays["game_id"] == tile["id"]]
            if not len(gp):
                continue  # play-by-play not published yet; try next build
            doc = json.loads(f.read_text())
            rec = grade_doc(doc, g, gp, base, tinfo)
            rec["text"] = recap_text(rec, M)
            doc["recap"] = rec
            f.write_text(json.dumps(doc, separators=(",", ":")))
            tile["final"] = rec["final"]
            tile["model_ok"] = (rec.get("model") or {}).get("ok")
            changed, n = True, n + 1
        if changed:
            gj.write_text(json.dumps(board, separators=(",", ":")))
    return n


def _score(rows, pk):
    r = [x for x in rows if x.get(pk) is not None and x["y"] is not None]
    if not r:
        return None
    p = np.clip(np.array([x[pk] for x in r], float), 1e-6, 1 - 1e-6)
    y = np.array([x["y"] for x in r], float)
    return {"n": len(r), "brier": round(float(np.mean((p - y) ** 2)), 4),
            "ll": round(float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), 4),
            "acc": round(float(np.mean((p > 0.5) == (y == 1))), 3)}


def _cum(rows):
    out, acc = [], []
    for w in sorted({x["week"] for x in rows}):
        acc += [x for x in rows if x["week"] == w and x.get("pm") is not None]
        m, k = _score(acc, "p"), _score(acc, "pm")
        if m and k:
            out.append({"week": w, "model": m["brier"], "market": k["brier"], "n": m["n"]})
    return out


def build(site, season, week, mmeta, synthetic):
    """Season track record: published (graded) picks plus a walk-forward run over every game this season."""
    pub = []
    for wdir in sorted((Path(site) / "data" / str(season)).glob("wk*")):
        gj = wdir / "games.json"
        if not gj.exists() or not wdir.name[2:].isdigit():
            continue
        board = json.loads(gj.read_text())
        if bool(board.get("synthetic")) != bool(synthetic) or board.get("projected"):
            continue
        for tile in board["games"]:
            if not tile.get("final") or not tile.get("model"):
                continue
            h, a = tile["home"], tile["away"]
            hs, as_ = tile["final"][h], tile["final"][a]
            if hs == as_:
                continue
            pub.append({"id": tile["id"], "week": board["week"], "home": h, "away": a,
                        "p": tile["model"]["p_home"], "pm": tile["model"].get("mkt"), "pf": tile["model"].get("fpi"),
                        "final": tile["final"], "y": float(hs > as_)})
    walk = []
    for r in (mmeta or {}).get("season_walk", []):
        if r["margin"] != 0:
            walk.append({**r, "y": float(r["margin"] > 0)})
    pub_m = [x for x in pub if x.get("pm") is not None]
    pub_3 = [x for x in pub_m if x.get("pf") is not None]
    walk_m = [x for x in walk if x.get("pm") is not None]
    out = {"season": season, "week": week,
           "published": {"model": _score(pub_m, "p"), "market": _score(pub_m, "pm"), "games": pub[::-1], "cum": _cum(pub)},
           "three": {"model": _score(pub_3, "p"), "market": _score(pub_3, "pm"), "fpi": _score(pub_3, "pf")},
           "walk": {"model": _score(walk_m, "p"), "market": _score(walk_m, "pm"), "cum": _cum(walk)},
           "backtest": (mmeta or {}).get("backtest", []), "calib": (mmeta or {}).get("calib", [])}
    p = Path(site) / "data" / str(season) / "record.json"
    p.write_text(json.dumps(out, separators=(",", ":")))
    return len(pub), len(walk)
