"""API tests with the third-party services mocked out.

These check the wiring (validation, planner, recommendation, response shape)
without hitting the network, so they're fast and don't flake.
"""
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
from django.test import Client

from routing import clients


def fake_routes(origin, destination, wanted=3):
    # three straight-ish "roads" heading north, ~69 miles each
    def road(lon_offset, duration):
        coords = [(lon_offset, 0.0), (lon_offset + 0.05, 0.5), (lon_offset, 1.0)]
        return {
            "coords": coords,
            "osrm_durations": [],
            "osrm_duration_s": duration,
            "distance_mi": 69,
            "via": f"Road {lon_offset}",
        }

    return [road(0.0, 3600 * 1.2), road(0.5, 3600 * 1.3), road(1.0, 3600 * 1.5)]


def fake_weather(points, start, end):
    hours = int((end - start).total_seconds() // 3600) + 1
    times = [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:00") for h in range(hours)]
    out = []
    for lon, lat in points:
        # make the westmost road (lon ~0) windy, everything else calm
        wind = 50.0 if lon < 0.2 else 5.0
        out.append(
            {
                "times": times,
                "wind_mph": [wind] * hours,
                "gust_mph": [wind + 10] * hours,
                "rain_in": [0.0] * hours,
                "snow_in": [0.0] * hours,
            }
        )
    return out


@pytest.fixture
def body():
    return {
        "origin": {"lon": 0, "lat": 0},
        "destination": {"lon": 0, "lat": 1},
        "departure": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "load_lb": 35_000,
        "interval_mi": 10,
    }


def post(body):
    return Client().post("/api/plan", body, content_type="application/json")


@mock.patch.object(clients, "get_hourly_weather", side_effect=fake_weather)
@mock.patch.object(clients, "get_routes", side_effect=fake_routes)
def test_plan_avoids_the_windy_road(_routes, _weather, body):
    resp = post(body)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["routes"]) == 3
    # Road A is fastest but 50 mph wind + 35k lb = No Travel, so B should win
    assert data["recommended_id"] == "B"
    a = next(r for r in data["routes"] if r["id"] == "A")
    assert a["summary"]["miles_by_level"]["no_travel"] > 0
    assert "No Travel" in data["recommendation_reason"]
    # heatmap has one row per grid point and 49 hourly values (0..48)
    hm = data["heatmap"]
    assert len(hm["levels"]) == len(hm["points"])
    assert all(len(row) == 49 for row in hm["levels"])


@pytest.mark.parametrize(
    "patch,message",
    [
        ({"interval_mi": 15}, "interval"),
        ({"load_lb": -5}, "Load"),
        ({"departure": "tomorrow"}, "departure"),
        ({"origin": {"lon": 0}}, "origin"),
        ({"destination": {"lon": 0, "lat": 0}}, "same place"),
    ],
)
def test_validation(body, patch, message):
    body.update(patch)
    resp = post(body)
    assert resp.status_code == 400
    assert message in resp.json()["error"]


def test_past_departure_rejected(body):
    body["departure"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert post(body).status_code == 400


@mock.patch.object(clients, "get_routes", side_effect=clients.UpstreamError("OSRM is down"))
def test_upstream_failure_is_502(_routes, body):
    resp = post(body)
    assert resp.status_code == 502
    assert "OSRM" in resp.json()["error"]
