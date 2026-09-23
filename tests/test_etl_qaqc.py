"""Unit tests for field-mapping and QA/QC logic (scope 6.5).

arcpy-free by construction: `li.etl` and `li.qaqc` keep every decision in pure
functions and let the arcpy half only execute them. These are the decisions —
whether a county is cleared to ingest, what maps to what, whether a feature
count identifies the layer we meant, how a zero land value is treated, whether
a check passes.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from li import config, etl, qaqc  # noqa: E402


# --------------------------------------------------------------------------
# Field mapping
# --------------------------------------------------------------------------

TARRANT_FIELDS = [
    "OBJECTID", "TAXPIN", "ACCOUNT", "OWNER_NAME", "SITUS_ADDR", "CITY",
    "LAND_ACRES", "LAND_SQFT", "LAND_VALUE", "IMPR_VALUE", "TOTAL_VALU",
    "YEAR_BUILT", "APPRAISEDV", "DESCR", "PARCELTYPE",
]


@pytest.fixture(scope="module")
def tarrant_cfg():
    return etl.county_config("S01", "tarrant")


def test_tarrant_maps_cleanly_against_the_real_field_list(tarrant_cfg):
    m = etl.resolve_field_mapping(tarrant_cfg, TARRANT_FIELDS)
    assert m.ok, f"unmapped: {m.missing_from_source}"
    assert m.mapping["acres_published"] == "LAND_ACRES"
    assert m.mapping["appraised_land_val"] == "LAND_VALUE"
    assert m.mapping["appraised_total_val"] == "TOTAL_VALU"
    # ACCOUNT is the unique key; TAXPIN is the abstract tract (98.44% unique)
    assert m.mapping["parcel_id"] == "ACCOUNT"
    assert m.mapping["alt_parcel_id"] == "TAXPIN"


def test_unavailable_fields_are_declared_not_silently_missing(tarrant_cfg):
    """Tarrant publishes no zoning or land use. That must be a recorded fact."""
    m = etl.resolve_field_mapping(tarrant_cfg, TARRANT_FIELDS)
    assert "zoning_code" in m.declared_unavailable
    assert "land_use_code" in m.declared_unavailable
    # ...and must not masquerade as a mapping failure
    assert not any("zoning_code" in s for s in m.missing_from_source)


def test_missing_source_field_is_reported_not_skipped():
    cfg = {"field_map": {"parcel_id": "TAXPIN", "appraised_land_val": "LAND_VAL"}}
    m = etl.resolve_field_mapping(cfg, TARRANT_FIELDS)   # LAND_VAL does not exist
    assert not m.ok
    assert any("LAND_VAL" in s for s in m.missing_from_source)


def test_field_matching_is_case_insensitive_but_records_source_spelling():
    cfg = {"field_map": {"parcel_id": "account", "alt_parcel_id": "TaxPin"}}
    m = etl.resolve_field_mapping(cfg, TARRANT_FIELDS)
    assert m.ok
    # Matched case-insensitively, but stored as the source spells it.
    assert m.mapping["parcel_id"] == "ACCOUNT"
    assert m.mapping["alt_parcel_id"] == "TAXPIN"


def test_account_is_the_unique_key_not_taxpin(tarrant_cfg):
    """Verified over a 20,000-record sample: ACCOUNT 100% unique, TAXPIN 98.44%.

    TAXPIN identifies the survey abstract tract, and one tract can hold several
    separately-appraised parcels - A1614-1C carries eight. Keying on it would
    have produced duplicate parcel_ids, which the QA check caught on the pilot.
    """
    assert tarrant_cfg["field_map"]["parcel_id"] == "ACCOUNT"
    assert tarrant_cfg["field_map"]["alt_parcel_id"] == "TAXPIN"


def test_unmapped_source_fields_are_listed(tarrant_cfg):
    m = etl.resolve_field_mapping(tarrant_cfg, TARRANT_FIELDS)
    assert "IMPR_VALUE" in m.unmapped_source_fields
    assert "ACCOUNT" not in m.unmapped_source_fields


def test_every_county_field_map_targets_real_parcel_fields():
    from li import gdb
    parcels = config.schema()["feature_classes"]["Parcels"]
    valid = {f["name"] for f in gdb.all_fields(parcels)} | etl.EXTRA_MAPPABLE
    s01 = next(s for s in config.sources()["sources"] if s["source_id"] == "S01")
    for county, cfg in (s01.get("counties") or {}).items():
        for schema_field in (cfg.get("field_map") or {}):
            assert schema_field in valid, f"{county}: {schema_field} is not a Parcels field"


# --------------------------------------------------------------------------
# Refusal to guess
# --------------------------------------------------------------------------

def test_verified_county_is_cleared(tarrant_cfg):
    etl.assert_ready_to_ingest(tarrant_cfg, "tarrant")      # must not raise


def test_unverified_county_is_refused():
    cfg = {"status": "skeleton", "endpoint": "https://x", "field_map": {"a": "b"}}
    with pytest.raises(etl.IngestRefused, match="not 'verified'"):
        etl.assert_ready_to_ingest(cfg, "dallas")


def test_unverified_county_can_be_forced_deliberately():
    cfg = {"status": "skeleton", "endpoint": "https://x", "field_map": {"a": "b"}}
    etl.assert_ready_to_ingest(cfg, "dallas", allow_unverified=True)


def test_county_without_endpoint_is_refused():
    with pytest.raises(etl.IngestRefused, match="endpoint"):
        etl.assert_ready_to_ingest({"status": "verified", "field_map": {"a": "b"}}, "x")


def test_county_without_field_map_is_refused():
    with pytest.raises(etl.IngestRefused, match="field_map"):
        etl.assert_ready_to_ingest({"status": "verified", "endpoint": "https://x"}, "x")


def test_unknown_county_raises_rather_than_returning_empty():
    with pytest.raises(etl.IngestRefused, match="no county entry"):
        etl.county_config("S01", "nowhere")


# --------------------------------------------------------------------------
# Feature-count sanity - the TADParcels / TCProperty trap
# --------------------------------------------------------------------------

def test_expected_count_accepts_the_real_layer():
    ok, msg = etl.feature_count_ok(758_633, 758_633, 5.0)
    assert ok and "within" in msg


def test_expected_count_tolerates_normal_drift():
    ok, _ = etl.feature_count_ok(770_000, 758_633, 5.0)   # +1.5%
    assert ok


def test_expected_count_rejects_the_lookalike_layer():
    """TCProperty has an identical 56-field schema but 110 features."""
    ok, msg = etl.feature_count_ok(110, 758_633, 5.0)
    assert not ok and "OUTSIDE" in msg


def test_expected_count_is_skipped_when_not_configured():
    ok, _ = etl.feature_count_ok(42, None)
    assert ok


# --------------------------------------------------------------------------
# D-008 land value and acreage
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (528_536.0, "Valued"),
    (0, "ZeroExempt"),
    (0.0, "ZeroExempt"),
    (None, "Missing"),
    (-1, "Invalid"),
    ("not a number", "Invalid"),
])
def test_land_value_classification(value, expected):
    assert etl.classify_land_value(value) == expected


def test_zero_land_value_is_never_treated_as_valued():
    """The whole point of D-008: zero is exempt land, not the cheapest land."""
    assert etl.classify_land_value(0) != "Valued"


def test_acreage_delta_basic():
    assert etl.acreage_delta_pct(100.0, 100.0) == 0.0
    assert etl.acreage_delta_pct(105.0, 100.0) == pytest.approx(5.0)
    assert etl.acreage_delta_pct(95.0, 100.0) == pytest.approx(5.0)


@pytest.mark.parametrize("geom,pub", [(None, 100.0), (100.0, None), (100.0, 0)])
def test_acreage_delta_is_none_when_undefined(geom, pub):
    assert etl.acreage_delta_pct(geom, pub) is None


# --------------------------------------------------------------------------
# Paging and provenance
# --------------------------------------------------------------------------

def test_paged_query_params_advance_the_offset():
    p0 = etl.paged_query_params(0, 1000, ["TAXPIN"])
    p1 = etl.paged_query_params(1000, 1000, ["TAXPIN"])
    assert p0["resultOffset"] == 0 and p1["resultOffset"] == 1000
    assert p0["resultRecordCount"] == 1000
    assert p0["returnGeometry"] == "true"


def test_registry_row_carries_required_provenance(tarrant_cfg):
    s01 = next(s for s in config.sources()["sources"] if s["source_id"] == "S01")
    row = etl.registry_row(s01, tarrant_cfg, datetime(2026, 9, 22))
    for key in ("source_id", "provider", "dataset", "url", "download_date",
                "license", "native_crs"):
        assert key in row
    assert row["source_id"] == "S01"
    assert row["native_crs"] == "3785"
    assert "tarrantcounty.com" in row["url"]


# --------------------------------------------------------------------------
# QA/QC evaluation
# --------------------------------------------------------------------------

def test_evaluate_max_mode():
    assert qaqc.evaluate(0, 0) == qaqc.PASS
    assert qaqc.evaluate(1, 0) == qaqc.FAIL
    assert qaqc.evaluate(1, 0, warn_only=True) == qaqc.WARN


def test_evaluate_min_mode():
    assert qaqc.evaluate(500, 100, mode="min") == qaqc.PASS
    assert qaqc.evaluate(50, 100, mode="min") == qaqc.FAIL


def test_evaluate_without_threshold_passes():
    assert qaqc.evaluate(999, None) == qaqc.PASS


def test_null_rate_counts_blank_strings_as_null():
    nulls, total, pct = qaqc.null_rate(["a", None, "", "   ", "b"])
    assert (nulls, total) == (3, 5)
    assert pct == pytest.approx(60.0)


def test_duplicate_keys_ignores_nulls():
    dups = qaqc.duplicate_keys(["A", "B", "A", None, None, "", "C"])
    assert dups == {"A": 2}


def test_domain_violations_allows_nulls():
    allowed = ["Confirmed", "Inferred", "Unzoned", "Unknown"]
    bad = qaqc.domain_violations(["Confirmed", None, "Industrial", "Industrial"], allowed)
    assert bad == {"Industrial": 2}


def test_out_of_range_flags_non_numeric():
    assert qaqc.out_of_range([0, 50, 100, None], 0, 100) == 0
    assert qaqc.out_of_range([-1, 101, "x"], 0, 100) == 3


def test_acreage_disagreements_uses_tolerance():
    pairs = [(100.0, 100.0), (110.0, 100.0), (100.0, None)]
    assert qaqc.acreage_disagreements(pairs, 5.0) == 1
    assert qaqc.acreage_disagreements(pairs, 15.0) == 0


def test_crs_match():
    assert qaqc.crs_matches(6584, 6584)
    assert not qaqc.crs_matches(3785, 6584)
    assert not qaqc.crs_matches(None, 6584)


def test_check_result_row_shape():
    r = qaqc.CheckResult("ING-CRS", "Parcels", "CRS", qaqc.PASS, 0, 0, "ok")
    row = r.as_row("20260922_1200_ingest")
    assert row["run_id"] == "20260922_1200_ingest"
    assert row["passed"] == 1
    assert set(row) == {"check_id", "run_id", "layer", "check_name", "result",
                        "affected_cnt", "threshold", "passed", "check_timestamp", "detail"}


def test_warning_does_not_count_as_passed():
    assert qaqc.CheckResult("X", "Parcels", "n", qaqc.WARN).passed == 0
    assert qaqc.CheckResult("X", "Parcels", "n", qaqc.SKIP).passed == 0


def test_parcel_check_plan_covers_the_section_10_checks():
    ids = {c["id"] for c in qaqc.parcel_check_plan()}
    for required in ("ING-CRS", "ING-GEOM-NULL", "ING-GEOM-INVALID",
                     "ING-DUP-KEY", "ING-COUNT"):
        assert required in ids


def test_hard_checks_are_not_warn_only():
    """CRS, null geometry and duplicate keys must be able to fail the run."""
    plan = {c["id"]: c for c in qaqc.parcel_check_plan()}
    for cid in ("ING-CRS", "ING-GEOM-NULL", "ING-DUP-KEY"):
        assert not plan[cid].get("warn_only", False), f"{cid} must be a hard failure"


def test_summarize_counts_by_result():
    rs = [qaqc.CheckResult("a", "L", "n", qaqc.PASS),
          qaqc.CheckResult("b", "L", "n", qaqc.FAIL),
          qaqc.CheckResult("c", "L", "n", qaqc.WARN)]
    s = qaqc.summarize(rs)
    assert s[qaqc.PASS] == 1 and s[qaqc.FAIL] == 1 and s[qaqc.WARN] == 1
