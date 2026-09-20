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
    generated = gdb.expand_generated_fields(schema["feature_classes"]["SiteScores"])
    names = [f["name"] for f in generated]
    assert len(names) == 22
    assert names[0] == "c01_raw"
    assert names[10] == "c11_raw"
    assert names[11] == "c01_s"
    assert names[21] == "c11_s"


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
