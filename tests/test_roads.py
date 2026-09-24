"""Unit tests for the OSM road attribution rules (scope §4.6, D-004, D-019).

arcpy-free. Every decision that turns an OSM tag into a routing attribute lives
in a pure function, so the modelling assumptions are testable in CI and a
silent change to any of them fails the build.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from li import config, roads  # noqa: E402


@pytest.fixture(scope="module")
def cfg():
    return roads.road_cfg()


@pytest.fixture(scope="module")
def net():
    return config.network()


# --------------------------------------------------------------------------
# D-004: the source and its extent
# --------------------------------------------------------------------------

def test_osm_is_the_primary_source(net):
    """D-004. S04 is OSM, S03 is RHiNo; RHiNo is kept but demoted."""
    assert net["build"]["source_priority"][0] == "S04"
    assert "S03" in net["build"]["source_priority"]


def test_extent_covers_more_than_texas(cfg):
    """The served set spans a 10-hour truck drive, not one state."""
    slugs = roads.state_slugs(cfg)
    assert "texas" in slugs
    assert len(slugs) >= 9
    for expected in ("oklahoma", "louisiana", "arkansas", "new-mexico"):
        assert expected in slugs


def test_licence_and_attribution_are_recorded(cfg):
    """ODbL obliges attribution on every published map; it must not be implicit."""
    assert "ODbL" in cfg["license"]
    assert "OpenStreetMap" in cfg["attribution"]


# --------------------------------------------------------------------------
# Connectivity - the one that breaks the network silently
# --------------------------------------------------------------------------

def test_connectivity_is_any_vertex(net):
    """OGR returns whole OSM ways, not ways split at junctions. END_POINT
    connectivity would join them only where one way happens to end on
    another's endpoint, shredding the network into disconnected pieces."""
    assert net["build"]["connectivity"] == "ANY_VERTEX"


# --------------------------------------------------------------------------
# Functional class
# --------------------------------------------------------------------------

@pytest.mark.parametrize("highway,fc", [
    ("motorway", 1), ("motorway_link", 1), ("trunk", 2), ("primary", 3),
    ("secondary", 4), ("tertiary", 5), ("unclassified", 6), ("residential", 7),
])
def test_func_class_map(highway, fc, cfg):
    assert roads.map_func_class(highway, cfg) == fc


@pytest.mark.parametrize("bad", ["footway", "cycleway", "path", "", None, "steps"])
def test_non_routable_classes_have_no_func_class(bad, cfg):
    """A pavement is not an edge. None is what makes the extractor drop it."""
    assert roads.map_func_class(bad, cfg) is None


def test_func_class_is_case_and_space_insensitive(cfg):
    assert roads.map_func_class("  Motorway ", cfg) == 1


# --------------------------------------------------------------------------
# One-way
# --------------------------------------------------------------------------

@pytest.mark.parametrize("raw,want", [
    ("yes", "FT"), ("true", "FT"), ("1", "FT"),
    ("-1", "TF"), ("reverse", "TF"),
    ("no", ""), ("false", ""), ("0", ""), (None, ""), ("", ""),
])
def test_oneway_map(raw, want, cfg):
    assert roads.map_oneway(raw, None, cfg) == want


def test_oneway_values_survived_yaml(cfg):
    """YAML 1.1 turns a bare `no` into boolean false. If these keys are not
    strings the mapping silently stops matching."""
    for k in cfg["oneway_map"]:
        assert isinstance(k, str), f"{k!r} is not a string - quote it in YAML"


def test_roundabout_is_oneway_without_the_tag(cfg):
    """OSM treats junction=roundabout as implying oneway."""
    assert roads.map_oneway(None, "roundabout", cfg) == "FT"


def test_explicit_two_way_beats_roundabout_inference(cfg):
    assert roads.map_oneway("no", "roundabout", cfg) == ""


def test_unknown_oneway_value_is_two_way(cfg):
    """An unrecognised value must not be guessed into a restriction."""
    assert roads.map_oneway("alternating", None, cfg) == ""


# --------------------------------------------------------------------------
# Speed
# --------------------------------------------------------------------------

@pytest.mark.parametrize("raw,want", [
    ("65 mph", 65.0), ("65mph", 65.0), ("45", 45.0), (" 30 MPH ", 30.0),
])
def test_parse_maxspeed_mph(raw, want):
    assert roads.parse_maxspeed(raw) == pytest.approx(want)


def test_parse_maxspeed_converts_metric():
    assert roads.parse_maxspeed("100 km/h") == pytest.approx(62.1, abs=0.1)


@pytest.mark.parametrize("raw", ["walk", "none", "signals", "DE:urban", "", None, "variable"])
def test_unparseable_maxspeed_is_none(raw):
    """OSM allows non-numeric speeds. Coercing them to a number would invent
    a posted limit; None sends the segment to the class default instead."""
    assert roads.parse_maxspeed(raw) is None


def test_posted_speed_wins_over_default(net):
    assert roads.speed_mph("55 mph", 1, net) == pytest.approx(55.0)


