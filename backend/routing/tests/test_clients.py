"""Routing-client tests. OSRM is mocked; nothing here touches the network."""
from unittest import mock

import pytest

from routing import clients

DENVER = (-104.9903, 39.7392)
SALT_LAKE = (-111.8910, 40.7608)


def _route(duration_h, distance_mi, via="Road"):
    return {
        "coords": [DENVER, SALT_LAKE],
        "osrm_durations": [],
        "osrm_duration_s": duration_h * 3600,
        "distance_mi": distance_mi,
        "via": via,
    }


def test_denver_slc_via_route_slower_than_1_25x_is_dropped():
    """The live bug: Route C was 13.27 h vs Route A's 8.98 h (1.48×).

    It was only 573/518 ≈ 1.11× as long, so the 1.4× distance check kept it.
    The duration cap is what drops it.
    """
    fastest = _route(8.98, 518, via="I-80")
    detour = _route(13.27, 573, via="Detour")

    def fake_osrm(coords, alternatives):
        return [fastest] if len(coords) == 2 else [detour]

    with mock.patch.object(clients, "_osrm", side_effect=fake_osrm):
        routes = clients.get_routes(DENVER, SALT_LAKE, wanted=3)

    assert len(routes) == 1
    assert routes[0]["osrm_duration_s"] == fastest["osrm_duration_s"]
    assert routes[0]["distance_mi"] == 518


def test_via_route_within_1_25x_is_kept():
    # 1.20× time and 1.11× distance: a real alternative, not a detour to drop.
    fastest = _route(8.98, 518, via="I-80")
    alternate = _route(8.98 * 1.20, 573, via="I-70")

    def fake_osrm(coords, alternatives):
        return [fastest] if len(coords) == 2 else [alternate]

    with mock.patch.object(clients, "_osrm", side_effect=fake_osrm):
        routes = clients.get_routes(DENVER, SALT_LAKE, wanted=3)

    assert len(routes) == 2
    assert routes[1]["distance_mi"] == 573


def test_weather_responses_are_cached_for_30_to_60_minutes():
    assert 30 * 60 <= clients.WEATHER_CACHE_SECONDS <= 60 * 60


def _photon_denver():
    return {
        "features": [
            {
                "properties": {
                    "name": "Denver",
                    "city": "Denver",
                    "state": "Colorado",
                    "country": "United States",
                },
                "geometry": {"coordinates": [-104.98, 39.74]},
            }
        ]
    }


def _open_meteo_geocode():
    return {
        "results": [
            {
                "name": "Denver",
                "admin1": "Colorado",
                "country": "United States",
                "latitude": 39.74,
                "longitude": -104.98,
            }
        ]
    }


def test_geocode_uses_photon_when_it_answers(monkeypatch):
    def fake_get(url, params, cache_seconds=600, headers=None):
        assert "photon" in url
        return _photon_denver()

    monkeypatch.setattr(clients, "_get_json", fake_get)
    places = clients.geocode("Denver")
    assert places == [{"label": "Denver, Colorado, United States", "lon": -104.98, "lat": 39.74}]


def test_geocode_falls_back_when_photon_refuses(monkeypatch):
    def fake_get(url, params, cache_seconds=600, headers=None):
        if "photon" in url:
            raise clients.UpstreamError(
                "Could not reach https://photon.komoot.io/api/: [Errno 111] Connection refused"
            )
        assert "geocoding-api.open-meteo.com" in url
        return _open_meteo_geocode()

    monkeypatch.setattr(clients, "_get_json", fake_get)
    places = clients.geocode("Denver")
    assert places[0]["label"] == "Denver, Colorado, United States"
    assert places[0]["lat"] == 39.74


def test_geocode_error_names_both_failures(monkeypatch):
    def fake_get(url, params, cache_seconds=600, headers=None):
        if "photon" in url:
            raise clients.UpstreamError("Could not reach photon: [Errno 111] Connection refused")
        raise clients.UpstreamError("geocoding returned 429: Daily API request limit exceeded")

    monkeypatch.setattr(clients, "_get_json", fake_get)
    with pytest.raises(clients.UpstreamError) as exc:
        clients.geocode("Denver")
    message = str(exc.value)
    assert "Place search is unavailable" in message
    assert "connection was refused" in message
    assert "daily request limit" in message


