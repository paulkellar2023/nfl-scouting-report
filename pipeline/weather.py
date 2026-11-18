"""Kickoff weather forecasts from Open-Meteo (free, no key). Only for games 0-15 days out; indoor games get no fetch."""
import datetime as dt
import logging

from . import health

log = logging.getLogger(__name__)
API = "https://api.open-meteo.com/v1/forecast"
SRC = "Open-Meteo forecast"
DAYS_AHEAD = 15

# Home stadiums: (lat, lon, indoor). Indoor = fixed dome or a roof that is usually closed. nflverse `roof` wins when set.
HOME = {
    "ARI": (33.528, -112.263, True), "ATL": (33.755, -84.401, True), "BAL": (39.278, -76.623, False),
    "BUF": (42.774, -78.787, False), "CAR": (35.226, -80.853, False), "CHI": (41.862, -87.617, False),
    "CIN": (39.095, -84.516, False), "CLE": (41.506, -81.699, False), "DAL": (32.748, -97.093, True),
    "DEN": (39.744, -105.020, False), "DET": (42.340, -83.046, True), "GB": (44.501, -88.062, False),
    "HOU": (29.685, -95.411, True), "IND": (39.760, -86.164, True), "JAX": (30.324, -81.637, False),
    "KC": (39.049, -94.484, False), "LV": (36.091, -115.184, True), "LAC": (33.953, -118.339, True),
    "LA": (33.953, -118.339, True), "MIA": (25.958, -80.239, False), "MIN": (44.974, -93.258, True),
    "NE": (42.091, -71.264, False), "NO": (29.951, -90.081, True), "NYG": (40.814, -74.074, False),
    "NYJ": (40.814, -74.074, False), "PHI": (39.901, -75.168, False), "PIT": (40.447, -80.016, False),
    "SF": (37.403, -121.970, False), "SEA": (47.595, -122.332, False), "TB": (27.976, -82.503, False),
    "TEN": (36.166, -86.771, False), "WAS": (38.908, -76.864, False),
}
# Neutral sites, matched on the nflverse stadium name.
NEUTRAL = {"tottenham": (51.604, -0.066, False), "wembley": (51.556, -0.280, False), "allianz": (48.219, 11.625, False),
           "azteca": (19.303, -99.150, False), "banorte": (19.303, -99.150, False), "corinthians": (-23.545, -46.474, False),
           "neo qu": (-23.545, -46.474, False), "croke": (53.360, -6.251, False), "bernab": (40.453, -3.688, False),
           "olympiastadion": (52.515, 13.239, False), "melbourne": (-37.820, 144.983, False), "mcg": (-37.820, 144.983, False)}


def kind(code, wind):
    """WMO weather code to one of: clear, cloud, fog, rain, snow, storm, wind."""
    c = int(code)
    k = ("storm" if c >= 95 else "snow" if c in (71, 73, 75, 77, 85, 86) else "rain" if 51 <= c <= 82 else
         "fog" if c in (45, 48) else "cloud" if c in (2, 3) else "clear")
    return "wind" if k in ("clear", "cloud") and wind >= 20 else k


def _site(g):
    if str(g.get("location", "Home")) == "Neutral":
        name = str(g.get("stadium") or "").lower()
        return next((v for k, v in NEUTRAL.items() if k in name), None)
    return HOME.get(g.home_team)


def _kickoff_utc(g):
    from zoneinfo import ZoneInfo
    try:
        return (dt.datetime.strptime(f"{g.gameday} {g.gametime}", "%Y-%m-%d %H:%M")
                .replace(tzinfo=ZoneInfo("America/New_York")).astimezone(dt.timezone.utc))
    except (ValueError, TypeError):
        return None


def forecasts(games, now):
    """games: schedule rows. Returns {game_id: {"indoor": True} | {"t", "pp", "wind", "kind", "src"}}."""
    import requests

    out, want = {}, {}
    for _, g in games.iterrows():
        ko, site = _kickoff_utc(g), _site(g)
        if ko is None or site is None or not (now <= ko <= now + dt.timedelta(days=DAYS_AHEAD)):
            continue
        roof = str(g.get("roof") or "").lower()
        if roof in ("dome", "closed") or (roof not in ("outdoors", "open") and site[2]):
            out[g.game_id] = {"indoor": True}
            continue
        want.setdefault(site[:2], []).append((g.game_id, ko))
    fails, first = 0, None
    for (lat, lon), rows in want.items():
        try:
            r = requests.get(API, timeout=15, params={
                "latitude": lat, "longitude": lon, "timezone": "UTC", "forecast_days": 16,
                "hourly": "temperature_2m,precipitation_probability,weather_code,wind_speed_10m",
                "temperature_unit": "fahrenheit", "wind_speed_unit": "mph"})
            r.raise_for_status()
            hr = r.json()["hourly"]
            idx = {t: i for i, t in enumerate(hr["time"])}
            for gid, ko in rows:
                i = idx.get(ko.replace(minute=0).strftime("%Y-%m-%dT%H:00"))
                if i is None or hr["temperature_2m"][i] is None:
                    continue
                w = hr["wind_speed_10m"][i] or 0
                pp = hr["precipitation_probability"][i]
                out[gid] = {"t": round(hr["temperature_2m"][i]), "pp": None if pp is None else round(pp), "wind": round(w),
                            "kind": kind(hr["weather_code"][i] or 0, w), "src": SRC}
        except Exception as e:  # weather is optional: never fail the build
            fails += 1
            first = first or f"{type(e).__name__}: {str(e)[:160]} {getattr(getattr(e, 'response', None), 'text', '')[:160]}".strip()
            log.warning("weather: %s,%s failed: %s", lat, lon, e)
    health.info("weather", {"games": len(out), "sites": len(want), "failed": fails})
    if fails:
        health.warn(f"weather: {fails} of {len(want)} forecast requests failed. First error: {first}")
    return out
