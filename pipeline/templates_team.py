"""Team-level stat templates. Each template pairs an offensive measure with the same
measure allowed by defenses. 'tendency' templates add a usage table from the side that
chooses the action (offense for play action, defense for blitz)."""
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from . import stats as S
from .clean import GAP_ORDER

SRC_PBP = "NFLVERSE PLAY-BY-PLAY"
SRC_FTN = "FTN CHARTING VIA NFLVERSE"
SRC_PART = "NFLVERSE PARTICIPATION"
SRC_PFR = "PRO FOOTBALL REFERENCE VIA NFLVERSE"


@dataclass
class Tpl:
    id: str
    phase: str
    kind: str                      # unit | tendency
    label: str                     # metric name used in keys and axis
    fmt: str                       # epa | pct | yds
    sign: int                      # +1 if higher value = better for offense
    off: pd.DataFrame
    deff: pd.DataFrame
    unit_off: str
    unit_def: str
    keys: tuple                    # (off exploit, off survive, def exploit, def survive)
    chart: str
    n_label: str = "plays"
    freq: Optional[pd.DataFrame] = None
    chooser: str = "off"
    freq_label: str = ""
    freq_fmt: str = "pct"
    more: str = ""
    verb: str = ""
    sources: tuple = (SRC_PBP,)
    note: str = "Garbage time removed"
    def_word: str = "allowed"
    weight: float = 1.0
    extra: dict = field(default_factory=dict)


def _eb_pair(sub, y, min_n):
    return S.eb(S.agg(sub, "posteam", y), min_n), S.eb(S.agg(sub, "defteam", y), min_n)


def _adj_pair(sub, y, min_n, teams, off_key="posteam"):
    o, d = S.opp_adjust(sub, y, off_key=off_key)
    o = o[o.index.isin(teams)].copy()
    d = d[d.index.isin(teams)].copy()
    o.loc[o["n"] < min_n, "value_s"] = np.nan
    d.loc[d["n"] < min_n, "value_s"] = np.nan
    return o, d


