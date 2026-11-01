"""HTTP layer. Validates input, calls the planner, turns errors into JSON.

Two endpoints:
    GET  /api/geocode?q=...   -> place suggestions for the search boxes
    POST /api/plan            -> the full trip plan (routes, risk, heatmap)
"""
import json
from datetime import datetime, timedelta, timezone

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import clients
from .planner import plan_trip

ALLOWED_INTERVALS = {10, 25, 50}
MAX_LOAD_LB = 120_000
# Open-Meteo forecasts go out ~16 days; leave room for the trip itself + 48h slider
MAX_DAYS_AHEAD = 10


@require_GET
def geocode_view(request):
    q = request.GET.get("q", "").strip()
    if len(q) < 3:
        return JsonResponse({"results": []})
    try:
        return JsonResponse({"results": clients.geocode(q)})
    except clients.UpstreamError as exc:
        return JsonResponse({"error": str(exc)}, status=502)


def _point(value, name):
    try:
        return float(value["lon"]), float(value["lat"])
    except (TypeError, KeyError, ValueError):
        raise ValueError(f"{name} must be an object with lon and lat")


def _parse_plan_request(body):
    """Returns cleaned kwargs for plan_trip, or raises ValueError with a message for the user."""
    origin = _point(body.get("origin"), "origin")
    destination = _point(body.get("destination"), "destination")
    if origin == destination:
        raise ValueError("Origin and destination are the same place")

    try:
        departure = datetime.fromisoformat(body["departure"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("departure must be an ISO date-time")
    if departure.tzinfo is None:
        # the frontend always sends an offset; if someone doesn't, assume UTC
        departure = departure.replace(tzinfo=timezone.utc)
    departure = departure.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if departure < now - timedelta(hours=1):
        raise ValueError("Departure time is in the past")
    if departure > now + timedelta(days=MAX_DAYS_AHEAD):
        raise ValueError(f"Departure must be within {MAX_DAYS_AHEAD} days (forecast limit)")

    try:
        load_lb = float(body["load_lb"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("load_lb must be a number")
    if not 0 <= load_lb <= MAX_LOAD_LB:
        raise ValueError(f"Load must be between 0 and {MAX_LOAD_LB:,} lb")

    interval = int(body.get("interval_mi", 25))
    if interval not in ALLOWED_INTERVALS:
        raise ValueError("interval_mi must be 10, 25 or 50")

    return {
        "origin": origin,
        "destination": destination,
        "departure": departure,
        "load_lb": load_lb,
        "interval_mi": interval,
    }


@csrf_exempt  # public JSON API with no sessions/cookies, so CSRF doesn't apply
@require_POST
def plan_view(request):
    try:
        body = json.loads(request.body or "{}")
        params = _parse_plan_request(body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Body must be JSON"}, status=400)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    try:
        return JsonResponse(plan_trip(**params))
    except clients.UpstreamError as exc:
        return JsonResponse({"error": str(exc)}, status=502)
