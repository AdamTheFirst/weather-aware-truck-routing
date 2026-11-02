"""Thin wrappers around the third-party APIs.

All free and key-less, so the reviewer can run the project without signing
up for anything:

* Photon (komoot)       -> geocoding / autocomplete   https://photon.komoot.io
* Open-Meteo Geocoding  -> backup place search        https://open-meteo.com
* OSRM demo server      -> routing                    https://project-osrm.org
* Open-Meteo            -> hourly weather forecast    https://open-meteo.com
* MET Norway            -> backup forecast            https://api.met.no

Photon refuses some cloud addresses, and Open-Meteo's free daily limit is
shared by everyone on a host like Render. Each primary call falls back to
the other provider rather than failing the demo. Nominatim is not used:
its policy forbids autocomplete, which is what the search box does.

The base URLs come from settings so they can be swapped for a self-hosted or
paid provider without touching the code.
"""
import hashlib
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests
from django.conf import settings
from django.core.cache import cache

from .geo import METERS_PER_MILE, haversine_mi, offset_point

log = logging.getLogger(__name__)

# MET Norway blocks generic clients and asks for an app name plus a page
# where they can reach the operator. The same agent is fine for the others.
HEADERS = {
    "User-Agent": (
        "weather-aware-truck-routing/1.0 "
        "(+https://github.com/AdamTheFirst/weather-aware-truck-routing)"
    )
}
TIMEOUT = 20
# MET Norway's terms cap an application at 20 requests/second and reject
# coordinates with more than 4 decimal places. Stay well under the cap.
MET_MAX_PER_SECOND = 8
_met_lock = threading.Lock()
_met_next = 0.0


class UpstreamError(Exception):
    """Something outside our control failed (API down, rate limited, no route)."""


def _brief(exc):
    """One short clause a driver can read, instead of a URL and a traceback."""
    text = " ".join(str(exc).split())
    lowered = text.lower()
    if "429" in text or "limit" in lowered:
        return "the daily request limit for this server is used up"
    if "connection refused" in lowered or "errno 111" in lowered or "could not reach" in lowered:
        return "the connection was refused"
    return text[:140]


