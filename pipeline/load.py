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
        "synthetic": False,
    }
