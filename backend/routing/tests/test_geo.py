import pytest

from routing.geo import (
    TRUCK_MAX_MPH,
    corridor_grid,
    dedupe_coords,
    haversine_mi,
    offset_point,
    sample_checkpoints,
    segment_profile,
)

DALLAS = (-96.797, 32.776)
HOUSTON = (-95.369, 29.760)


def test_haversine_known_distance():
    # straight-line Dallas -> Houston is about 225 miles
    assert haversine_mi(DALLAS, HOUSTON) == pytest.approx(225, abs=5)


def test_truck_speed_cap():
    # a 1-degree-of-latitude segment (~69 mi) that OSRM claims takes 30 min
    coords = [(0, 0), (0, 1)]
    miles, seconds = segment_profile(coords, osrm_durations=[1800])
    assert miles[0] / (seconds[0] / 3600) == pytest.approx(TRUCK_MAX_MPH)


def test_falls_back_when_annotations_dont_line_up():
    coords = [(0, 0), (0, 0.5), (0, 1)]
    miles, seconds = segment_profile(coords, osrm_durations=[1], osrm_total_s=7200)
    assert sum(seconds) == pytest.approx(7200)


def test_checkpoints_every_interval_plus_destination():
    coords = [(0, 0), (0, 1)]  # ~69 miles
    miles, seconds = segment_profile(coords, osrm_total_s=69.09 / 50 * 3600)
    cps = sample_checkpoints(coords, miles, seconds, interval_mi=25)
    assert [round(c["mile"]) for c in cps] == [0, 25, 50, 69]
    # time grows along the route
    assert all(a["offset_s"] < b["offset_s"] for a, b in zip(cps, cps[1:]))
    # interpolated position is in the right place
    assert cps[1]["lat"] == pytest.approx(25 / miles[0], rel=1e-3)


def test_bad_interval():
    with pytest.raises(ValueError):
        sample_checkpoints([(0, 0), (0, 1)], [69], [3600], 0)


def test_offset_point_is_off_the_line():
    p = offset_point(DALLAS, HOUSTON, 0.5, side_mi=30)
    mid = ((DALLAS[0] + HOUSTON[0]) / 2, (DALLAS[1] + HOUSTON[1]) / 2)
    assert haversine_mi(p, mid) == pytest.approx(30, rel=0.1)


def test_corridor_grid_respects_budget():
    route = [(-100 + i * 0.1, 35) for i in range(100)]
    pts, step = corridor_grid([route], max_points=50)
    assert 0 < len(pts) <= 50


def test_default_corridor_grid_stays_within_120():
    # A long haul. The default budget is what the weather call actually uses.
    route = [(-122 + i * 0.15, 37 + (i % 7) * 0.02) for i in range(120)]
    pts, _step = corridor_grid([route])
    assert 0 < len(pts) <= 120


def test_dedupe_coords_collapses_one_cell_and_remembers_the_index():
    unique, indexes = dedupe_coords([(0.0, 0.0), (0.01, -0.01), (1.0, 1.0)], step_deg=0.05)
    assert unique[0] == (0.0, 0.0)
    assert indexes == [0, 0, 1]
    assert len(unique) == 2