def _get_json(url, params, cache_seconds=600, headers=None):
    key = "http:" + hashlib.sha1(json.dumps([url, params], sort_keys=True).encode()).hexdigest()
    hit = cache.get(key)
    if hit is not None:
        return hit
    try:
        resp = requests.get(url, params=params, headers=headers or HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise UpstreamError(f"Could not reach {url}: {exc}") from exc
    if resp.status_code != 200:
        raise UpstreamError(f"{url} returned {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    cache.set(key, data, cache_seconds)
    return data


# ---------------------------------------------------------------- geocoding


def _place_label(parts):
    # drop empties and repeats ("Dallas, Dallas, Texas")
    return ", ".join(dict.fromkeys(x for x in parts if x))


def _geocode_photon(query, limit):
    data = _get_json(
        f"{settings.PHOTON_URL}/api/",
        {"q": query, "limit": limit, "lang": "en"},
        cache_seconds=86400,
    )
    results = []
    for f in data.get("features", []):
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"]
        results.append(
            {
                "label": _place_label([p.get("name"), p.get("city"), p.get("state"), p.get("country")]),
                "lon": lon,
                "lat": lat,
            }
        )
    return results


def _geocode_open_meteo(query, limit):
    """Backup search. A different host from the forecast API, and it allows search."""
    data = _get_json(
        settings.OPEN_METEO_GEOCODE_URL,
        {"name": query, "count": limit, "language": "en", "format": "json"},
        cache_seconds=86400,
    )
    results = []
    for r in data.get("results") or []:
        results.append(
            {
                "label": _place_label([r.get("name"), r.get("admin1"), r.get("country")]),
                "lon": r["longitude"],
                "lat": r["latitude"],
            }
        )
    return results


def geocode(query, limit=5):
    """Place search. Photon first; Open-Meteo Geocoding if Photon cannot be reached."""
    try:
        return _geocode_photon(query, limit)
    except UpstreamError as primary:
        log.warning("Photon geocoding failed: %s", primary)
        try:
            return _geocode_open_meteo(query, limit)
        except UpstreamError as backup:
            log.warning("Open-Meteo geocoding failed: %s", backup)
            raise UpstreamError(
                "Place search is unavailable right now. "
                f"Photon: {_brief(primary)}. Backup geocoder: {_brief(backup)}."
            ) from backup


# ---------------------------------------------------------------- routing


def _osrm(coords, alternatives):
    path = ";".join(f"{lon:.5f},{lat:.5f}" for lon, lat in coords)
    data = _get_json(
        f"{settings.OSRM_URL}/route/v1/driving/{path}",
        {
            "alternatives": str(alternatives).lower() if isinstance(alternatives, bool) else alternatives,
            "overview": "full",
            "geometries": "geojson",
            "annotations": "duration",
            "steps": "true",  # only needed for the road-name summary
        },
    )
    if data.get("code") != "Ok":
        raise UpstreamError(f"Routing failed: {data.get('message') or data.get('code')}")
    return [_parse_osrm_route(r) for r in data["routes"]]


def _parse_osrm_route(r):
    durations = []
    for leg in r["legs"]:
        durations.extend(leg.get("annotation", {}).get("duration", []))
    # OSRM gives "Road A, Road B" per leg; flatten and drop repeats across legs
    names = [n.strip() for leg in r["legs"] for n in leg.get("summary", "").split(",") if n.strip()]
    via = ", ".join(dict.fromkeys(names))
    return {
        "coords": [tuple(c) for c in r["geometry"]["coordinates"]],
        "osrm_durations": durations,
        "osrm_duration_s": r["duration"],
        "distance_mi": r["distance"] / METERS_PER_MILE,
        "via": via,
    }


def _is_duplicate(candidate, existing):
    # Two routes within 2% on both distance and time are "the same road" for
    # our purposes. Crude, but cheap and good enough to avoid showing twins.
    for r in existing:
        if (
            abs(candidate["distance_mi"] - r["distance_mi"]) / r["distance_mi"] < 0.02
            and abs(candidate["osrm_duration_s"] - r["osrm_duration_s"]) / r["osrm_duration_s"] < 0.02
        ):
            return True
    return False


# Via-point detours slower than this are not real alternatives. 1.25× the
# fastest route drops the Denver–Salt Lake City case (13.27 h / 8.98 h ≈ 1.48)
# while keeping a route that is only a bit slower. Distance is checked
# separately (1.4×); that detour was only ~1.11× as long, so miles alone
# would have kept it.
MAX_VIA_DURATION_FACTOR = 1.25


def get_routes(origin, destination, wanted=3):
    """Return up to `wanted` distinct routes.

    OSRM's `alternatives` often gives back only one or two routes, especially
    on long trips. When that happens we push the router onto other roads by
    adding a via point to the left/right of the straight line. Detours more
    than 40% longer, or more than 25% slower than the fastest route, are
    dropped. This is the most "hacky" part of the backend and is the first
    thing I'd replace with a provider that supports real alternatives for
    trucks (HERE, TomTom, ORS driving-hgv).
    """
    routes = []
    for r in _osrm([origin, destination], alternatives=wanted):
        if not _is_duplicate(r, routes):
            routes.append(r)

    if len(routes) < wanted:
        fastest_s = min(r["osrm_duration_s"] for r in routes)
        straight = haversine_mi(origin, destination)
        side = max(15.0, straight * 0.15)
        for fraction, mult in [(0.5, 1), (0.5, -1), (0.5, 2), (0.5, -2), (0.33, 1), (0.66, -1)]:
            if len(routes) >= wanted:
                break
            via = offset_point(origin, destination, fraction, side * mult)
            try:
                found = _osrm([origin, via, destination], alternatives=False)
            except UpstreamError as exc:
                log.info("via-point route failed: %s", exc)
                continue
            r = found[0]
            # a detour that adds more than 40% distance isn't a sensible option
            if r["distance_mi"] > routes[0]["distance_mi"] * 1.4:
                continue
            # nor is one that takes more than 25% longer than the fastest route
            if r["osrm_duration_s"] > fastest_s * MAX_VIA_DURATION_FACTOR:
                continue
            if not _is_duplicate(r, routes):
                routes.append(r)

    return routes[:wanted]


# ---------------------------------------------------------------- weather

WEATHER_VARS = ["wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall"]
CHUNK = 100  # Open-Meteo accepts many locations per call, keep URLs sane
# Hourly forecasts don't move faster than the hour. 45 minutes sits inside
# the 30–60 minute window: long enough that a repeat demo doesn't burn the
# free-tier quota, short enough that a refreshed forecast shows up the same day.
WEATHER_CACHE_SECONDS = 45 * 60


def _fetch_weather_chunk(points, start_hour, end_hour):
    data = _get_json(
        settings.OPEN_METEO_URL,
        {
            "latitude": ",".join(f"{lat:.3f}" for _, lat in points),
            "longitude": ",".join(f"{lon:.3f}" for lon, _ in points),
            "hourly": ",".join(WEATHER_VARS),
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",  # also makes snowfall come back in inches
            "timezone": "GMT",
            "start_hour": start_hour,
            "end_hour": end_hour,
        },
        cache_seconds=WEATHER_CACHE_SECONDS,
    )
    return data if isinstance(data, list) else [data]


def _open_meteo_weather(points, start, end):
    start_hour = start.strftime("%Y-%m-%dT%H:00")
    end_hour = end.strftime("%Y-%m-%dT%H:00")
    chunks = [points[i : i + CHUNK] for i in range(0, len(points), CHUNK)]

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda c: _fetch_weather_chunk(c, start_hour, end_hour), chunks))

    out = []
    for chunk_result in results:
        for loc in chunk_result:
            h = loc["hourly"]
            n = len(h["time"])
            zero = [0.0] * n
            out.append(
                {
                    "times": h["time"],
                    "wind_mph": _clean(h.get("wind_speed_10m", zero)),
                    "gust_mph": _clean(h.get("wind_gusts_10m", zero)),
                    # Open-Meteo splits rain into large-scale "rain" and convective "showers"
                    "rain_in": [a + b for a, b in zip(_clean(h.get("rain", zero)), _clean(h.get("showers", zero)))],
                    "snow_in": _clean(h.get("snowfall", zero)),
                }
            )
    if len(out) != len(points):
        raise UpstreamError("Weather service returned an unexpected number of locations")
    return out


