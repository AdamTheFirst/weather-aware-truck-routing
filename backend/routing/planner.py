"""Puts it all together: routes -> checkpoints -> weather -> risk -> recommendation.

This is the only place that knows about both the APIs (clients.py) and the
rules (risk.py / geo.py). Views call `plan_trip` and return what it gives.
"""
from datetime import timedelta

from . import clients
from .geo import corridor_grid, dedupe_coords, haversine_mi, sample_checkpoints, segment_profile
from .risk import AVG_RISK_TOLERANCE, LEVEL_NAMES, classify_checkpoint, recommend, summarize_route

HEATMAP_HOURS = 48
ROUTE_LABELS = "ABC"


def _hour_index(times, when):
    """Index of the forecast hour closest to `when` (UTC)."""
    target = when.strftime("%Y-%m-%dT%H:00")
    if when.minute >= 30:
        target = (when + timedelta(hours=1)).strftime("%Y-%m-%dT%H:00")
    try:
        return times.index(target)
    except ValueError:
        # outside the window we asked for; clamp to the nearest end
        return 0 if target < times[0] else len(times) - 1


def plan_trip(origin, destination, departure, load_lb, interval_mi):
    """
    origin/destination: (lon, lat)
    departure: timezone-aware datetime
    """
    raw_routes = clients.get_routes(origin, destination)
    if not raw_routes:
        raise clients.UpstreamError("No route found between these places.")

    # 1. checkpoints along each route, with the truck's ETA at each one
    routes = []
    for label, r in zip(ROUTE_LABELS, raw_routes):
        miles, seconds = segment_profile(r["coords"], r["osrm_durations"], r["osrm_duration_s"])
        cps = sample_checkpoints(r["coords"], miles, seconds, interval_mi)
        routes.append(
            {
                "id": label,
                "via": r["via"],
                "distance_mi": round(sum(miles), 1),
                "duration_s": round(sum(seconds)),
                "geometry": _thin(r["coords"]),
                "checkpoints": cps,
            }
        )

    # 2. one weather request for every point we care about: all checkpoints
    #    plus the heatmap grid. The time window covers the 48h slider and the
    #    whole trip (a long haul can run past 48h).
    grid, grid_step = corridor_grid([r["coords"] for r in raw_routes])
    cp_points = [(cp["lon"], cp["lat"]) for r in routes for cp in r["checkpoints"]]
    longest_s = max(r["duration_s"] for r in routes)
    start = departure.replace(minute=0, second=0, microsecond=0)
    end = start + timedelta(seconds=max(HEATMAP_HOURS * 3600, longest_s + 3600))

    # Routes that share a road, and grid cells on top of a checkpoint, would
    # otherwise be separate Open-Meteo locations. 0.05° is about 3 miles,
    # finer than the forecast grid, so the weather a driver sees doesn't change.
    unique_points, point_index = dedupe_coords(cp_points + grid, step_deg=0.05)
    weather_unique = clients.get_hourly_weather(unique_points, start, end)
    weather = [weather_unique[i] for i in point_index]
    cp_weather, grid_weather = weather[: len(cp_points)], weather[len(cp_points) :]

    # 3. classify each checkpoint at the hour the truck gets there
    i = 0
    for r in routes:
        for cp in r["checkpoints"]:
            w = cp_weather[i]
            i += 1
            eta = departure + timedelta(seconds=cp["offset_s"])
            h = _hour_index(w["times"], eta)
            # Classify the raw forecast. Rounding first moves a boundary the
            # wrong way: 34.96 mph is Moderate, but round(34.96, 1) is 35.0
            # and that is High. The popup still shows the rounded numbers.
            raw_wind = w["wind_mph"][h]
            raw_rain = w["rain_in"][h]
            raw_snow = w["snow_in"][h]
            cp["eta"] = eta.isoformat()
            cp["mile"] = round(cp["mile"], 1)
            cp["lon"] = round(cp["lon"], 5)
            cp["lat"] = round(cp["lat"], 5)
            cp["weather"] = {
                "wind_mph": round(raw_wind, 1),
                "gust_mph": round(w["gust_mph"][h], 1),
                "rain_in": round(raw_rain, 3),
                "snow_in": round(raw_snow, 3),
            }
            cp["risk"] = classify_checkpoint(raw_wind, raw_rain, raw_snow, load_lb)
            del cp["offset_s"]
        r["summary"] = summarize_route(r["checkpoints"])

    best = recommend(routes)
    best_miles = best["summary"]["miles_by_level"]
    # False when the winner itself still crosses No Travel or Severe weather.
    # The UI uses this to warn instead of showing a green "all clear".
    safe = best_miles["no_travel"] == 0 and best_miles["severe"] == 0

    # 4. heatmap: risk level for every grid point at every hour 0..48 from
    #    departure. Sent as small ints so the slider can scrub client-side
    #    without any further requests.
    heat_levels = []
    for w in grid_weather:
        h0 = _hour_index(w["times"], departure)
        row = []
        for h in range(h0, h0 + HEATMAP_HOURS + 1):
            h = min(h, len(w["times"]) - 1)
            row.append(classify_checkpoint(w["wind_mph"][h], w["rain_in"][h], w["snow_in"][h], load_lb)["level"])
        heat_levels.append(row)

    return {
        "departure": departure.isoformat(),
        "load_lb": load_lb,
        "interval_mi": interval_mi,
        "levels": LEVEL_NAMES,
        "routes": routes,
        "recommended_id": best["id"],
        "recommendation_reason": _explain(best, routes),
        "safe": safe,
        "heatmap": {
            "hours": HEATMAP_HOURS,
            "step_deg": grid_step,
            "points": [[lon, lat] for lon, lat in grid],
            "levels": heat_levels,
        },
    }


def _thin(coords, min_gap_mi=0.15):
    """Drop geometry points closer than `min_gap_mi` to the last kept one.

    OSRM's full geometry has a point every few metres in cities, which makes
    the JSON ~4x bigger than it needs to be for drawing a line on a map. All
    the maths above still uses the full geometry; this is display only.
    """
    kept = [coords[0]]
    for c in coords[1:-1]:
        if haversine_mi(kept[-1], c) >= min_gap_mi:
            kept.append(c)
    kept.append(coords[-1])
    return [[round(lon, 5), round(lat, 5)] for lon, lat in kept]


def _explain(best, routes):
    """One human sentence on why the winner won, following the ranking order."""
    others = [r for r in routes if r is not best]
    if not others:
        return "Only one route was found."
    b = best["summary"]["miles_by_level"]
    checks = [
        ("no_travel", "it avoids No Travel conditions"),
        ("severe", "it has the fewest Severe-risk miles"),
        ("high", "it has the fewest High-risk miles"),
    ]
    for key, text in checks:
        if any(o["summary"]["miles_by_level"][key] > b[key] for o in others):
            return f"Route {best['id']} is recommended because {text}."
    # Same tolerance as recommend(). A tenth of a point is not "lower risk".
    if any(o["summary"]["avg_risk"] - best["summary"]["avg_risk"] >= AVG_RISK_TOLERANCE for o in others):
        return f"Route {best['id']} is recommended because it has the lowest average weather risk."
    return f"Route {best['id']} is recommended because weather risk is similar and it is the fastest."
