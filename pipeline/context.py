import numpy as np
import pandas as pd

from .config import BG_HEX
from .teams_meta import espn_logo


def _rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def _lum(h):
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in _rgb(h)]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _contrast(a, b):
    la, lb = sorted([_lum(a), _lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _mix_white(h, t):
    r = [x + (1 - x) * t for x in _rgb(h)]
    return "#" + "".join(f"{int(round(v * 255)):02X}" for v in r)


def accent(c1, c2):
    cands = [c for c in (c1, c2) if isinstance(c, str) and c.startswith("#") and len(c) == 7]
    best = max(cands, key=lambda c: _contrast(c, BG_HEX)) if cands else "#BBBBBB"
    t = 0.0
    while _contrast(_mix_white(best, t), BG_HEX) < 4.5 and t < 1:
        t += 0.05
    return _mix_white(best, t)


def possessive(name):
    return name + ("'" if name.endswith("s") else "'s")


def team_meta(teams_df, active):
    out = {}
    t = teams_df.drop_duplicates("team_abbr").set_index("team_abbr")
    for ab in active:
        r = t.loc[ab]
        city = r["team_name"].replace(r["team_nick"], "").strip()
        plural = city in ("Los Angeles", "New York", "")
        label = f"the {r['team_nick']}" if plural else city
        out[ab] = {"abbr": ab, "name": r["team_name"], "nick": r["team_nick"], "label": label, "plural": plural,
                   "conf": r.get("team_conf"), "division": r.get("team_division"),
                   "color": r.get("team_color"), "accent": accent(r.get("team_color"), r.get("team_color2")),
                   "logo_url": r.get("team_logo_espn") if isinstance(r.get("team_logo_espn"), str) else espn_logo(ab), "logo": f"assets/logos/{ab}.png"}
    return out


def player_context(plays, rosters, sched, target_week):
    names, heads = {}, {}
    for c_id, c_nm in [("passer_player_id", "passer_player_name"), ("rusher_player_id", "rusher_player_name"),
                       ("receiver_player_id", "receiver_player_name")]:
        s = plays[[c_id, c_nm]].dropna().drop_duplicates(c_id)
        names.update(dict(zip(s[c_id], s[c_nm])))
    if rosters is not None and len(rosters) and "gsis_id" in rosters.columns:
        r = rosters.dropna(subset=["gsis_id"]).drop_duplicates("gsis_id", keep="last")
        nm = "full_name" if "full_name" in r.columns else "display_name"
        names.update({k: v for k, v in zip(r["gsis_id"], r[nm]) if isinstance(v, str)})
        if "headshot_url" in r.columns:
            heads = {k: v for k, v in zip(r["gsis_id"], r["headshot_url"]) if isinstance(v, str) and v}

    last_wk = plays.groupby("posteam")["week"].max()
    recent = plays[plays["week"] == plays["posteam"].map(last_wk)]
    qb_last = recent[recent["dropback"] & recent["qb_id"].notna()].groupby(["posteam", "qb_id"]).size()
    starters = qb_last.reset_index().sort_values(0).groupby("posteam").tail(1).set_index("posteam")["qb_id"].to_dict()
    tw = sched[(sched["week"] == target_week)]
    for col_t, col_q in [("home_team", "home_qb_id"), ("away_team", "away_qb_id")]:
        if col_q in tw.columns:
            for t, q in zip(tw[col_t], tw[col_q]):
                if isinstance(q, str) and q:
                    starters[t] = q

    w3 = plays[plays["week"] >= plays["posteam"].map(last_wk) - 2]
    rb = w3[w3["designed_run"] & w3["rusher_player_id"].notna()]
    rb = rb[~rb["rusher_player_id"].isin(set(starters.values()))]
    lead_rb = rb.groupby(["posteam", "rusher_player_id"])["w"].sum().reset_index().sort_values("w") \
        .groupby("posteam").tail(1).set_index("posteam")["rusher_player_id"].to_dict()
    tg = plays[plays["attempt"] & plays["receiver_player_id"].notna()]
    tg = tg.groupby(["posteam", "receiver_player_id"])["w"].sum().reset_index().sort_values("w", ascending=False)
    top_tgt = tg.groupby("posteam").head(2).groupby("posteam")["receiver_player_id"].apply(list).to_dict()
    p_team = pd.concat([
        plays[["passer_player_id", "posteam", "week"]].rename(columns={"passer_player_id": "pid"}),
        plays[["rusher_player_id", "posteam", "week"]].rename(columns={"rusher_player_id": "pid"}),
        plays[["receiver_player_id", "posteam", "week"]].rename(columns={"receiver_player_id": "pid"}),
    ]).dropna().sort_values("week").drop_duplicates("pid", keep="last").set_index("pid")["posteam"].to_dict()
    return {"names": names, "heads": heads, "qb": starters, "rb": lead_rb, "tgt": top_tgt, "team": p_team}


def short_name(full):
    if not isinstance(full, str):
        return "?"
    parts = full.replace(".", ". ").split()
    return parts[-1] if parts else full