def _pace_met():
    """Space MET Norway calls out so one plan cannot burst past their limit."""
    global _met_next
    with _met_lock:
        now = time.monotonic()
        wait = _met_next - now
        _met_next = max(now, _met_next) + (1 / MET_MAX_PER_SECOND)
    if wait > 0:
        time.sleep(wait)


def met_precip_inches(mm, symbol, temp_c):
    """Turn MET Norway's millimetres of water into the inches the risk table uses.

    `precipitation_amount` is liquid water, not snow depth. Rain is that
    water in inches. Snow depth is about ten times the water (a 10:1 ratio)
    when the symbol, or a temperature at or below freezing, says it is snow.
    Sleet counts as both, and the risk rules keep the worse of the two.
    """
    water_in = (mm or 0.0) / 25.4
    code = (symbol or "").lower()
    snow = "snow" in code
    sleet = "sleet" in code
    if not snow and not sleet and temp_c is not None and temp_c <= 0 and water_in > 0 and "rain" not in code:
        snow = True
    if sleet:
        return water_in * 0.5, water_in * 5
    if snow:
        return 0.0, water_in * 10
    return water_in, 0.0


def _utc_hour(when):
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def met_timeseries_to_hourly(payload, start, end):
    """One MET Norway location payload -> the same hourly dict Open-Meteo produces.

    The compact feed is hourly for about two days and then every six hours.
    Hours that fall inside a six-hour step reuse that step, and its
    precipitation is spread across the six hours so the rate stays per hour.
    """
    try:
        series = payload["properties"]["timeseries"]
    except (KeyError, TypeError) as exc:
        raise UpstreamError("MET Norway returned an unexpected forecast") from exc
    rows = []
    for entry in series:
        when = _utc_hour(_parse_met_time(entry["time"]))
        data = entry.get("data") or {}
        instant = (data.get("instant") or {}).get("details") or {}
        next_1 = data.get("next_1_hours") or {}
        next_6 = data.get("next_6_hours") or {}
        symbol = ((next_1.get("summary") or next_6.get("summary") or {}).get("symbol_code"))
        mm_1 = (next_1.get("details") or {}).get("precipitation_amount")
        mm_6 = (next_6.get("details") or {}).get("precipitation_amount")
        if mm_1 is not None:
            mm = mm_1
        elif mm_6 is not None:
            mm = mm_6 / 6.0
        else:
            mm = 0.0
        rows.append(
            {
                "time": when,
                "wind": instant.get("wind_speed") or 0.0,
                "gust": instant.get("wind_speed_of_gust"),
                "temp": instant.get("air_temperature"),
                "symbol": symbol,
                "mm": mm,
            }
        )
    if not rows:
        raise UpstreamError("MET Norway returned no forecast times")
    rows.sort(key=lambda row: row["time"])

    start_hour = _utc_hour(start)
    end_hour = _utc_hour(end)
    times, wind, gust, rain, snow = [], [], [], [], []
    hour = start_hour
    mps_to_mph = 2.2369362920544
    while hour <= end_hour:
        row = _row_at(rows, hour)
        rain_in, snow_in = met_precip_inches(row["mm"], row["symbol"], row["temp"])
        gust_mps = row["wind"] if row["gust"] is None else row["gust"]
        times.append(hour.strftime("%Y-%m-%dT%H:00"))
        wind.append(row["wind"] * mps_to_mph)
        gust.append(gust_mps * mps_to_mph)
        rain.append(rain_in)
        snow.append(snow_in)
        hour += timedelta(hours=1)
    return {
        "times": times,
        "wind_mph": wind,
        "gust_mph": gust,
        "rain_in": rain,
        "snow_in": snow,
    }


