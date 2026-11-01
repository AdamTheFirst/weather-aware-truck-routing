"""Geometry helpers: distances and placing checkpoints along a route.

Pure Python, no Django, so it's easy to test.
Coordinates are (lon, lat) everywhere, because that's what GeoJSON and OSRM use.
"""
import math

EARTH_RADIUS_MI = 3958.8
METERS_PER_MILE = 1609.344

# OSRM's public server only has a *car* profile. Trucks are slower, so we
# never let a segment go faster than this. It's a rough correction, not a
# truck routing engine (the brief says we don't need one).
TRUCK_MAX_MPH = 65


def haversine_mi(a, b):
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(h))


def segment_profile(coords, osrm_durations=None, osrm_total_s=None):
    """Per-segment (miles, seconds) for a polyline, with the truck speed cap applied.

    If OSRM gave us per-segment durations that line up with the geometry we
    use them. Otherwise we spread the total time evenly by distance.
    """
    miles = [haversine_mi(a, b) for a, b in zip(coords, coords[1:])]
    if osrm_durations and len(osrm_durations) == len(miles):
        seconds = list(osrm_durations)
    else:
        total_mi = sum(miles) or 1
        total_s = osrm_total_s or total_mi / 55 * 3600
        seconds = [m / total_mi * total_s for m in miles]

    min_s_per_mi = 3600 / TRUCK_MAX_MPH
    seconds = [max(s, m * min_s_per_mi) for m, s in zip(miles, seconds)]
    return miles, seconds


def sample_checkpoints(coords, seg_miles, seg_seconds, interval_mi):
    """Walk along the route and drop a checkpoint every `interval_mi` miles.

    Returns a list of dicts: {mile, offset_s, lon, lat}. The first checkpoint
    is the origin and the last is always the destination, even if the final
    gap is shorter than the interval.
    """
    if interval_mi <= 0:
        raise ValueError("interval must be positive")

    points = [{"mile": 0.0, "offset_s": 0.0, "lon": coords[0][0], "lat": coords[0][1]}]
    next_mark = interval_mi
    walked_mi = 0.0
    walked_s = 0.0

    for i, (m, s) in enumerate(zip(seg_miles, seg_seconds)):
        # a single long segment can contain several marks, hence the while
        while m > 0 and walked_mi + m >= next_mark:
            t = (next_mark - walked_mi) / m
            a, b = coords[i], coords[i + 1]
            points.append(
                {
                    "mile": next_mark,
                    "offset_s": walked_s + t * s,
                    "lon": a[0] + t * (b[0] - a[0]),
                    "lat": a[1] + t * (b[1] - a[1]),
                }
            )
            next_mark += interval_mi
        walked_mi += m
        walked_s += s

    # Close off with the destination unless a mark landed right on it.
    if walked_mi - points[-1]["mile"] > 0.05:
        points.append(
            {"mile": walked_mi, "offset_s": walked_s, "lon": coords[-1][0], "lat": coords[-1][1]}
        )
    return points


def bbox(coord_lists, pad_deg=0.3):
    lons = [c[0] for coords in coord_lists for c in coords]
    lats = [c[1] for coords in coord_lists for c in coords]
    return (min(lons) - pad_deg, min(lats) - pad_deg, max(lons) + pad_deg, max(lats) + pad_deg)


def corridor_grid(coord_lists, max_points=220, near_mi=40):
    """Grid of points covering the area around all routes, for the heatmap.

    We lay a regular grid over the bounding box and keep only cells within
    `near_mi` of some route point. The grid spacing grows with the trip
    length so we stay under `max_points` (each point is one weather lookup).
    """
    west, south, east, north = bbox(coord_lists)
    # thin the route so the "near" check stays cheap on long routes
    route_pts = [c for coords in coord_lists for c in coords[:: max(1, len(coords) // 150)]]

    step = 0.25
    while True:
        cells = []
        lat = south
        while lat <= north:
            lon = west
            while lon <= east:
                cells.append((round(lon, 4), round(lat, 4)))
                lon += step
            lat += step
        kept = [c for c in cells if any(haversine_mi(c, p) <= near_mi for p in route_pts)]
        if len(kept) <= max_points:
            return kept, step
        step *= 1.3


def offset_point(a, b, fraction, side_mi):
    """A point `fraction` of the way from a to b, pushed sideways by `side_mi`.

    Used to build a via point that forces the router onto a different road
    when it doesn't return enough alternatives on its own.
    """
    mid_lon = a[0] + fraction * (b[0] - a[0])
    mid_lat = a[1] + fraction * (b[1] - a[1])
    # perpendicular direction in roughly-equal-distance degrees
    dx = (b[0] - a[0]) * math.cos(math.radians(mid_lat))
    dy = b[1] - a[1]
    length = math.hypot(dx, dy) or 1
    px, py = -dy / length, dx / length
    deg = side_mi / 69.0
    return (mid_lon + px * deg / math.cos(math.radians(mid_lat)), mid_lat + py * deg)
