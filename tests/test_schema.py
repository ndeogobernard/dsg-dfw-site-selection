"""Schema and configuration integrity tests.

These run without arcpy so they can execute in GitHub Actions (scope 6.5).
They catch the class of error that is otherwise only discovered several
minutes into a geodatabase build: a field pointing at a domain that was never
declared, a relationship naming a feature class that does not exist, or
criteria.yaml drifting out of step with weights.json.

They also support acceptance criterion 13.5 - that the documented schema and
the delivered schema match.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from li import config, gdb  # noqa: E402

VALID_FIELD_TYPES = {"TEXT", "FLOAT", "DOUBLE", "SHORT", "LONG", "DATE", "BLOB", "GUID", "RASTER"}
VALID_GEOMETRIES = {"POINT", "MULTIPOINT", "POLYLINE", "POLYGON"}


@pytest.fixture(scope="module")
def schema():
    return config.schema()


@pytest.fixture(scope="module")
def datasets(schema):
    """Every named dataset in the schema: feature classes plus tables."""
    return {**schema.get("feature_classes", {}), **schema.get("tables", {})}


# --------------------------------------------------------------------------
# Weights
# --------------------------------------------------------------------------

def test_weight_scenarios_sum_to_one():
    sums = config.validate_weights()
    assert set(sums) == {"Balanced", "LaborFirst", "AccessFirst"}


def test_every_scenario_covers_every_criterion():
    criterion_ids = {c["id"] for c in config.criteria()["criteria"]}
    for scenario, weights in config.weights().items():
        assert set(weights) == criterion_ids, (
            f"{scenario} weights do not match the criteria defined in criteria.yaml"
        )


def test_weights_are_non_negative():
    for scenario, weights in config.weights().items():
        for criterion_id, weight in weights.items():
            assert weight >= 0, f"{scenario}/{criterion_id} has a negative weight"


# --------------------------------------------------------------------------
# Domains
# --------------------------------------------------------------------------

def test_domain_types_are_valid(schema):
    for name, spec in schema["domains"].items():
        assert spec["type"] in {"coded", "range"}, name
        assert spec.get("field_type", "TEXT").upper() in VALID_FIELD_TYPES, name
        if spec["type"] == "coded":
            assert spec.get("values"), f"{name} has no coded values"
        else:
            assert spec["min"] < spec["max"], f"{name} has an empty range"


def test_every_referenced_domain_exists(schema, datasets):
    declared = set(schema["domains"])
    for ds_name, spec in datasets.items():
        for field in gdb.all_fields(spec):
            domain = field.get("domain")
            if domain:
                assert domain in declared, (
                    f"{ds_name}.{field['name']} references undeclared domain '{domain}'"
                )


def test_domain_field_types_match_their_fields(schema, datasets):
    """A DOUBLE domain cannot be applied to a TEXT field."""
    domains = schema["domains"]
    for ds_name, spec in datasets.items():
        for field in gdb.all_fields(spec):
            domain = field.get("domain")
            if not domain:
                continue
            expected = domains[domain].get("field_type", "TEXT").upper()
            actual = field["type"].upper()
            assert expected == actual, (
                f"{ds_name}.{field['name']} is {actual} but domain "
                f"'{domain}' is {expected}"
            )


# --------------------------------------------------------------------------
# Fields
# --------------------------------------------------------------------------

def test_field_types_are_valid(datasets):
    for ds_name, spec in datasets.items():
        for field in gdb.all_fields(spec):
            assert field["type"].upper() in VALID_FIELD_TYPES, (
                f"{ds_name}.{field['name']} has unsupported type {field['type']}"
            )


def test_text_fields_declare_a_length(datasets):
    for ds_name, spec in datasets.items():
        for field in gdb.all_fields(spec):
            if field["type"].upper() == "TEXT":
                assert field.get("length"), (
                    f"{ds_name}.{field['name']} is TEXT with no length"
                )


def test_no_duplicate_field_names(datasets):
    for ds_name, spec in datasets.items():
        names = [f["name"].lower() for f in gdb.all_fields(spec)]
        assert len(names) == len(set(names)), f"{ds_name} has duplicate field names"


def test_geometry_types_are_valid(schema):
    for name, spec in schema["feature_classes"].items():
        assert spec["geometry"].upper() in VALID_GEOMETRIES, name


def test_feature_classes_reference_declared_datasets(schema):
    declared = set(schema["feature_datasets"])
    for name, spec in schema["feature_classes"].items():
        dataset = spec.get("dataset")
        if dataset:
            assert dataset in declared, f"{name} names undeclared dataset '{dataset}'"


# --------------------------------------------------------------------------
# Generated criterion fields
# --------------------------------------------------------------------------

def test_generated_fields_expand_to_expected_names(schema):
    """One raw and one scaled column per criterion, derived from criteria.yaml.

    Asserting a hard-coded 22 meant adding C12 broke this test rather than the
    thing it was meant to protect. The count now follows the criteria list, so
    the test fails only if the schema and the criteria genuinely disagree.
    """
    n = len(config.criteria()["criteria"])
    generated = gdb.expand_generated_fields(schema["feature_classes"]["SiteScores"])
    names = [f["name"] for f in generated]
    assert len(names) == 2 * n
    assert names[0] == "c01_raw"
    assert names[n - 1] == f"c{n:02d}_raw"
    assert names[n] == "c01_s"
    assert names[-1] == f"c{n:02d}_s"


def test_criteria_fields_match_generated_schema_fields(schema):
    """criteria.yaml field_raw/field_scaled must exist on SiteScores."""
    site_scores = schema["feature_classes"]["SiteScores"]
    available = {f["name"] for f in gdb.all_fields(site_scores)}
    for criterion in config.criteria()["criteria"]:
        assert criterion["field_raw"] in available, criterion["id"]
        assert criterion["field_scaled"] in available, criterion["id"]


def test_criteria_directions_are_valid(schema):
    allowed = set(schema["domains"]["dm_Direction"]["values"])
    for criterion in config.criteria()["criteria"]:
        assert criterion["direction"] in allowed, criterion["id"]


def test_criteria_ids_are_sequential():
    ids = [c["id"] for c in config.criteria()["criteria"]]
    assert ids == [f"C{i:02d}" for i in range(1, len(ids) + 1)]


# --------------------------------------------------------------------------
# Relationships, topology, attribute rules
# --------------------------------------------------------------------------

def test_relationship_endpoints_exist(schema, datasets):
    for rel in schema["relationships"]:
        assert rel["origin"] in datasets, f"{rel['name']}: origin {rel['origin']} missing"
        assert rel["destination"] in datasets, (
            f"{rel['name']}: destination {rel['destination']} missing"
        )


def test_relationship_keys_exist_on_both_sides(schema, datasets):
    for rel in schema["relationships"]:
        origin_fields = {f["name"] for f in gdb.all_fields(datasets[rel["origin"]])}
        dest_fields = {f["name"] for f in gdb.all_fields(datasets[rel["destination"]])}
        assert rel["primary_key"] in origin_fields, (
            f"{rel['name']}: primary key {rel['primary_key']} not on {rel['origin']}"
        )
        assert rel["foreign_key"] in dest_fields, (
            f"{rel['name']}: foreign key {rel['foreign_key']} not on {rel['destination']}"
        )


def test_relationship_names_are_unique(schema):
    names = [r["name"] for r in schema["relationships"]]
    assert len(names) == len(set(names))


def test_topology_references_existing_classes(schema):
    feature_classes = schema["feature_classes"]
    for topo in schema["topologies"]:
        assert topo["dataset"] in schema["feature_datasets"]
        for fc in topo["feature_classes"]:
            assert fc in feature_classes, f"{topo['name']} references missing {fc}"
            assert feature_classes[fc]["dataset"] == topo["dataset"], (
                f"{fc} must live in {topo['dataset']} to participate in {topo['name']}"
            )
        for rule in topo["rules"]:
            assert rule["origin"] in topo["feature_classes"]


def test_attribute_rules_reference_existing_tables_and_fields(schema, datasets):
    for rule in schema["attribute_rules"]:
        assert rule["table"] in datasets, f"{rule['name']}: {rule['table']} missing"
        assert rule["type"] in {"CALCULATION", "CONSTRAINT", "VALIDATION"}
        if rule["type"] == "CALCULATION":
            fields = {f["name"] for f in gdb.all_fields(datasets[rule["table"]])}
            assert rule["field"] in fields, (
                f"{rule['name']} calculates {rule['field']}, which is not on "
                f"{rule['table']}"
            )


def test_constraint_rules_declare_an_error_message(schema):
    for rule in schema["attribute_rules"]:
        if rule["type"] == "CONSTRAINT":
            assert rule.get("error_number"), rule["name"]
            assert rule.get("error_message"), rule["name"]


def test_subtype_field_is_integer(schema):
    """ArcGIS requires subtype fields to be SHORT or LONG."""
    for name, spec in schema["feature_classes"].items():
        field_name = spec.get("subtype_field")
        if not field_name:
            continue
        match = [f for f in gdb.all_fields(spec) if f["name"] == field_name]
        assert match, f"{name}: subtype field {field_name} is not declared"
        assert match[0]["type"].upper() in {"SHORT", "LONG"}, (
            f"{name}: subtype field {field_name} must be SHORT or LONG"
        )


def test_subtype_defaults_reference_real_fields(schema):
    for name, spec in schema["feature_classes"].items():
        fields = {f["name"] for f in gdb.all_fields(spec)}
        for label, sub in (spec.get("subtypes") or {}).items():
            for field_name in (sub.get("defaults") or {}):
                assert field_name in fields, f"{name}/{label}: {field_name} missing"


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------

def test_study_area_has_eleven_counties():
    """DFW-Arlington MSA, 2023 OMB delineation (Hood and Somervell excluded)."""
    counties = config.sources()["study_area"]["counties"]
    assert len(counties) == 11
    assert "Hood" not in counties
    assert "Somervell" not in counties


def test_source_ids_are_unique_and_sequential():
    ids = [s["source_id"] for s in config.sources()["sources"]]
    assert len(ids) == len(set(ids))
    assert ids == sorted(ids)


def test_sources_targeting_the_gdb_name_real_datasets(schema, datasets):
    rasters = {"Slope_pct", "LandCover_NLCD"}   # created by tools, not by the schema build
    for source in config.sources()["sources"]:
        target = source.get("target")
        if not target:
            continue
        for name in ([target] if isinstance(target, str) else target):
            assert name in datasets or name in rasters, (
                f"{source['source_id']} targets unknown dataset '{name}'"
            )


# --------------------------------------------------------------------------
# D-008 / D-009 / D-013 invariants
# --------------------------------------------------------------------------

def _parcels(schema):
    return schema["feature_classes"]["Parcels"]


def _parcel_field_names(schema):
    return {f["name"] for f in gdb.all_fields(_parcels(schema))}


def test_d008_parcels_carry_both_acreages(schema):
    """D-008 screens on CAD-published acreage; geometry acreage is kept beside it."""
    names = _parcel_field_names(schema)
    assert "acres" in names, "geometry-derived acreage missing"
    assert "acres_published" in names, "CAD-published acreage missing"
    assert "acres_delta_pct" in names, "acreage discrepancy field missing"


def test_d008_acreage_discrepancy_rule_exists(schema):
    rules = {r["name"]: r for r in schema["attribute_rules"]}
    rule = rules.get("calc_Parcel_AcresDelta")
    assert rule, "acreage-discrepancy rule missing"
    assert rule["field"] == "acres_delta_pct"
    assert "acres_published" in rule["script"]


def test_d008_land_value_flag_exists(schema):
    """A zero land value is exempt/ROW land, never silently treated as free."""
    assert "land_val_flag" in _parcel_field_names(schema)


def test_d009_zoning_confidence_domain(schema):
    dom = schema["domains"].get("dm_ZoningConfidence")
    assert dom, "dm_ZoningConfidence missing"
    assert set(dom["values"]) == {"Confirmed", "Inferred", "Unzoned", "Unknown"}


def test_d009_parcels_carry_zoning_confidence(schema):
    fields = {f["name"]: f for f in gdb.all_fields(_parcels(schema))}
    assert "zoning_confidence" in fields
    assert fields["zoning_confidence"]["domain"] == "dm_ZoningConfidence"


def test_d013_subtype_is_keyed_on_zoning_confidence(schema):
    """D-013 Q2: subtypes moved off land_use_class, which nothing populates."""
    spec = _parcels(schema)
    assert spec["subtype_field"] == "zoning_conf_st"
    assert set(spec["subtypes"]) == {"Confirmed", "Inferred", "Unzoned", "Unknown"}
    # Unknown is the default: a parcel is unknown until proven otherwise.
    unknown_code = spec["subtypes"]["Unknown"]["code"]
    assert spec["default_subtype"] == unknown_code


def test_d013_land_use_class_is_nullable(schema):
    """Retained as an attribute for counties that supply it - Tarrant does not."""
    fields = {f["name"]: f for f in gdb.all_fields(_parcels(schema))}
    assert "land_use_class" in fields
    assert fields["land_use_class"].get("nullable", True) is True


def test_d013_screening_has_no_industrial_zoning_gate():
    """Screening is physical/infrastructural only."""
    zoning = config.screening()["zoning"]
    assert zoning["hard_filter"] is False
    assert "eligible_classes" not in zoning, "industrial-zoning gate still present"
    assert set(zoning["never_excluded_confidences"]) == {"Inferred", "Unzoned", "Unknown"}


def test_d013_screening_keeps_every_physical_filter():
    s = config.screening()
    for key in ("min_acres", "max_sfha_pct", "max_floodway_pct", "max_wetland_pct",
                "max_mean_slope_pct", "max_developed_pct", "require_water_ccn",
                "require_sewer_ccn_or_within_miles", "max_truck_min_to_interchange"):
        assert key in s, f"physical filter {key} was dropped"


def test_d013_zoning_signal_criterion_exists():
    c12 = {c["id"]: c for c in config.criteria()["criteria"]}.get("C12")
    assert c12, "C12 zoning/entitlement signal missing"
    assert c12["direction"] == "Benefit"
    assert set(c12["tier_scores"]) == {"Confirmed", "Inferred", "Unzoned", "Unknown"}
    # Confidence must be monotonic: more certainty never scores worse.
    t = c12["tier_scores"]
    assert t["Confirmed"] > t["Inferred"] > t["Unzoned"] > t["Unknown"]


def test_c01_uses_transport_and_material_moving_only():
    """Recon 4.2: the C24010 parent lines would fold in production workers."""
    c01 = {c["id"]: c for c in config.criteria()["criteria"]}["C01"]
    v = c01["acs_variables"]
    assert v["occ_transp_matmov"] == ["C24010_036E", "C24010_037E",
                                      "C24010_072E", "C24010_073E"]
    for parent in ("C24010_034E", "C24010_070E"):
        assert parent not in v["occ_transp_matmov"], f"{parent} includes production"


def test_c09_derives_flood_fields_from_real_nfhl_names():
    """NFHL has no boolean SFHA field and no floodway field (recon 3)."""
    c09 = {c["id"]: c for c in config.criteria()["criteria"]}["C09"]
    sf = c09["source_fields"]
    assert sf["sfha"]["field"] == "SFHA_TF"
    assert sf["sfha"]["true_value"] == "T"
    assert sf["floodway"]["field"] == "ZONE_SUBTY"
    assert sf["floodway"]["value"].upper() == "FLOODWAY"


def test_s01_has_no_guessed_default_field_map():
    """The 11 CADs share no schema; a shared default is how wrong maps happen."""
    s01 = next(s for s in config.sources()["sources"] if s["source_id"] == "S01")
    assert "field_map" not in s01, "S01 still carries a shared default field_map"
    assert "counties" in s01


def test_tarrant_field_map_is_verified_and_complete():
    s01 = next(s for s in config.sources()["sources"] if s["source_id"] == "S01")
    t = s01["counties"]["tarrant"]
    assert t["status"] == "verified"
    fm = t["field_map"]
    for schema_field, cad_field in (("acres_published", "LAND_ACRES"),
                                    ("appraised_land_val", "LAND_VALUE"),
                                    ("appraised_total_val", "TOTAL_VALU"),
                                    ("parcel_id", "TAXPIN")):
        assert fm[schema_field] == cad_field
    # Fields verified absent must be declared, not silently unmapped.
    assert set(t["unavailable"]) >= {"zoning_code", "land_use_code"}


def test_county_field_maps_target_real_schema_fields(schema):
    """Every mapped key must be a field that actually exists on Parcels."""
    names = _parcel_field_names(schema) | {"alt_parcel_id", "city"}
    s01 = next(s for s in config.sources()["sources"] if s["source_id"] == "S01")
    for county, spec in s01["counties"].items():
        for schema_field in (spec.get("field_map") or {}):
            assert schema_field in names, f"{county}: {schema_field} not on Parcels"
