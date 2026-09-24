"""Unit tests for the Phase A screening rule engine (scope §5.1, D-013).

arcpy-free: `li.screening` keeps every threshold decision in pure functions and
lets the arcpy half only measure parcels. These test the decisions.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from li import config, screening  # noqa: E402


@pytest.fixture(scope="module")
def t():
    return screening.resolve_thresholds()


def parcel(**over):
    """A parcel that passes every filter, unless a test breaks one."""
    base = {
        "acres_published": 120.0,
        "floodway_pct": 0.0,
        "sfha_pct": 3.0,
        "wetland_pct": 1.0,
        "mean_slope_pct": 1.8,
        "developed_pct": 8.0,
        "water_ccn": 1,
        "interchange_miles": 2.5,
    }
    base.update(over)
    return base


# --------------------------------------------------------------------------
# Thresholds come from config, never from code
# --------------------------------------------------------------------------

def test_scope_default_thresholds_are_in_force(t):
    """Appendix B defaults, unchanged. This run must not be silently tightened."""
    assert t["min_acres"] == 80
    assert t["max_floodway_pct"] == 0
    assert t["max_sfha_pct"] == 20
    assert t["max_wetland_pct"] == 10
    assert t["max_mean_slope_pct"] == 5
    assert t["max_developed_pct"] == 30
    assert t["require_water_ccn"] is True
    assert t["max_truck_min_to_interchange"] == 15


def test_no_zoning_filter_in_the_chain(t):
    """D-013: screening is physical and infrastructural only."""
    keys = {f.key for f in screening.filter_order(t)}
    for forbidden in ("zoning_class", "zoning_confidence", "industrial"):
        assert forbidden not in keys
    assert t["zoning"]["hard_filter"] is False


def test_filters_run_acreage_first(t):
    """Acreage cuts 758,633 to under a thousand; everything else is spatial."""
    assert screening.filter_order(t)[0].key == "acres_published"


# --------------------------------------------------------------------------
# D-015 straight-line interchange approximation
# --------------------------------------------------------------------------

def test_interchange_radius_is_derived_not_typed(t):
    """15 min / 60 * 35 mph / 1.3 = 6.73 miles."""
    assert t["_derived_interchange_miles"] == pytest.approx(6.73, abs=0.01)


def test_circuity_shrinks_the_radius(t):
    """Roads do not run straight, so the straight-line radius must be SMALLER
    than the distance the drive itself covers - otherwise the screen admits
    parcels that cannot reach an interchange in time."""
    ip = t["interchange_proximity"]
    raw = t["max_truck_min_to_interchange"] / 60 * ip["assumed_speed_mph"]
    assert t["_derived_interchange_miles"] < raw
    assert ip["circuity_factor"] > 1.0


def test_interchange_is_straight_line_this_run(t):
    assert t["interchange_proximity"]["method"] == "straight_line"


# --------------------------------------------------------------------------
# D-016 sewer is NOT a hard filter this run
# --------------------------------------------------------------------------

def test_sewer_is_not_a_hard_filter():
    assert screening.sewer_is_a_filter() is False


def test_sewer_absence_never_drops_a_parcel(t):
    """A parcel with no sewer information at all must still pass."""
    status, _ = screening.evaluate(parcel(sewer_ccn=0, sewer_status=None), t)
    assert status == screening.PASS


def test_no_sewer_filter_in_the_chain(t):
    assert not any("sewer" in f.key.lower() for f in screening.filter_order(t))


def test_sewer_status_records_the_open_question():
    v = screening.sewer_status_value()
    assert "Unknown" in v and "D-016" in v


def test_water_ccn_is_still_a_hard_filter(t):
    assert any(f.key == "water_ccn" for f in screening.filter_order(t))
    status, reason = screening.evaluate(parcel(water_ccn=0), t)
    assert status == screening.FAIL
    assert "water CCN" in reason


# --------------------------------------------------------------------------
# Each filter rejects what it should
# --------------------------------------------------------------------------

@pytest.mark.parametrize("over,fragment", [
    ({"acres_published": 79.9}, "acreage"),
    ({"floodway_pct": 0.1}, "floodway"),
    ({"sfha_pct": 20.1}, "SFHA"),
    ({"wetland_pct": 10.1}, "wetland"),
    ({"mean_slope_pct": 5.1}, "slope"),
    ({"developed_pct": 30.1}, "developed"),
    ({"water_ccn": 0}, "water CCN"),
    ({"interchange_miles": 99.0}, "interchange"),
])
def test_each_filter_rejects(over, fragment, t):
    status, reason = screening.evaluate(parcel(**over), t)
    assert status == screening.FAIL
    assert fragment.lower() in reason.lower()


@pytest.mark.parametrize("over", [
    {"acres_published": 80.0},      # exactly at the threshold
    {"floodway_pct": 0.0},
    {"sfha_pct": 20.0},
    {"wetland_pct": 10.0},
    {"mean_slope_pct": 5.0},
    {"developed_pct": 30.0},
    {"interchange_miles": 6.73},
])
def test_boundary_values_pass(over, t):
    """Thresholds are inclusive; a parcel exactly at the limit is not rejected."""
    assert screening.evaluate(parcel(**over), t)[0] == screening.PASS


def test_clean_parcel_passes(t):
    assert screening.evaluate(parcel(), t) == (screening.PASS, "")


# --------------------------------------------------------------------------
# Missing data must not pass silently
# --------------------------------------------------------------------------

@pytest.mark.parametrize("missing", ["mean_slope_pct", "developed_pct"])
def test_unmeasurable_metric_is_review_not_pass(missing, t):
    """A raster that did not cover the parcel is not evidence of a gentle slope."""
    status, reason = screening.evaluate(parcel(**{missing: None}), t)
    assert status == screening.REVIEW
    assert "not measurable" in reason


def test_absent_overlap_is_genuinely_zero(t):
    """No intersecting flood polygon really does mean no flood coverage."""
    assert screening.evaluate(parcel(sfha_pct=None, wetland_pct=None), t)[0] == screening.PASS


def test_a_hard_failure_beats_a_review(t):
    """A parcel that fails outright is not rescued by an unmeasured metric."""
    status, reason = screening.evaluate(
        parcel(sfha_pct=90.0, mean_slope_pct=None), t)
    assert status == screening.FAIL
    assert "SFHA" in reason


def test_first_failing_rule_is_reported(t):
    """Attribution to one filter is what makes the funnel reconcile."""
    status, reason = screening.evaluate(
        parcel(acres_published=10, sfha_pct=90, wetland_pct=90), t)
    assert status == screening.FAIL
    assert "acreage" in reason.lower()


# --------------------------------------------------------------------------
# Funnel arithmetic
# --------------------------------------------------------------------------

def test_funnel_stages_reconcile(t):
    rows = [parcel(), parcel(acres_published=10), parcel(sfha_pct=90),
            parcel(water_ccn=0), parcel(interchange_miles=50)]
    steps = screening.funnel(rows, t)
    assert steps[0]["remaining"] == len(rows)
    for prev, cur in zip(steps, steps[1:]):
        assert cur["entering"] == prev["remaining"]
        assert cur["remaining"] == cur["entering"] - cur["removed"]
    assert steps[-1]["remaining"] == 1


def test_funnel_covers_every_filter(t):
    steps = screening.funnel([parcel()], t)
    assert len(steps) == len(screening.filter_order(t)) + 1


def test_funnel_removals_sum_to_the_drop(t):
    rows = [parcel() for _ in range(3)] + [parcel(acres_published=1),
                                           parcel(developed_pct=99)]
    steps = screening.funnel(rows, t)
    assert sum(s["removed"] for s in steps) == steps[0]["remaining"] - steps[-1]["remaining"]


def test_review_parcels_survive_the_funnel(t):
    """Review is not a rejection - those parcels reach CandidateSites."""
    steps = screening.funnel([parcel(mean_slope_pct=None)], t)
    assert steps[-1]["remaining"] == 1