def build(plays, flags, starters, teams, X=None):
    X = X or {}
    e = plays[plays["eff"]].copy()
    e["pkey"] = np.where(e["qb_id"].isin(set(starters.values())) | ~e["dropback"], e["posteam"], e["posteam"] + "~alt")
    nt = plays[plays["neutral"]]
    db, att, ru = e[e["dropback"]], e[e["attempt"]], e[e["designed_run"]]
    T = []

    o, d = _adj_pair(db, "epa", 100, teams, off_key="pkey")
    # A starter with too few dropbacks has no rating: fall back to the team's rating with every QB.
    o = o.reindex(sorted(set(o.index) | set(teams)))
    miss = [t for t in teams if pd.isna(o.loc[t, "value_s"])]
    pass_note = "Opponent-adjusted · projected starting QB only · garbage time removed"
    if miss:
        ot, _ = _adj_pair(db, "epa", 100, teams)
        for c in ot.columns:
            if c in o.columns:
                o.loc[miss, c] = ot.reindex(miss)[c].values
        pass_note += f" · team rating (all QBs) for {', '.join(miss)}"
    T.append(Tpl("pass_epa", "pass", "unit", "EPA per dropback", "epa", 1, o, d, "passing offense",
                 "pass defense", ("Win through the air", "Stay efficient through the air",
                                  "Make them throw", "Limit the passing game"), "duel", "dropbacks",
                 note=pass_note))

    o, d = _adj_pair(ru, "epa", 80, teams)
    T.append(Tpl("rush_epa", "rush", "unit", "EPA per designed run", "epa", 1, o, d, "run game",
                 "run defense", ("Lean on the run", "Keep the run game honest",
                                 "Make them one-dimensional", "Stop the run"), "duel", "runs",
                 note="Opponent-adjusted · designed runs · garbage time removed"))

    o, d = _eb_pair(e, "explosive", 250)
    T.append(Tpl("explosive", "explosive", "unit", "explosive play rate", "pct1", 1, o, d,
                 "big-play offense", "big-play defense", ("Hunt explosives", "Find a chunk play",
                                                          "Keep everything in front", "Limit chunk plays"),
                 "duel", "plays", note="Explosive = 20+ yd dropback or 10+ yd run · shrunk to league mean"))

    nt_e = nt[nt["early"]].copy()
    nt_e["proe"] = nt_e["is_pass"] - nt_e["xpass"] if nt_e["xpass"].notna().mean() > 0.5 else nt_e["is_pass"]
    fq = S.eb(S.agg(nt_e, "posteam", "proe"), 80)
    o, d = _eb_pair(db[db["early"]], "epa", 80)
    T.append(Tpl("early_down", "pass", "tendency", "early-down EPA per dropback", "epa", 1, o, d,
                 "early-down passing", "early-down pass defense",
                 ("Throw early", "Stay balanced early", "Win early downs", "Survive early-down passing"),
                 "scatter_off", "dropbacks", freq=fq, chooser="off", freq_label="early-down pass rate over expected",
                 freq_fmt="pct_pm", more="throws more on early downs", verb="throws early",
                 note="Neutral script for pass rate · garbage time removed for EPA"))

    team_adot = att.groupby("posteam")["air_yards"].mean()
    a2 = att.copy()
    a2["adot_dev"] = a2["air_yards"] - a2["posteam"].map(team_adot)
    deep = att[att["deep"] == 1]
    o, d = _eb_pair(deep, "epa", 25)
    T.append(Tpl("depth", "pass", "tendency", "EPA per deep attempt", "epa", 1, o, d, "deep passing",
                 "deep coverage", ("Take shots downfield", "Find the deep ball", "Keep a lid on it",
                                   "Don't give up the deep ball"),
                 "scatter_depth", "deep attempts", freq=S.eb(S.agg(att, "posteam", "deep"), 100),
                 chooser="off", freq_label="deep-attempt rate", more="throws deep more",
                 verb="throws deep", note="Deep = 15+ air yards · garbage time removed",
                 extra={"adot_dev": S.eb(S.agg(a2, "defteam", "adot_dev"), 100),
                        "epa_att_def": S.eb(S.agg(att, "defteam", "epa"), 100)}))

    comp = att[att["yacoe"].notna()]
    o, d = _eb_pair(comp, "yacoe", 60)
    T.append(Tpl("yacoe", "pass", "unit", "YAC over expected per catch", "yds", 1, o, d, "YAC game",
                 "tackling in space", ("Win after the catch", "Turn short throws into gains",
                                       "Tackle in space", "Rally to the catch"),
                 "scatter_yac", "catches", note="YAC over expected = YAC minus nflverse xYAC",
                 extra={"adot": S.eb(S.agg(att, "posteam", "air_yards"), 100),
                        "adot_dev": S.eb(S.agg(a2, "defteam", "adot_dev"), 100)}))

    plab = "pressure rate" if flags["pressure"] == "participation" else "QB hit + sack rate"
    psrc = (SRC_PBP, SRC_PART) if flags["pressure"] == "participation" else (SRC_PBP,)
    o, d = _eb_pair(db, "pressure", 100)
    pnote, pn, pextra, plab_t, psrc_t = "Shrunk to league mean · garbage time removed", "dropbacks", {}, plab, psrc
    if "press_off" in X and flags["pressure"] != "participation":
        o = X["press_off"][X["press_off"].index.isin(teams)]
        d = X["press_def"][X["press_def"].index.isin(teams)]
        pnote, pn, plab_t, psrc_t = "Charted pressures per dropback · all game states · shrunk to league mean", "games", "pressure rate", (SRC_PBP, SRC_PFR)
        pextra = {"grade_label": "QB hit + sack rate"}
    T.append(Tpl("pressure", "pressure", "unit", plab_t, "pct", -1, o, d, "pass protection", "pass rush",
                 ("Keep the pocket clean", "Protect the quarterback", "Win up front", "Find a way to get home"),
                 "duel", pn, sources=psrc_t, note=pnote, def_word="generated", extra=pextra))
    if "tackle_off" in X:
        T.append(Tpl("tackling", "tackling", "unit", "broken tackles per touch", "pct1", 1,
                     X["tackle_off"][X["tackle_off"].index.isin(teams)], X["tackle_def"][X["tackle_def"].index.isin(teams)],
                     "tackle-breaking offense", "tackling defense",
                     ("Break tackles", "Fight for extra yards", "Wrap up", "Tackle in space"), "duel", "games",
                     sources=(SRC_PFR,), def_word="missed",
                     note="Broken tackles per run or catch vs. missed tackles per opponent run or catch · all game states · shrunk"))

    o, d = _eb_pair(ru, "stuffed", 80)
    T.append(Tpl("stuff", "rush", "unit", "stuff rate", "pct", -1, o, d, "run blocking", "run front",
                 ("Win at the line", "Stay ahead of the chains", "Win at the point of attack", "Fit the run gaps"),
                 "duel", "runs", note="Stuff = designed run for 0 or fewer yards", def_word="generated"))

    sy = e[e["short_yd"]].copy()
    sy["is_run"] = 1 - sy["is_pass"]
    o, d = _eb_pair(sy[sy["designed_run"]], "success", 12)
    T.append(Tpl("short_yd", "situational", "unit", "short-yardage run success", "pct", 1, o, d,
                 "short-yardage run game", "short-yardage defense",
                 ("Run it in short yardage", "Convert the short ones", "Win short yardage", "Hold up in short yardage"),
                 "short_yd", "short-yardage runs", note="Short yardage = 2nd & 1-6 and 3rd & 1-3",
                 extra={"run_rate": S.eb(S.agg(sy, "posteam", "is_run"), 15)}))

    dr = plays.groupby(["game_id", "posteam", "defteam", "fixed_drive"], observed=True).agg(
        rz=("yardline_100", lambda s: (s <= 20).any()), res=("fixed_drive_result", "first"), w=("w", "first")).reset_index()
    dr = dr[dr["rz"]].copy()
    dr["td"] = (dr["res"] == "Touchdown").astype(float)
    o, d = _eb_pair(dr, "td", 10)
    T.append(Tpl("red_zone", "situational", "unit", "red-zone TD rate", "pct", 1, o, d, "red-zone offense",
                 "red-zone defense", ("Finish drives", "Turn trips into touchdowns", "Hold them to field goals",
                                      "Tighten up in the red zone"), "bars", "red-zone trips",
                 note="Per drive reaching the 20 · all game states"))

    if flags["ftn"]:
        for col, tid, lab, uo, ud, more, verb, keys in [
            ("pa", "play_action", "EPA per play-action dropback", "play-action game", "defense vs play action",
             "uses more play action", "uses play action",
             ("Lean on play action", "Use play action to open things up", "Stay disciplined vs play action",
              "Don't bite on play action")),
            ("motion", "motion", "EPA per dropback with motion", "motion passing game", "defense vs motion",
             "uses more pre-snap motion", "uses motion",
             ("Move people pre-snap", "Use motion to create leverage", "Stay sound vs motion",
              "Communicate vs motion"))]:
            o, d = _eb_pair(db[db[col] == 1], "epa", 25)
            T.append(Tpl(tid, "pass", "tendency", lab, "epa", 1, o, d, uo, ud,
                         keys, "scatter_off", "dropbacks", freq=S.eb(S.agg(db, "posteam", col), 100),
                         chooser="off", freq_label=f"{tid.replace('_', ' ')} rate", more=more, verb=verb,
                         sources=(SRC_PBP, SRC_FTN)))
        o, d = _eb_pair(db[db["blitz"] == 1], "epa", 25)
        T.append(Tpl("blitz", "pressure", "tendency", "EPA per dropback vs blitz", "epa", 1, o, d,
                     "offense vs the blitz", "blitz package", ("Punish the blitz", "Beat the blitz", "Bring pressure",
                                                       "Pick blitz spots carefully"),
                     "scatter_def", "dropbacks", freq=S.eb(S.agg(db, "defteam", "blitz"), 100), chooser="def",
                     freq_label="blitz rate", more="blitzes more", verb="blitzes", sources=(SRC_PBP, SRC_FTN),
                     note="Blitz = 1+ blitzer per FTN charting"))
        four = db[db["rushers"] <= 4]
        o, d = _eb_pair(four, "pressure", 80)
        T.append(Tpl("four_man", "pressure", "unit", f"{plab} vs 4 or fewer rushers", "pct", -1, o, d,
                     "protection vs a standard rush", "four-man rush",
                     ("Hold up vs four", "Survive the four-man rush", "Get home with four", "Generate a rush without blitzing"),
                     "four_man", "dropbacks", sources=(SRC_PBP, SRC_FTN) + psrc[1:], def_word="generated",
                     extra={"sack4": S.eb(S.agg(four, "defteam", "sack"), 80)}))

    if flags["coverage"]:
        o, d = _eb_pair(att[att["man"] == 1], "epa", 30)
        T.append(Tpl("man_zone", "coverage", "tendency", "EPA per attempt vs man", "epa", 1, o, d,
                     "offense vs man", "man coverage", ("Beat man coverage", "Win one-on-one",
                                                        "Lock them up in man", "Mix up the coverage"),
                     "scatter_mz", "attempts", freq=S.eb(S.agg(att, "defteam", "man"), 100), chooser="def",
                     freq_label="man coverage rate", more="plays more man coverage", verb="plays man",
                     sources=(SRC_PBP, SRC_PART),
                     extra={"zone": S.eb(S.agg(att[att["man"] == 0], "posteam", "epa"), 30)}))
    return T


