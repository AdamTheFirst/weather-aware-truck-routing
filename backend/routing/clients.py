"""Thin wrappers around the third-party APIs.

All free and key-less, so the reviewer can run the project without signing
up for anything:

* Photon (komoot)  -> geocoding / autocomplete   https://photon.komoot.io
* OSRM demo server -> routing                    https://project-osrm.org
* Open-Meteo       -> hourly weather forecast    https://open-meteo.com

The base URLs come from settings so they can be swapped for a self-hosted or
paid provider without touching the code.
"""
import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor

import requests
from django.conf import settings
from django.core.cache import cache

from .geo import METERS_PER_MILE, haversine_mi, offset_point

log = logging.getLogger(__name__)

HEADERS = {"User-Agent": "weather-aware-truck-routing (assessment project)"}
TIMEOUT = 20


class UpstreamError(Exception):
    """Something outside our control failed (API down, rate limited, no route)."""


def _get_json(url, params, cache_seconds=600):
    key = "http:" + hashlib.sha1(json.dumps([url, params], sort_keys=True).encode()).hexdigest()
    hit = cache.get(key)
    if hit is not None:
        return hit
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise UpstreamError(f"Could not reach {url}: {exc}") from exc
    if resp.status_code != 200:
        raise UpstreamError(f"{url} returned {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    cache.set(key, data, cache_seconds)
    return data


# ---------------------------------------------------------------- geocoding


def geocode(query, limit=5):
    data = _get_json(
        f"{settings.PHOTON_URL}/api/",
        {"q": query, "limit": limit, "lang": "en"},
        cache_seconds=86400,
    )
    results = []
    for f in data.get("features", []):
        p = f["properties"]
        parts = [p.get("name"), p.get("city"), p.get("state"), p.get("country")]
        # drop empties and repeats ("Dallas, Dallas, Texas")
        label = ", ".join(dict.fromkeys(x for x in parts if x))
        lon, lat = f["geometry"]["coordinates"]
        results.append({"label": label, "lon": lon, "lat": lat})
    return results


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


def get_routes(origin, destination, wanted=3):
    """Return up to `wanted` distinct routes.

    OSRM's `alternatives` often gives back only one or two routes, especially
    on long trips. When that happens we push the router onto other roads by
    adding a via point to the left/right of the straight line. This is the
    most "hacky" part of the backend and is the first thing I'd replace with a
    provider that supports real alternatives for trucks (HERE, TomTom, ORS
    driving-hgv).
    """
    routes = []
    for r in _osrm([origin, destination], alternatives=wanted):
        if not _is_duplicate(r, routes):
            routes.append(r)

    if len(routes) < wanted:
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
            # a detour that adds more than 40% isn't a sensible option
            if r["distance_mi"] > routes[0]["distance_mi"] * 1.4:
                continue
            if not _is_duplicate(r, routes):
                routes.append(r)

    return routes[:wanted]


# ---------------------------------------------------------------- weather

WEATHER_VARS = ["wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall"]
CHUNK = 100  # Open-Meteo accepts many locations per call, keep URLs sane


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
    )
    return data if isinstance(data, list) else [data]


def get_hourly_weather(points, start, end):
    """Hourly weather for many points between two UTC datetimes.

    Returns a list (same order as `points`) of dicts:
        {"times": [...iso...], "wind_mph": [...], "gust_mph": [...],
         "rain_in": [...], "snow_in": [...]}
    """
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


def _clean(values):
    # the API uses null for missing hours; treat missing as calm/dry
    return [v if v is not None else 0.0 for v in values]
