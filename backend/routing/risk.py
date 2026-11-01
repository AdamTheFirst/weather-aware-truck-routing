"""Weather risk rules and route recommendation.

This module is deliberately pure Python: no Django, no HTTP. Everything that
decides *how dangerous* a route is lives here, so it can be unit tested
without mocking any API.

Risk levels are plain ints so they can be compared and averaged:

    0 Low < 1 Moderate < 2 High < 3 Severe < 4 No Travel
"""

LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = range(5)

LEVEL_NAMES = {
    LOW: "low",
    MODERATE: "moderate",
    HIGH: "high",
    SEVERE: "severe",
    NO_TRAVEL: "no_travel",
}

# Lower bound of each band, from the table in the brief.
# A value >= bound moves into that band. Shared edges resolve upwards.
WIND_BOUNDS_MPH = [(55, NO_TRAVEL), (45, SEVERE), (35, HIGH), (25, MODERATE)]
RAIN_BOUNDS_IN = [(0.50, SEVERE), (0.25, HIGH), (0.10, MODERATE)]
SNOW_BOUNDS_IN = [(2.0, SEVERE), (1.0, HIGH), (0.5, MODERATE)]

# For rain and snow the brief says "> X" for No Travel (strictly greater),
# so these are handled separately from the >= bands above.
RAIN_NO_TRAVEL_ABOVE = 1.00
SNOW_NO_TRAVEL_ABOVE = 3.0


def _band(value, bounds):
    for bound, level in bounds:
        if value >= bound:
            return level
    return LOW


def classify_wind(mph):
    return _band(mph, WIND_BOUNDS_MPH)


def classify_rain(inches_per_hr):
    if inches_per_hr > RAIN_NO_TRAVEL_ABOVE:
        return NO_TRAVEL
    return _band(inches_per_hr, RAIN_BOUNDS_IN)


def classify_snow(inches_per_hr):
    if inches_per_hr > SNOW_NO_TRAVEL_ABOVE:
        return NO_TRAVEL
    return _band(inches_per_hr, SNOW_BOUNDS_IN)


def apply_load_rules(wind_level, wind_mph, load_lb):
    """Heavier trucks are more exposed to crosswind, so wind gets worse with load.

    Returns (new_level, reason_or_None).
    """
    if wind_mph >= 55:
        return NO_TRAVEL, "55+ mph wind: no travel for any load"
    if 45 <= wind_mph < 55 and load_lb > 30_000:
        return NO_TRAVEL, "45-54 mph wind with load over 30,000 lb"
    if 35 <= wind_mph < 45 and load_lb > 40_000:
        return max(wind_level, SEVERE), "35-44 mph wind with load over 40,000 lb"
    return wind_level, None


def classify_checkpoint(wind_mph, rain_in, snow_in, load_lb):
    """Risk for one point at one hour. The worst single condition wins.

    `driver` tells the UI *why* a point is risky, which is more useful to a
    driver than just a colour.
    """
    wind_level, load_rule = apply_load_rules(classify_wind(wind_mph), wind_mph, load_lb)
    levels = {
        "wind": wind_level,
        "rain": classify_rain(rain_in),
        "snow": classify_snow(snow_in),
    }
    driver = max(levels, key=levels.get)
    level = levels[driver]
    return {
        "level": level,
        "label": LEVEL_NAMES[level],
        "driver": driver if level > LOW else None,
        "by_condition": {k: LEVEL_NAMES[v] for k, v in levels.items()},
        "load_rule": load_rule if driver == "wind" else None,
    }


def summarize_route(checkpoints):
    """Turn a list of checkpoints into miles-per-level and an average risk.

    Checkpoints only exist every N miles, but the recommendation rules talk
    about *miles*. Each stretch between two checkpoints is given the worse of
    its two ends. That is on the cautious side: if either end is severe we
    count the whole stretch as severe. For a truck driver, over-warning is
    cheaper than under-warning.

    Each checkpoint must have `mile` and `risk.level`.
    """
    miles = {name: 0.0 for name in LEVEL_NAMES.values()}
    weighted = 0.0
    total = 0.0
    for a, b in zip(checkpoints, checkpoints[1:]):
        length = b["mile"] - a["mile"]
        level = max(a["risk"]["level"], b["risk"]["level"])
        miles[LEVEL_NAMES[level]] += length
        weighted += level * length
        total += length

    worst = max((cp["risk"]["level"] for cp in checkpoints), default=LOW)
    return {
        "miles_by_level": {k: round(v, 1) for k, v in miles.items()},
        "avg_risk": round(weighted / total, 3) if total else 0.0,
        "worst_level": LEVEL_NAMES[worst],
    }


def ranking_key(route):
    """Sort key implementing the brief's priority list.

    The brief lists: fewest Severe miles, fewest High miles, lowest average
    risk, shortest time. It doesn't mention No Travel, but a No Travel mile
    is clearly worse than a Severe one, so it goes in front.
    """
    m = route["summary"]["miles_by_level"]
    return (
        m["no_travel"],
        m["severe"],
        m["high"],
        route["summary"]["avg_risk"],
        route["duration_s"],
    )


def recommend(routes):
    if not routes:
        return None
    return min(routes, key=ranking_key)