def shell_tables(plays):
    att = plays[plays["eff"] & plays["attempt"] & plays["shell"].notna()] if "shell" in plays.columns else None
    if att is None or not len(att):
        return None
    top = att["shell"].value_counts()
    shells = [s for s in top.index[:5] if top[s] >= 300]
    out = {"shells": shells, "off": {}, "def": {}, "use": {}}
    for s in shells:
        sub = att[att["shell"] == s]
        out["off"][s], out["def"][s] = _eb_pair(sub, "epa", 20)
        a2 = att.assign(is_s=(att["shell"] == s).astype(float))
        out["use"][s] = S.eb(S.agg(a2, "defteam", "is_s"), 100)
    out["league"] = att.groupby("shell")["epa"].mean().to_dict()
    return out


def gap_tables(plays):
    ru = plays[plays["eff"] & plays["designed_run"] & plays["gap"].notna()]
    out = {"off": {}, "def": {}, "use": {}}
    for g in GAP_ORDER:
        sub = ru[ru["gap"] == g]
        out["off"][g], out["def"][g] = _eb_pair(sub, "epa", 15)
        a2 = ru.assign(is_g=(ru["gap"] == g).astype(float))
        out["use"][g] = S.eb(S.agg(a2, "posteam", "is_g"), 60)
    out["league"] = ru.groupby("gap")["epa"].mean().reindex(GAP_ORDER).fillna(0).to_dict()
    return out


def form_tables(plays):
    e = plays[plays["eff"]]
    off = e.groupby(["posteam", "week"])["epa"].mean().rename("off")
    de = e.groupby(["defteam", "week"])["epa"].mean().rename("def")
    off.index.names = de.index.names = ["team", "week"]
    net = pd.concat([off, de], axis=1).dropna()
    net["net"] = net["off"] - net["def"]
    return net.reset_index()


def luck_tables(plays):
    db = plays[plays["attempt"]].copy()
    if "is_interception_worthy" not in db.columns:
        return None
    db["worthy"] = ((db["is_interception_worthy"] == 1) | (db["interception"] == 1)).astype(float)
    g = db.groupby("posteam").agg(att=("epa", "size"), ints=("interception", "sum"), worthy=("worthy", "sum"))
    r = g["ints"].sum() / max(g["worthy"].sum(), 1)
    g["exp_ints"] = g["worthy"] * r
    g["luck"] = (g["exp_ints"] - g["ints"])
    g["int_rate"] = g["ints"] / g["att"]
    g["worthy_rate"] = g["worthy"] / g["att"]
    g.attrs["r"] = r
    return g