def test_default_speed_used_when_unposted(net):
    assert roads.speed_mph(None, 1, net) == pytest.approx(net["default_speeds_mph"][1])


def test_zero_speed_never_returned(net):
    """A zero speed would make travel time infinite and silently sever the
    network at that segment."""
    for fc in (1, 2, 3, 4, 5, 6, 7):
        assert roads.speed_mph("0", fc, net) > 0
        assert roads.truck_speed_mph(roads.speed_mph(None, fc, net), fc, net) > 0


# --------------------------------------------------------------------------
# D-019: truck speed is a separate cost, not an overwrite
# --------------------------------------------------------------------------

def test_truck_cost_is_a_separate_attribute(net):
    names = {a["name"] for a in net["attributes"]}
    assert {"Minutes", "TruckMinutes"} <= names
    assert net["travel_modes"]["Driving"]["impedance"] == "Minutes"
    assert net["travel_modes"]["Truck"]["impedance"] == "TruckMinutes"


def test_truck_speed_capped_by_band(net):
    caps = net["travel_modes"]["Truck"]["speed_caps_mph"]
    assert roads.truck_speed_mph(80, 1, net) == caps["freeway"]
    assert roads.truck_speed_mph(80, 3, net) == caps["arterial"]
    assert roads.truck_speed_mph(80, 7, net) == caps["local"]


def test_truck_speed_never_exceeds_posted(net):
    """A cap is a ceiling, not a target - a 30 mph street stays 30 for trucks."""
    assert roads.truck_speed_mph(30, 1, net) == 30


def test_truck_is_never_faster_than_driving(net):
    for fc in (1, 2, 3, 4, 5, 6, 7):
        base = roads.speed_mph(None, fc, net)
        assert roads.truck_speed_mph(base, fc, net) <= base


def test_truck_minutes_never_less_than_driving_minutes(net):
    for fc in (1, 2, 3, 4, 5, 6, 7):
        base = roads.speed_mph(None, fc, net)
        truck = roads.truck_speed_mph(base, fc, net)
        assert roads.minutes_for(10.0, truck) >= roads.minutes_for(10.0, base)


# --------------------------------------------------------------------------
# Truck restrictions
# --------------------------------------------------------------------------

@pytest.mark.parametrize("tags", [
    {"hgv": "no"}, {"hgv": "destination"}, {"hgv": "private"},
    {"motor_vehicle": "no"}, {"access": "private"},
])
def test_explicit_prohibition_restricts(tags, cfg, net):
    assert roads.truck_restricted(tags, 1, cfg, net) == 1


def test_restriction_values_survived_yaml(cfg):
    """`hgv: [no, ...]` unquoted parses as [False, ...] and stops matching the
    single commonest truck prohibition in OSM. Caught once; kept caught."""
    for tag, vals in cfg["truck_restriction_tags"].items():
        for v in vals:
            assert isinstance(v, str), f"{tag}: {v!r} is not a string - quote it"


def test_permissive_tag_does_not_restrict(cfg, net):
    assert roads.truck_restricted({"hgv": "yes"}, 1, cfg, net) == 0


def test_functional_class_fallback_restricts_local(cfg, net):
    """Where OSM is silent the class rule applies - a modelling assumption,
    recorded as one in D-004."""
    restricted = net["truck_restriction_rule"]["restricted_func_classes"]
    for fc in restricted:
        assert roads.truck_restricted({}, fc, cfg, net) == 1


def test_freeway_without_tags_is_not_restricted(cfg, net):
    assert roads.truck_restricted({}, 1, cfg, net) == 0


# --------------------------------------------------------------------------
# Misc
# --------------------------------------------------------------------------

@pytest.mark.parametrize("raw,want", [
    ("1", 1), ("-1", -1), ("+1", 1), ("0", 0), (None, 0), ("", 0), ("junk", 0),
])
def test_parse_layer(raw, want):
    assert roads.parse_layer(raw) == want


def test_minutes_for():
    assert roads.minutes_for(60.0, 60.0) == pytest.approx(60.0)
    assert roads.minutes_for(0.0, 60.0) == 0.0
    assert roads.minutes_for(10.0, 0.0) == 0.0


def test_where_clause_quotes_every_class(cfg):
    w = roads.where_clause(cfg["tiers"]["long_haul"]["highway_classes"])
    assert w.startswith("highway IN (")
    for c in cfg["tiers"]["long_haul"]["highway_classes"]:
        assert "'%s'" % c in w


def test_long_haul_is_a_subset_of_local(cfg):
    """The local tier adds street detail; it must not drop a class the
    long-haul tier relies on, or the study area would lose its motorways."""
    lh = set(cfg["tiers"]["long_haul"]["highway_classes"])
    lo = set(cfg["tiers"]["local"]["highway_classes"])
    assert lh <= lo


def test_local_tier_has_a_computed_bbox(cfg):
    bbox = cfg["tiers"]["local"]["bbox_wgs84"]
    assert len(bbox) == 4
    xmin, ymin, xmax, ymax = bbox
    assert xmin < xmax and ymin < ymax
    assert -100 < xmin < -94 and 30 < ymin < 35      # DFW, not somewhere else


