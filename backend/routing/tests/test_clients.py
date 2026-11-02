"""Routing-client tests. OSRM is mocked; nothing here touches the network."""
from unittest import mock

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