def _met_payload(when, wind=10, mm=2.54, symbol="rain", temp=8, six_hour=False):
    block = "next_6_hours" if six_hour else "next_1_hours"
    amount = mm * 6 if six_hour else mm
    return {
        "properties": {
            "timeseries": [
                {
                    "time": when,
                    "data": {
                        "instant": {"details": {"wind_speed": wind, "air_temperature": temp}},
                        block: {
                            "summary": {"symbol_code": symbol},
                            "details": {"precipitation_amount": amount},
                        },
                    },
                }
            ]
        }
    }


def test_met_rain_and_wind_use_the_risk_units():
    # 10 m/s -> mph, 2.54 mm of rain -> 0.1 inch. Snow stays dry.
    from datetime import datetime, timezone

    when = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
    out = clients.met_timeseries_to_hourly(
        _met_payload("2026-11-02T12:00:00Z"), when, when
    )
    assert out["times"] == ["2026-11-02T12:00"]
    assert out["wind_mph"][0] == pytest.approx(22.369, abs=0.01)
    assert out["rain_in"][0] == pytest.approx(0.1)
    assert out["snow_in"][0] == 0


def test_met_snow_depth_is_about_ten_times_the_water():
    from datetime import datetime, timezone

    when = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
    out = clients.met_timeseries_to_hourly(
        _met_payload("2026-11-02T12:00:00Z", symbol="heavysnow", temp=-4), when, when
    )
    assert out["rain_in"][0] == 0
    assert out["snow_in"][0] == pytest.approx(1.0)


def test_met_six_hour_step_is_spread_across_the_hour():
    from datetime import datetime, timedelta, timezone

    start = datetime(2026, 11, 5, 0, tzinfo=timezone.utc)
    out = clients.met_timeseries_to_hourly(
        _met_payload("2026-11-05T00:00:00Z", mm=2.54, six_hour=True),
        start,
        start + timedelta(hours=1),
    )
    assert out["times"] == ["2026-11-05T00:00", "2026-11-05T01:00"]
    assert out["rain_in"] == pytest.approx([0.1, 0.1])


def test_weather_falls_back_when_open_meteo_is_rate_limited(monkeypatch):
    from datetime import datetime, timezone

    calls = []

    def fake_get(url, params, cache_seconds=600, headers=None):
        calls.append((url, params))
        if "open-meteo.com" in url:
            raise clients.UpstreamError(
                "https://api.open-meteo.com/v1/forecast returned 429: Daily API request limit exceeded"
            )
        return _met_payload("2026-11-02T12:00:00Z")

    monkeypatch.setattr(clients, "_get_json", fake_get)
    when = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
    # More than 4 decimals would be rejected by MET Norway with a 403.
    out = clients.get_hourly_weather([(-104.984862, 39.73923641)], when, when)
    urls = [url for url, _params in calls]
    assert any("open-meteo.com" in url for url in urls)
    met_params = next(params for url, params in calls if "locationforecast" in url)
    assert met_params == {"lat": "39.7392", "lon": "-104.9849"}
    assert out[0]["rain_in"][0] == pytest.approx(0.1)


def test_weather_error_names_both_failures(monkeypatch):
    from datetime import datetime, timezone

    def fake_get(url, params, cache_seconds=600, headers=None):
        if "forecast" in url and "locationforecast" not in url:
            raise clients.UpstreamError("forecast returned 429: limit exceeded")
        raise clients.UpstreamError("Could not reach https://api.met.no: [Errno 111] Connection refused")

    monkeypatch.setattr(clients, "_get_json", fake_get)
    when = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
    with pytest.raises(clients.UpstreamError) as exc:
        clients.get_hourly_weather([(-104.98, 39.74)], when, when)
    message = str(exc.value)
    assert "Weather data is unavailable" in message
    assert "daily request limit" in message
    assert "connection was refused" in message
