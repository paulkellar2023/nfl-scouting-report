"""ESPN FPI matchup predictor (home win %) from ESPN's public, undocumented game summary endpoint.
Optional: any failure returns None and the site shows "-"."""
import logging

import pandas as pd

log = logging.getLogger(__name__)
URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary"


def fpi_home(espn_id, home_abbr=None):
    if espn_id is None or pd.isna(espn_id):
        return None
    try:
        import requests

        r = requests.get(URL, params={"event": str(int(float(espn_id)))}, timeout=10)
        r.raise_for_status()
        j = r.json()
        pr = j.get("predictor") or {}
        ht = pr.get("homeTeam") or {}
        v = ht.get("gameProjection")
        if v is None:
            return None
        p = float(v) / 100
        # sanity check: predictor.homeTeam should be the home competitor
        comp = ((j.get("header") or {}).get("competitions") or [{}])[0].get("competitors", [])
        home = next((c for c in comp if c.get("homeAway") == "home"), None)
        if home and ht.get("id") and str(home.get("id")) != str(ht.get("id")):
            p = 1 - p
        return round(p, 4) if 0 < p < 1 else None
    except Exception as e:
        log.warning("fpi: event %s failed: %s", espn_id, e)
        return None
