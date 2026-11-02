"""Tests for the risk rules. These were written before risk.py.

The table in the brief has shared edges (e.g. rain 0.25 sits in both
"Moderate" and "High"). We resolve every shared edge upwards: a value that
touches the next band's lower bound belongs to that band. The tests below
pin that down so nobody "fixes" it by accident.
"""
import pytest

from routing.risk import (
    HIGH,
    LOW,
    MODERATE,
    NO_TRAVEL,
    SEVERE,
    classify_checkpoint,
    classify_rain,
    classify_snow,
    classify_wind,
    recommend,
    summarize_route,
)


@pytest.mark.parametrize(
    "mph,expected",
    [
        (0, LOW),
        (24.9, LOW),
        (25, MODERATE),
        (34.9, MODERATE),
        (35, HIGH),
        (44.9, HIGH),
        (45, SEVERE),
        (54.9, SEVERE),
        (55, NO_TRAVEL),
        (80, NO_TRAVEL),
    ],
)
def test_wind_bands(mph, expected):
    assert classify_wind(mph) == expected


@pytest.mark.parametrize(
    "inches,expected",
    [
        (0, LOW),
        (0.09, LOW),
        (0.10, MODERATE),
        (0.25, HIGH),
        (0.49, HIGH),
        (0.50, SEVERE),
        (1.00, SEVERE),  # the brief says "> 1.00" for No Travel, so 1.00 is still Severe
        (1.01, NO_TRAVEL),
    ],
)
def test_rain_bands(inches, expected):
    assert classify_rain(inches) == expected


@pytest.mark.parametrize(
    "inches,expected",
    [
        (0.4, LOW),
        (0.5, MODERATE),
        (1.0, HIGH),
        (2.0, SEVERE),
        (3.0, SEVERE),
        (3.1, NO_TRAVEL),
    ],
)
def test_snow_bands(inches, expected):
    assert classify_snow(inches) == expected


def test_worst_condition_wins():
    # calm wind, light snow, heavy rain -> the rain decides
    result = classify_checkpoint(wind_mph=5, rain_in=0.6, snow_in=0.6, load_lb=10_000)
    assert result["level"] == SEVERE
    assert result["driver"] == "rain"


class TestLoadRules:
    def test_55_mph_is_no_travel_even_when_empty(self):
        assert classify_checkpoint(55, 0, 0, load_lb=0)["level"] == NO_TRAVEL

    def test_45_mph_heavy_load_is_no_travel(self):
        assert classify_checkpoint(46, 0, 0, load_lb=30_001)["level"] == NO_TRAVEL

    def test_45_mph_at_exactly_30k_is_only_severe(self):
        # "> 30,000 lb" is strict
        assert classify_checkpoint(46, 0, 0, load_lb=30_000)["level"] == SEVERE

    def test_35_mph_very_heavy_load_bumps_to_severe(self):
        result = classify_checkpoint(36, 0, 0, load_lb=40_001)
        assert result["level"] == SEVERE
        assert result["load_rule"] is not None

    def test_35_mph_light_load_stays_high(self):
        assert classify_checkpoint(36, 0, 0, load_lb=20_000)["level"] == HIGH


def _cp(mile, level):
    return {"mile": mile, "risk": {"level": level}}


class TestSummarize:
    def test_segment_takes_worse_end(self):
        # 0 ---- 10 ---- 20, the middle checkpoint is severe so both
        # segments touching it count as severe miles.
        cps = [_cp(0, LOW), _cp(10, SEVERE), _cp(20, LOW)]
        s = summarize_route(cps)
        assert s["miles_by_level"]["severe"] == pytest.approx(20)
        assert s["miles_by_level"]["low"] == pytest.approx(0)

    def test_average_is_distance_weighted(self):
        cps = [_cp(0, LOW), _cp(30, LOW), _cp(40, HIGH)]
        s = summarize_route(cps)
        # 30 mi at 0 and 10 mi at 2 -> 20 / 40 = 0.5
        assert s["avg_risk"] == pytest.approx(0.5)


def _route(rid, severe=0, high=0, avg=0.0, duration=3600, no_travel=0):
    return {
        "id": rid,
        "duration_s": duration,
        "summary": {
            "miles_by_level": {
                "low": 0,
                "moderate": 0,
                "high": high,
                "severe": severe,
                "no_travel": no_travel,
            },
            "avg_risk": avg,
        },
    }


class TestRecommend:
    def test_fewest_severe_miles_first(self):
        routes = [_route("a", severe=10, duration=100), _route("b", severe=0, duration=9999)]
        assert recommend(routes)["id"] == "b"

    def test_then_high_miles(self):
        routes = [_route("a", high=20), _route("b", high=5)]
        assert recommend(routes)["id"] == "b"

    def test_then_average_risk(self):
        routes = [_route("a", avg=1.2), _route("b", avg=0.4)]
        assert recommend(routes)["id"] == "b"

    def test_then_time(self):
        routes = [_route("a", duration=5000), _route("b", duration=4000)]
        assert recommend(routes)["id"] == "b"

    def test_denver_slc_shape_prefers_the_lowest_average_risk(self):
        # No High, Severe, or No Travel miles. B is slower than A but calmer,
        # so the spec order picks B.
        routes = [
            _route("A", avg=0.096, duration=8.98 * 3600),
            _route("B", avg=0.0, duration=9.71 * 3600),
            _route("C", avg=0.091, duration=9.97 * 3600),
        ]
        assert recommend(routes)["id"] == "B"

    def test_avg_risk_equal_at_3_decimals_falls_through_to_time(self):
        # 0.0964 and 0.0956 are both 0.096 at 3 decimals. That is float noise,
        # so the shorter trip wins. A real hundredth still would not.
        routes = [
            _route("A", avg=0.0964, duration=8.98 * 3600),
            _route("B", avg=0.0956, duration=9.71 * 3600),
        ]
        assert round(0.0964, 3) == round(0.0956, 3) == 0.096
        assert recommend(routes)["id"] == "A"

    def test_no_travel_beats_everything(self):
        # A route that crosses a No Travel zone should never be recommended
        # over one that does not, even if it is "only" a mile of it.
        routes = [_route("a", no_travel=1), _route("b", severe=50, high=50)]
        assert recommend(routes)["id"] == "b"

    def test_empty(self):
        assert recommend([]) is None


def test_reason_names_lowest_average_risk():
    from routing.planner import _explain

    routes = [
        _route("A", avg=0.096, duration=8.98 * 3600),
        _route("B", avg=0.0, duration=9.71 * 3600),
        _route("C", avg=0.091, duration=9.97 * 3600),
    ]
    best = recommend(routes)
    assert _explain(best, routes) == (
        "Route B is recommended because it has the lowest average weather risk."
    )


def test_reason_uses_duration_when_average_risk_matches():
    from routing.planner import _explain

    routes = [
        _route("A", avg=0.0964, duration=8.98 * 3600),
        _route("B", avg=0.0956, duration=9.71 * 3600),
    ]
    best = recommend(routes)
    assert _explain(best, routes) == (
        "Route A is recommended because weather risk is similar and it is the fastest."
    )
