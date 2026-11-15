import logging

import pandas as pd

from .teams_meta import TEAMS, espn_logo

log = logging.getLogger(__name__)


def _pd(x):
    return x.to_pandas() if hasattr(x, "to_pandas") else x


def _try(name, fn):
    try:
        df = _pd(fn())
        log.info("loaded %s: %d rows", name, len(df))
        return df
    except Exception as e:  # source may be missing for the season
        log.warning("could not load %s: %s", name, e)
        return None


def load(season):
    import nflreadpy as nfl

    pbp = _try("pbp", lambda: nfl.load_pbp([season]))
    sched = _try("schedules", lambda: nfl.load_schedules([season]))
    if pbp is None or sched is None:
        raise SystemExit("pbp and schedules are required")
    teams = _try("teams", nfl.load_teams)
    if teams is None:
        teams = pd.DataFrame([{"team_abbr": t, "team_name": v[0], "team_nick": v[1], "team_conf": v[2],
                               "team_division": v[3], "team_color": v[4], "team_color2": v[5],
                               "team_logo_espn": espn_logo(t)} for t, v in TEAMS.items()])
    return {
        "pbp": pbp,
        "sched": sched,
        "teams": teams,
        "rosters": _try("rosters", lambda: nfl.load_rosters([season])),
        "part": _try("participation", lambda: nfl.load_participation([season])),
        "ftn": _try("ftn_charting", lambda: nfl.load_ftn_charting([season])),
        "x": {**{f"ngs_{k[:4] if k != 'receiving' else 'rec'}": _try(f"nextgen {k}", lambda k=k: nfl.load_nextgen_stats([season], stat_type=k))
                 for k in ("passing", "rushing", "receiving")},
              **{f"pfr_{k}": _try(f"pfr {k}", lambda k=k: nfl.load_pfr_advstats([season], stat_type=k, summary_level="week"))
                 for k in ("pass", "rush", "rec", "def")}},
        "synthetic": False,
    }


MODEL_COLS = ["season", "season_type", "week", "game_id", "posteam", "defteam", "home_team", "play_type", "epa",
              "pass", "qb_dropback", "wp", "passer_player_id", "rusher_player_id"]


def load_history(season, first, cur_pbp, cache_dir):
    """Extra seasons for the model. Skips pbp for seasons whose feature cache exists."""
    import nflreadpy as nfl

    need = [s for s in range(first, season) if not (cache_dir / f"features_{s}.csv").exists()]
    pbp_seasons = sorted({x for s in need for x in (s - 1, s)} | {season - 1})
    frames = [cur_pbp[[c for c in MODEL_COLS if c in cur_pbp.columns]]]
    if pbp_seasons:
        p = nfl.load_pbp(pbp_seasons)
        cols = [c for c in MODEL_COLS if c in p.columns]
        frames.append(_pd(p.select(cols) if type(p).__module__.startswith("polars") else p[cols]))
        log.info("history pbp seasons %s", pbp_seasons)
    inj_seasons = sorted(set(need) | {season})
    return {
        "pbp": pd.concat(frames, ignore_index=True),
        "sched": _try("schedules (history)", lambda: nfl.load_schedules(list(range(first - 1, season + 1)))),
        "injuries": _try("injuries", lambda: nfl.load_injuries(inj_seasons)),
        "snaps": _try("snap_counts", lambda: nfl.load_snap_counts(inj_seasons)),
        "players": _try("players", nfl.load_players),
        "synthetic": False,
    }