def _parse_met_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _row_at(rows, hour):
    chosen = rows[0]
    for row in rows:
        if row["time"] <= hour:
            chosen = row
        else:
            break
    return chosen


def _fetch_met_point(point, start, end):
    lon, lat = point
    _pace_met()
    # 5+ decimal places are rejected with 403. Four is the precision they ask for.
    data = _get_json(
        settings.MET_NORWAY_URL,
        {"lat": f"{round(lat, 4):.4f}", "lon": f"{round(lon, 4):.4f}"},
        cache_seconds=WEATHER_CACHE_SECONDS,
    )
    return met_timeseries_to_hourly(data, start, end)


def _met_norway_weather(points, start, end):
    # A handful of calls in flight, and _pace_met keeps the rate near 8/s.
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda point: _fetch_met_point(point, start, end), points))


def get_hourly_weather(points, start, end):
    """Hourly weather for many points between two UTC datetimes.

    Returns a list (same order as `points`) of dicts:
        {"times": [...iso...], "wind_mph": [...], "gust_mph": [...],
         "rain_in": [...], "snow_in": [...]}

    Open-Meteo is asked first because one call covers many locations.
    MET Norway is the backup when that call is refused or rate-limited.
    """
    if not points:
        return []
    try:
        return _open_meteo_weather(points, start, end)
    except UpstreamError as primary:
        log.warning("Open-Meteo forecast failed: %s", primary)
        try:
            return _met_norway_weather(points, start, end)
        except UpstreamError as backup:
            log.warning("MET Norway forecast failed: %s", backup)
            raise UpstreamError(
                "Weather data is unavailable right now. "
                f"Open-Meteo: {_brief(primary)}. Backup forecast: {_brief(backup)}."
            ) from backup


def _clean(values):
    # the API uses null for missing hours; treat missing as calm/dry
    return [v if v is not None else 0.0 for v in values]