# --------------------------------------------------------------------------
# Network dataset XML - the schema arcpy has no API for
# --------------------------------------------------------------------------

def test_every_attribute_gets_an_element(net):
    attrs, _ = roads.network_xml_sections(net)
    assert attrs.count("<EvaluatedNetworkAttribute ") == len(net["attributes"])
    for a in net["attributes"]:
        assert "<Name>%s</Name>" % a["name"] in attrs


def test_costs_and_restrictions_get_the_right_usage(net):
    attrs, _ = roads.network_xml_sections(net)
    import re
    got = dict(re.findall(r"<Name>(\w+)</Name>.*?<UsageType>(\w+)</UsageType>", attrs))
    for a in net["attributes"]:
        want = ("esriNAUTRestriction" if a["usage"].lower() == "restriction"
                else "esriNAUTCost")
        assert got[a["name"]] == want


def test_restrictions_are_boolean_costs_are_double(net):
    attrs, _ = roads.network_xml_sections(net)
    import re
    got = dict(re.findall(r"<Name>(\w+)</Name>.*?<DataType>(\w+)</DataType>", attrs))
    assert got["Minutes"] == "esriNADTDouble"
    assert got["Oneway"] == "esriNADTBoolean"
    assert got["TruckRestricted"] == "esriNADTBoolean"


def test_every_attribute_has_all_three_defaults(net):
    """A missing junction or turn default fails the build - or worse, does not."""
    _, assigns = roads.network_xml_sections(net)
    for a in net["attributes"]:
        for et in ("esriNETJunction", "esriNETEdge", "esriNETTurn"):
            frag = ("<NetworkAttributeName>%s</NetworkAttributeName>"
                    "<NetworkElementType>%s</NetworkElementType>" % (a["name"], et))
            assert frag in assigns, f"{a['name']} has no {et} default"


def test_both_directions_are_assigned(net):
    _, assigns = roads.network_xml_sections(net)
    for a in net["attributes"]:
        for d in ("esriNEDAlongDigitized", "esriNEDAgainstDigitized"):
            assert d in assigns


def test_oneway_directions_are_opposite(net):
    """Along-digitized is blocked by TF and against-digitized by FT. Swap them
    and the network still solves, with every one-way street reversed."""
    _, assigns = roads.network_xml_sections(net)
    import re
    pairs = re.findall(
        r"<NetworkAttributeName>Oneway</NetworkAttributeName>"
        r"<NetworkSourceName>\w+</NetworkSourceName>"
        r"<NetworkEvaluatorCLSID>[^<]+</NetworkEvaluatorCLSID>"
        r"<NetworkEdgeDirection>(\w+)</NetworkEdgeDirection>.*?"
        r"<Key>Expression</Key><Value xsi:type='xs:string'>([^<]*)</Value>", assigns)
    got = dict(pairs)
    assert got["esriNEDAlongDigitized"] == "!oneway! == 'TF'"
    assert got["esriNEDAgainstDigitized"] == "!oneway! == 'FT'"


def test_cost_expressions_reference_their_field(net):
    _, assigns = roads.network_xml_sections(net)
    for a in net["attributes"]:
        if a["usage"].lower() == "cost":
            assert "!%s!" % a["field"] in assigns


def test_driving_and_truck_read_different_cost_fields(net):
    """D-019. If both modes shared one column the labour-shed isochrones would
    quietly be computed at truck speeds."""
    by_name = {a["name"]: a for a in net["attributes"]}
    d = by_name[net["travel_modes"]["Driving"]["impedance"]]["field"]
    t = by_name[net["travel_modes"]["Truck"]["impedance"]]["field"]
    assert d != t


def test_patch_sets_connectivity_and_name(net):
    stub = ("<DENetworkDataset><CatalogPath>/FD=Transportation/ND=_ScratchND"
            "</CatalogPath><Name>_ScratchND</Name>"
            "<LogicalNetworkName>_ScratchND</LogicalNetworkName>"
            "<Key>ClassConnectivity</Key><Value xsi:type='xs:short'>1</Value>"
            "<EvaluatedNetworkAttributes xsi:type='t'></EvaluatedNetworkAttributes>"
            "<NetworkAssignments xsi:type='t'></NetworkAssignments>"
            "</DENetworkDataset>")
    out = roads.patch_template(stub, net, nd_name="RoadNetwork_ND")
    # esriNetworkEdgeConnectivityPolicy: 1 = end vertex, 2 = any vertex
    assert "<Key>ClassConnectivity</Key><Value xsi:type='xs:short'>2</Value>" in out
    assert "<Name>RoadNetwork_ND</Name>" in out
    assert "_ScratchND" not in out
    assert "<EvaluatedNetworkAttribute " in out
    assert "<NetworkAssignment " in out


def test_travel_mode_restrictions_exist_as_attributes(net):
    """A mode naming a restriction the network does not define fails at solve
    time, long after the build reported success."""
    names = {a["name"] for a in net["attributes"]}
    for mode in net["travel_modes"].values():
        for r in mode.get("restrictions", []):
            assert r in names
        assert mode["impedance"] in names
