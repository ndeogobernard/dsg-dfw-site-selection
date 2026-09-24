"""OSM road ingest and network-dataset construction (scope §4.6, D-004).

Split the same way the rest of this package is: every decision that turns an
OSM tag into a routing attribute is a pure function with no arcpy import, so it
can be tested in CI. The arcpy half only moves geometry.

D-004 chose OpenStreetMap over TxDOT RHiNo. The short version: RHiNo is Texas
only and its one-way field is 0% populated, and the served set this network has
to reach spans sixteen states.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

import requests

from . import config

log = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "dsg-dfw-site-selection/1.0 (portfolio study)"})


# ---------------------------------------------------------------------------
# Pure helpers - no arcpy, no network. These carry every modelling decision.
# ---------------------------------------------------------------------------

def road_cfg() -> dict:
    return config.sources()["road_network"]


def state_slugs(cfg: dict | None = None) -> list[str]:
    return [s["slug"] for s in (cfg or road_cfg())["states"]]


def extract_url(slug: str, cfg: dict | None = None) -> str:
    return (cfg or road_cfg())["base_url"].format(slug=slug)


def map_func_class(highway: str | None, cfg: dict | None = None) -> int | None:
    """OSM `highway=` to an FHWA-style functional class.

    Returning the FHWA numbering rather than inventing a new scheme is what
    lets `network.yaml`'s existing `default_speeds_mph` and
    `truck_restriction_rule` keep working unchanged after the source swap.
    """
    if not highway:
        return None
    return (cfg or road_cfg())["func_class_map"].get(str(highway).strip().lower())


def map_oneway(oneway: str | None, junction: str | None = None,
               cfg: dict | None = None) -> str:
    """OSM `oneway=` to the FT / TF / blank convention `network.yaml` expects.

    A roundabout is one-way whether or not anyone tagged it so; OSM treats
    `junction=roundabout` as implying it, and a network that ignores that will
    route the wrong way around every circle.
    """
    cfg = cfg or road_cfg()
    v = "" if oneway is None else str(oneway).strip().lower()
    if v in cfg["oneway_map"]:
        return cfg["oneway_map"][v]
    if v == "" and junction and str(junction).strip().lower() in (
            "roundabout", "circular"):
        return "FT"
    return ""


_SPEED = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(mph|km/h|kph|kmh)?\s*$", re.I)


def parse_maxspeed(raw: str | None) -> float | None:
    """OSM `maxspeed` to mph, or None when it is not a plain posted speed.

    OSM allows `walk`, `none`, `signals`, `DE:urban` and similar. Those are not
    numbers and must not be coerced into one - returning None sends the segment
    to the functional-class default, which is the honest answer.
    """
    if raw is None:
        return None
    m = _SPEED.match(str(raw))
    if not m:
        return None
    val = float(m.group(1))
    unit = (m.group(2) or "mph").lower()
    if unit in ("km/h", "kph", "kmh"):
        val *= 0.621371
    return round(val, 1) if val > 0 else None


def speed_mph(maxspeed: str | None, func_class: int | None,
              net: dict | None = None) -> float:
    """Posted speed where OSM has one, else the functional-class default."""
    net = net or config.network()
    posted = parse_maxspeed(maxspeed)
    if posted:
        return posted
    defaults = net["default_speeds_mph"]
    return float(defaults.get(func_class, defaults[max(defaults)]))


def truck_speed_mph(base_mph: float, func_class: int | None,
                    net: dict | None = None) -> float:
    """Scope §4.6 caps truck speed below general traffic, by class band."""
    net = net or config.network()
    caps = net["travel_modes"]["Truck"]["speed_caps_mph"]
    if func_class in (1, 2):
        cap = caps["freeway"]
    elif func_class in (3, 4):
        cap = caps["arterial"]
    else:
        cap = caps["local"]
    return min(float(base_mph), float(cap))


def truck_restricted(tags: dict, func_class: int | None,
                     cfg: dict | None = None, net: dict | None = None) -> int:
    """1 when a truck may not use this segment.

    Explicit OSM prohibitions win. Where OSM is silent - which is most of the
    network, on any free source - the functional-class fallback in
    `network.yaml` applies. That fallback is a modelling assumption, not a
    measurement, and D-004 says so plainly.
    """
    cfg = cfg or road_cfg()
    for tag, bad in cfg["truck_restriction_tags"].items():
        v = tags.get(tag)
        if v is not None and str(v).strip().lower() in [str(b).lower() for b in bad]:
            return 1
    net = net or config.network()
    if func_class in net["truck_restriction_rule"]["restricted_func_classes"]:
        return 1
    return 0


def parse_layer(raw: str | None) -> int:
    """OSM `layer=` to an integer z-level for grade separation.

    Without this every overpass becomes an intersection and the network grows
    interchanges that do not exist. OSM writes `1`, `-1`, occasionally `+1` or
    a range like `0;1`; anything unparseable is ground level, which is the
    common case and the safe default.
    """
    if raw in (None, ""):
        return 0
    s = str(raw).strip().split(";")[0].replace("+", "")
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return 0


def minutes_for(miles: float, mph: float) -> float:
    return 0.0 if mph <= 0 else (miles / mph) * 60.0


def where_clause(classes: Sequence[str]) -> str:
    """OGR SQL restricting an OSM `lines` layer to routable highway classes."""
    vals = ",".join("'%s'" % c.replace("'", "''") for c in classes)
    return "highway IN (%s)" % vals


def local_only_classes(cfg: dict | None = None) -> list[str]:
    """The classes the local tier must add, excluding what long-haul covers.

    The two tiers overlap by design in the config - `local` declares the full
    detail the study area needs, which necessarily includes motorways. But the
    long-haul tier already covers the whole state, so extracting those classes
    again inside the MSA duplicates them: 121,147 OSM ways appeared in both
    tiers before this. Duplicate coincident edges do not break a solve, they
    just quietly double the network there and create parallel paths between the
    same junctions.

    Subtracting here rather than in the config keeps `local.highway_classes`
    readable as a statement of intent.
    """
    cfg = cfg or road_cfg()
    lh = set(cfg["tiers"]["long_haul"]["highway_classes"])
    return [c for c in cfg["tiers"]["local"]["highway_classes"] if c not in lh]


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_extracts(dest: Path | str | None = None, slugs: Iterable[str] | None = None,
                      cfg: dict | None = None) -> list[Path]:
    """Fetch the Geofabrik state extracts, resuming any partial file.

    3.8 GB over sixteen files. A failed byte here costs a re-download, so the
    size is checked against Content-Length and a short file is refetched rather
    than silently handed to the extractor as a truncated PBF.
    """
    cfg = cfg or road_cfg()
    dest = Path(dest or (Path(config.paths()["raw_dir"]) / "osm"))
    dest.mkdir(parents=True, exist_ok=True)
    slugs = list(slugs or state_slugs(cfg))
    out: list[Path] = []

    for i, slug in enumerate(slugs, 1):
        url = extract_url(slug, cfg)
        path = dest / ("%s-latest.osm.pbf" % slug)
        head = _SESSION.head(url, allow_redirects=True, timeout=120)
        want = int(head.headers.get("content-length", 0))

        if path.exists() and want and path.stat().st_size == want:
            log.info("  [%2d/%d] %-14s cached %.0f MB", i, len(slugs), slug, want / 1e6)
            out.append(path)
            continue

        t0 = time.time()
        with _SESSION.get(url, stream=True, timeout=1800) as r:
            r.raise_for_status()
            tmp = path.with_suffix(".part")
            got = 0
            with open(tmp, "wb") as fh:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    fh.write(chunk)
                    got += len(chunk)
            tmp.replace(path)
        if want and got != want:
            raise RuntimeError("%s: got %d bytes, expected %d" % (slug, got, want))
        log.info("  [%2d/%d] %-14s %.0f MB in %.0fs", i, len(slugs), slug,
                 got / 1e6, time.time() - t0)
        out.append(path)

    total = sum(p.stat().st_size for p in out)
    log.info("  %d extracts, %.1f GB total", len(out), total / 1e9)
    return out


# ---------------------------------------------------------------------------
# Extraction - OSM PBF to a projected GeoPackage, via GDAL
# ---------------------------------------------------------------------------

_OUT_FIELDS = [
    ("road_id", "str", 64), ("name", "str", 150), ("func_class", "int", 0),
    ("speed_mph", "int", 0), ("oneway", "str", 2), ("truck_restrict", "int", 0),
    ("lanes", "int", 0), ("minutes", "float", 0), ("truck_speed_mph", "int", 0),
    ("truck_minutes", "float", 0), ("miles", "float", 0), ("source_id", "str", 10),
]


def _as_int(v):
    try:
        return int(float(str(v).split(";")[0]))
    except (TypeError, ValueError):
        return None


def extract_state(pbf, out_gpkg, classes, bbox_wgs84=None, layer_name="roads",
                  cfg=None, net=None, target_crs=None):
    """Filter one OSM extract to routable roads and write it projected.

    Two passes, both cheap. GDAL's `VectorTranslate` does the reading, the
    attribute filter and the reprojection in C++; Python then walks the much
    smaller result and computes the routing attributes.

    Iterating the `lines` layer directly does not work on a state-sized PBF.
    The OSM driver accumulates features across all five of its layers as it
    streams the file, and reading one layer to the end makes the others
    overflow - GDAL raises "Too many features have accumulated in points
    layer" and tells you to use interleaved reading, which in turn requires
    iterating the DATASOURCE rather than the layer. `VectorTranslate` sidesteps
    the whole question.

    Output is a GeoPackage rather than a direct geodatabase insert because a
    row-by-row `arcpy.da.InsertCursor` runs at a few hundred rows a second -
    fine for 758k parcels overnight, hopeless for millions of road segments.
    The geodatabase gets one bulk append at the end.
    """
    from osgeo import gdal, ogr

    cfg = cfg or road_cfg()
    net = net or config.network()
    target_crs = int(target_crs or config.schema()["meta"]["crs"])
    conf = Path(cfg.get("osmconf", "config/osmconf.ini")).resolve()
    if not conf.exists():
        raise RuntimeError("osmconf.ini not found at %s - the routing tags "
                           "would silently be missing" % conf)

    gdal.UseExceptions()
    gdal.SetConfigOption("OSM_CONFIG_FILE", str(conf))
    gdal.SetConfigOption("OGR_INTERLEAVED_READING", "YES")

    out_gpkg = Path(out_gpkg)
    out_gpkg.parent.mkdir(parents=True, exist_ok=True)
    if out_gpkg.exists():
        out_gpkg.unlink()

    t0 = time.time()
    opts = gdal.VectorTranslateOptions(
        format="GPKG", layers=["lines"], layerName=layer_name,
        where=where_clause(classes), dstSRS="EPSG:%d" % target_crs,
        reproject=True, geometryType="LINESTRING", explodeCollections=True,
        spatFilter=tuple(bbox_wgs84) if bbox_wgs84 else None,
        spatSRS="EPSG:4326" if bbox_wgs84 else None)
    gdal.VectorTranslate(str(out_gpkg), str(pbf), options=opts)
    t_read = time.time() - t0

    # Second pass: add the routing columns and fill them.
    ds = ogr.Open(str(out_gpkg), 1)
    lyr = ds.GetLayerByName(layer_name)
    if lyr is None:
        raise RuntimeError("%s produced no `%s` layer" % (pbf, layer_name))
    have = {lyr.GetLayerDefn().GetFieldDefn(i).GetName()
            for i in range(lyr.GetLayerDefn().GetFieldCount())}
    for nm, kind, width in _OUT_FIELDS:
        if nm in have:
            continue
        fd = ogr.FieldDefn(nm, {"str": ogr.OFTString, "int": ogr.OFTInteger,
                                "float": ogr.OFTReal}[kind])
        if width:
            fd.SetWidth(width)
        lyr.CreateField(fd)

    # READ first, WRITE second, and never both at once.
    #
    # Modifying a layer while iterating it is not safe on a GeoPackage: the
    # iteration is a SQLite cursor, and committing mid-loop invalidates it.
    # Doing that silently restarted this pass every 250,000 rows, so Texas ran
    # for half an hour without ever finishing instead of six minutes. The bug
    # is invisible in a small file - a 28k-row state completes before the first
    # commit - which is exactly why it reached a 326k-row one.
    plan = []
    skipped = 0
    for feat in lyr:
        hw = feat.GetFieldAsString("highway") or None
        fc = map_func_class(hw, cfg)
        geom = feat.GetGeometryRef()
        # A `highway` tag on a closed way with area=yes is a pedestrian plaza,
        # not an edge; routing across one is meaningless.
        is_area = (feat.GetFieldAsString("area") or "").strip().lower() in (
            "yes", "true", "1")
        feet = geom.Length() if geom is not None else 0.0
        if fc is None or is_area or feet <= 0:
            plan.append((feat.GetFID(), None))
            skipped += 1
            continue

        miles = feet / 5280.0
        tags = {k: (feat.GetFieldAsString(k) or None)
                for k in ("hgv", "motor_vehicle", "access")}
        mph = speed_mph(feat.GetFieldAsString("maxspeed") or None, fc, net)
        tmph = truck_speed_mph(mph, fc, net)
        plan.append((feat.GetFID(), {
            "road_id": str(feat.GetFieldAsString("osm_id") or "")[:64],
            "func_class": fc,
            "speed_mph": int(round(mph)),
            "oneway": map_oneway(feat.GetFieldAsString("oneway") or None,
                                 feat.GetFieldAsString("junction") or None, cfg),
            "truck_restrict": truck_restricted(tags, fc, cfg, net),
            "lanes": _as_int(feat.GetFieldAsString("lanes") or None),
            "minutes": minutes_for(miles, mph),
            "truck_speed_mph": int(round(tmph)),
            "truck_minutes": minutes_for(miles, tmph),
            "miles": miles,
            "source_id": cfg["source_id"],
        }))
    t_read2 = time.time()

    kept = 0
    lyr.StartTransaction()
    for fid, vals in plan:
        if vals is None:
            lyr.DeleteFeature(fid)
            continue
        feat = lyr.GetFeature(fid)
        for k, v in vals.items():
            if v is not None:
                feat.SetField(k, v)
        lyr.SetFeature(feat)
        feat = None
        kept += 1
    lyr.CommitTransaction()
    ds = None
    log.info("      %s: %d rows scanned, %d written, %.0fs read / %.0fs write",
             layer_name, len(plan), kept, t_read2 - t0 - t_read,
             time.time() - t_read2)

    log.info("    %-14s kept %7d, dropped %6d  (read %.0fs, attrs %.0fs)",
             Path(pbf).stem.split("-")[0], kept, skipped, t_read,
             time.time() - t0 - t_read)
    return {"pbf": str(pbf), "gpkg": str(out_gpkg), "layer": layer_name,
            "kept": kept, "skipped": skipped}


def extract_all(cfg=None, net=None, out_dir=None, slugs=None):
    """Run both tiers: long-haul across every state, local over the study area.

    Returns one result dict per GeoPackage produced.
    """
    cfg = cfg or road_cfg()
    out_dir = Path(out_dir or (Path(config.paths()["interim_dir"]) / "osm"))
    raw = Path(config.paths()["raw_dir"]) / "osm"
    results = []

    lh = cfg["tiers"]["long_haul"]
    for slug in (slugs or state_slugs(cfg)):
        pbf = raw / ("%s-latest.osm.pbf" % slug)
        if not pbf.exists():
            raise RuntimeError("missing extract %s - run --download-only first" % pbf)
        results.append(extract_state(
            pbf, out_dir / ("%s_longhaul.gpkg" % slug), lh["highway_classes"],
            layer_name="roads", cfg=cfg, net=net))

    lo = cfg["tiers"]["local"]
    local_classes = local_only_classes(cfg)
    for slug in lo.get("states", ["texas"]):
        pbf = raw / ("%s-latest.osm.pbf" % slug)
        results.append(extract_state(
            pbf, out_dir / ("%s_local.gpkg" % slug), local_classes,
            bbox_wgs84=lo["bbox_wgs84"], layer_name="roads", cfg=cfg, net=net))

    log.info("  extracted %d layers, %d segments total",
             len(results), sum(r["kept"] for r in results))
    return results


# ---------------------------------------------------------------------------
# Load into the geodatabase
# ---------------------------------------------------------------------------

def _require_arcpy():
    try:
        import arcpy  # noqa: F401
    except ImportError as exc:                                  # pragma: no cover
        raise RuntimeError("this step needs arcpy") from exc


def load_roads(gdb=None, gpkgs=None, run_id="", cfg=None, truncate=True):
    """Bulk-append the extracted GeoPackages into Transportation/Roads.

    One `Append` per GeoPackage rather than a row-by-row cursor. The parcel
    pilot measured `arcpy.da.InsertCursor` at a few hundred rows a second,
    which would take days at this volume.
    """
    _require_arcpy()
    import arcpy
    from osgeo import ogr

    cfg = cfg or road_cfg()
    gdb = gdb or config.paths()["gdb"]
    dest = gdb + "\\Transportation\\Roads"
    gpkgs = [Path(p) for p in (gpkgs or sorted(
        (Path(config.paths()["interim_dir"]) / "osm").glob("*.gpkg")))]
    gpkgs = [p for p in gpkgs if not p.name.startswith("_")]
    if not gpkgs:
        raise RuntimeError("no extracted GeoPackages found - run --extract-only")

    arcpy.env.overwriteOutput = True
    if truncate and int(arcpy.management.GetCount(dest)[0]):
        arcpy.management.TruncateTable(dest)
        log.info("  Roads truncated")

    t0, loaded = time.time(), 0
    for i, p in enumerate(gpkgs, 1):
        # Confirm the layer has rows before handing it to Append - an empty
        # source appends cleanly and silently, which is how a missing state
        # would go unnoticed until a route failed to solve.
        ds = ogr.Open(str(p))
        lyr = ds.GetLayerByName("roads")
        n_src = lyr.GetFeatureCount() if lyr is not None else 0
        ds = None
        if n_src == 0:
            log.warning("  [%2d/%d] %-28s EMPTY - skipped", i, len(gpkgs), p.stem)
            continue

        arcpy.management.Append(str(p) + "\\main.roads", dest, "NO_TEST")
        loaded += n_src
        log.info("  [%2d/%d] %-28s +%s  (%.0fs)", i, len(gpkgs), p.stem,
                 format(n_src, ","), time.time() - t0)

    n = int(arcpy.management.GetCount(dest)[0])
    log.info("  Roads: %s features (%s appended) in %.0fs",
             format(n, ","), format(loaded, ","), time.time() - t0)
    if n != loaded:
        log.warning("  Roads holds %d rows but %d were appended", n, loaded)
    return {"target": "Roads", "loaded": n, "sources": len(gpkgs)}


# ---------------------------------------------------------------------------
# Network dataset
# ---------------------------------------------------------------------------
#
# arcpy can CREATE a network dataset and BUILD it, but it has no API for
# defining cost attributes, restrictions or evaluators. The supported route is
# `CreateNetworkDatasetFromTemplate`, which takes the ND schema as XML. So the
# pipeline creates a throwaway ND, exports Esri's own template, patches the
# attribute and connectivity sections, and recreates from the patched XML.
#
# Patching Esri's export rather than hand-authoring the document is deliberate:
# the namespaces, ClassIDs and DSIDs are environment-specific, and every
# evaluator CLSID below was read out of that export rather than looked up, so
# there is nothing here that was guessed.

# Read from Esri's own template export, not from documentation.
_EVAL_CONSTANT = "{318C4B91-F5D2-467A-996C-0AB51B0D8FF2}"
_EVAL_EXPRESSION = "{68055FC4-37D5-4BD0-81A5-CD177A29759C}"

# esriNetworkEdgeConnectivityPolicy: 1 = end vertex, 2 = any vertex.
_CONN = {"END_POINT": 1, "ANY_VERTEX": 2}


def _prop(key, value, xstype):
    return ("<PropertySetProperty xsi:type='typens:PropertySetProperty'>"
            "<Key>%s</Key><Value xsi:type='xs:%s'>%s</Value>"
            "</PropertySetProperty>" % (key, xstype, value))


def _propset(props):
    return ("<NetworkEvaluatorData xsi:type='typens:PropertySet'>"
            "<PropertyArray xsi:type='typens:ArrayOfPropertySetProperty'>"
            + "".join(props) +
            "</PropertyArray></NetworkEvaluatorData>")


def _attribute_xml(aid, name, units, datatype, usage):
    return ("<EvaluatedNetworkAttribute xsi:type='typens:EvaluatedNetworkAttribute'>"
            "<ID>%d</ID><Name>%s</Name><Units>%s</Units>"
            "<DataType>%s</DataType><UsageType>%s</UsageType>"
            "<UserData xsi:nil='true'/><UseByDefault>false</UseByDefault>"
            "<AttributeParameters xsi:type='typens:ArrayOfNetworkAttributeParameter'>"
            "</AttributeParameters><TimeAware>false</TimeAware>"
            "</EvaluatedNetworkAttribute>" % (aid, name, units, datatype, usage))


def _default_assignment(name, element_type, boolean=False):
    """Every attribute needs a default for junctions, edges and turns.

    Without them the build fails, and a restriction with no junction default
    is the kind of omission that produces a network which solves but routes
    through turns it should not.
    """
    if boolean:
        val = _prop("ConstantValue", "false", "boolean")
    else:
        val = _prop("ConstantValue", "0", "double")
    return ("<NetworkAssignment xsi:type='typens:NetworkAssignment'>"
            "<IsDefault>true</IsDefault><ID>-1</ID>"
            "<NetworkAttributeName>%s</NetworkAttributeName>"
            "<NetworkElementType>%s</NetworkElementType>"
            "<NetworkEvaluatorCLSID>%s</NetworkEvaluatorCLSID>"
            "<NetworkEdgeDirection>esriNEDNone</NetworkEdgeDirection>"
            "%s</NetworkAssignment>"
            % (name, element_type, _EVAL_CONSTANT,
               _propset([_prop("Version", "1", "short"), val])))


def _expression_assignment(name, source, direction, expression):
    return ("<NetworkAssignment xsi:type='typens:NetworkAssignment'>"
            "<IsDefault>false</IsDefault><ID>-1</ID>"
            "<NetworkAttributeName>%s</NetworkAttributeName>"
            "<NetworkSourceName>%s</NetworkSourceName>"
            "<NetworkEvaluatorCLSID>%s</NetworkEvaluatorCLSID>"
            "<NetworkEdgeDirection>%s</NetworkEdgeDirection>"
            "%s</NetworkAssignment>"
            % (name, source, _EVAL_EXPRESSION, direction,
               _propset([_prop("Version", "2", "short"),
                         _prop("Expression", expression, "string"),
                         _prop("PreLogic", "", "string"),
                         _prop("Language", "Python", "string")])))


def network_xml_sections(net=None, source="Roads"):
    """Build the attribute and assignment XML for the network dataset.

    Pure string assembly - no arcpy - so the modelling can be asserted in CI.
    """
    net = net or config.network()
    attrs, assigns = [], []

    specs = []
    for aid, a in enumerate(net["attributes"], start=1):
        is_restriction = a["usage"].lower() == "restriction"
        specs.append((aid, a, is_restriction))
        attrs.append(_attribute_xml(
            aid, a["name"], a.get("units", "Unknown"),
            "esriNADTBoolean" if is_restriction else "esriNADTDouble",
            "esriNAUTRestriction" if is_restriction else "esriNAUTCost"))

    for _, a, is_restriction in specs:
        name, field = a["name"], a["field"]
        for et in ("esriNETJunction", "esriNETEdge", "esriNETTurn"):
            assigns.append(_default_assignment(name, et, boolean=is_restriction))

        if name == "Oneway":
            # A one-way street is passable along the digitized direction and
            # blocked against it - so the two directions get OPPOSITE tests.
            # Getting this backwards yields a network that still solves, just
            # with every one-way street reversed.
            assigns.append(_expression_assignment(
                name, source, "esriNEDAlongDigitized", "!%s! == 'TF'" % field))
            assigns.append(_expression_assignment(
                name, source, "esriNEDAgainstDigitized", "!%s! == 'FT'" % field))
        elif is_restriction:
            expr = "!%s! == 1" % field
            assigns.append(_expression_assignment(
                name, source, "esriNEDAlongDigitized", expr))
            assigns.append(_expression_assignment(
                name, source, "esriNEDAgainstDigitized", expr))
        else:
            expr = "!%s!" % field
            assigns.append(_expression_assignment(
                name, source, "esriNEDAlongDigitized", expr))
            assigns.append(_expression_assignment(
                name, source, "esriNEDAgainstDigitized", expr))

    return ("".join(attrs), "".join(assigns))


def patch_template(xml_text, net=None, nd_name=None, source="Roads"):
    """Rewrite Esri's exported ND template with our attributes and connectivity."""
    net = net or config.network()
    nd_name = nd_name or net["build"]["nd_name"]
    attrs, assigns = network_xml_sections(net, source)

    out = re.sub(r"<EvaluatedNetworkAttributes[^>]*>.*?</EvaluatedNetworkAttributes>",
                 "<EvaluatedNetworkAttributes xsi:type='typens:ArrayOfEvaluatedNetworkAttribute'>"
                 + attrs + "</EvaluatedNetworkAttributes>", xml_text, flags=re.S)
    out = re.sub(r"<NetworkAssignments[^>]*>.*?</NetworkAssignments>",
                 "<NetworkAssignments xsi:type='typens:ArrayOfNetworkAssignment'>"
                 + assigns + "</NetworkAssignments>", out, flags=re.S)

    conn = _CONN[net["build"]["connectivity"]]
    out = re.sub(r"(<Key>ClassConnectivity</Key><Value xsi:type='xs:short'>)\d+(</Value>)",
                 r"\g<1>%d\g<2>" % conn, out)

    for tag in ("Name", "LogicalNetworkName"):
        out = re.sub(r"<%s>[^<]*</%s>" % (tag, tag),
                     "<%s>%s</%s>" % (tag, nd_name, tag), out, count=1)
    out = re.sub(r"(<CatalogPath>/FD=[^/]+/ND=)[^<]*(</CatalogPath>)",
                 r"\g<1>%s\g<2>" % nd_name, out)
    return out


def build_network(gdb=None, run_id="", net=None, keep_xml=True):
    """Create RoadNetwork_ND from Roads and build it."""
    _require_arcpy()
    import arcpy

    net = net or config.network()
    gdb = gdb or config.paths()["gdb"]
    fd = gdb + "\\" + net["build"]["dataset"]
    nd_name = net["build"]["nd_name"]
    nd = fd + "\\" + nd_name
    scratch = fd + "\\_ScratchND"
    arcpy.env.overwriteOutput = True

    n_roads = int(arcpy.management.GetCount(gdb + "\\Transportation\\Roads")[0])
    if n_roads == 0:
        raise RuntimeError("Roads is empty - a network built on it would solve "
                           "nothing and report no error")
    log.info("=" * 68)
    log.info("build %s from %s road segments", nd_name, format(n_roads, ","))

    for p in (nd, scratch):
        if arcpy.Exists(p):
            arcpy.management.Delete(p)

    t0 = time.time()
    arcpy.na.CreateNetworkDataset(fd, "_ScratchND", ["Roads"], "NO_ELEVATION")
    xml_path = Path(config.paths()["interim_dir"]) / ("%s_template.xml" % nd_name)
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    if xml_path.exists():
        xml_path.unlink()
    arcpy.na.CreateTemplateFromNetworkDataset(scratch, str(xml_path))
    arcpy.management.Delete(scratch)

    patched = patch_template(xml_path.read_text(encoding="utf-8"), net, nd_name)
    xml_path.write_text(patched, encoding="utf-8")
    log.info("  template patched: %d attributes, connectivity %s",
             len(net["attributes"]), net["build"]["connectivity"])

    arcpy.na.CreateNetworkDatasetFromTemplate(str(xml_path), fd)
    log.info("  %s created in %.0fs", nd_name, time.time() - t0)

    if net["build"].get("build_after_create", True):
        t1 = time.time()
        arcpy.na.BuildNetwork(nd)
        log.info("  network built in %.0fs", time.time() - t1)

    d = arcpy.Describe(nd)
    got = {a.name: a.usageType for a in d.attributes}
    log.info("  attributes: %s", ", ".join("%s(%s)" % (k, v) for k, v in got.items()))
    want = {a["name"] for a in net["attributes"]}
    missing = want - set(got)
    if missing:
        raise RuntimeError("network dataset is missing %s" % sorted(missing))

    if not keep_xml:
        xml_path.unlink()
    return {"nd": nd, "segments": n_roads, "attributes": sorted(got),
            "template": str(xml_path)}


def travel_mode(name, net=None):
    """Build an arcpy.nax TravelMode from network.yaml.

    The ND itself carries no named travel modes. Constructing them here keeps
    the impedance, the restrictions and the U-turn policy in config where the
    rest of the project's parameters live, rather than baked into a binary
    geodatabase where a reader cannot see them.
    """
    _require_arcpy()
    import arcpy
    import json

    net = net or config.network()
    m = net["travel_modes"][name]
    spec = {
        "name": name,
        "type": "AUTOMOBILE" if name == "Driving" else "TRUCK",
        "impedanceAttributeName": m["impedance"],
        "timeAttributeName": m["time_attribute"],
        "distanceAttributeName": m["distance_attribute"],
        "restrictionAttributeNames": list(m.get("restrictions", [])),
        "attributeParameterValues": [],
        "uTurnAtJunctions": ("esriNFSBAllowBacktrack"
                             if m.get("uturn_policy") == "ALLOW_UTURNS"
                             else "esriNFSBNoBacktrack"),
        "useHierarchy": False,
        "simplificationTolerance": 0,
        "simplificationToleranceUnits": "esriUnknownUnits",
        "outputGeometryPrecision": 0,
        "outputGeometryPrecisionUnits": "esriUnknownUnits",
        "timeAttributeUnits": "esriNAUMinutes",
        "distanceAttributeUnits": "esriNAUMiles",
        "description": "",
        "id": name,
    }
    return arcpy.nax.TravelMode(json.dumps(spec))


# ---------------------------------------------------------------------------
# Route validation (scope §14)
# ---------------------------------------------------------------------------

def validate_routes(gdb=None, net=None, mode="Driving"):
    """Solve known city-pair routes and compare against reference figures.

    This is a smoke test for the network, not an accuracy certification. It is
    looking for the failures that are otherwise invisible:

      * a network that does not connect at all - the solve fails outright;
      * one-way logic inverted, or speeds in the wrong units - times come out
        wildly wrong rather than slightly wrong;
      * a missing state - the out-of-state routes cannot be reached, while the
        in-state ones still look perfect.

    Four of the seven references cross a state line for that last reason.
    """
    _require_arcpy()
    import arcpy

    net = net or config.network()
    gdb = gdb or config.paths()["gdb"]
    nd = gdb + "\\" + net["build"]["dataset"] + "\\" + net["build"]["nd_name"]
    spec = net["validation_routes"]
    tol = float(spec["tolerance_pct"])
    target_crs = int(config.schema()["meta"]["crs"])
    sr_in = arcpy.SpatialReference(4326)
    sr_out = arcpy.SpatialReference(target_crs)

    tm = travel_mode(mode, net)
    results = []
    log.info("=" * 68)
    log.info("route validation - %s mode, tolerance +/-%.0f%%", mode, tol)
    log.info("  %-26s %9s %9s %9s %9s  %s",
             "route", "miles", "ref", "minutes", "ref", "verdict")

    for spec_route in spec["routes"]:
        rt = arcpy.nax.Route(nd)
        rt.travelMode = tm
        rt.timeUnits = arcpy.nax.TimeUnits.Minutes
        rt.distanceUnits = arcpy.nax.DistanceUnits.Miles
        rt.routeShapeType = arcpy.nax.RouteShapeType.NoGeometry

        with rt.insertCursor(arcpy.nax.RouteInputDataType.Stops,
                             ["SHAPE@", "Name"]) as cur:
            for label, lonlat in (("from", spec_route["from"]),
                                  ("to", spec_route["to"])):
                pt = arcpy.PointGeometry(arcpy.Point(*lonlat), sr_in).projectAs(sr_out)
                cur.insertRow([pt, label])

        solved = rt.solve()
        if not solved.solveSucceeded:
            msg = "; ".join(str(m) for m in solved.solverMessages(
                arcpy.nax.MessageSeverity.All))[:160]
            log.warning("  %-26s %9s %9s %9s %9s  FAIL  %s",
                        spec_route["name"], "-", spec_route["ref_miles"],
                        "-", spec_route["ref_minutes"], msg)
            results.append({"name": spec_route["name"], "solved": False,
                            "miles": None, "minutes": None, "message": msg})
            continue

        miles = minutes = None
        with solved.searchCursor(arcpy.nax.RouteOutputDataType.Routes,
                                 ["Total_Miles", "Total_Minutes"]) as c:
            for row in c:
                miles, minutes = float(row[0]), float(row[1])

        dm = 100.0 * (miles - spec_route["ref_miles"]) / spec_route["ref_miles"]
        dt = 100.0 * (minutes - spec_route["ref_minutes"]) / spec_route["ref_minutes"]
        ok = abs(dm) <= tol and abs(dt) <= tol
        log.info("  %-26s %9.1f %9s %9.1f %9s  %s (%+.0f%% mi, %+.0f%% min)",
                 spec_route["name"], miles, spec_route["ref_miles"],
                 minutes, spec_route["ref_minutes"],
                 "ok  " if ok else "OFF ", dm, dt)
        results.append({"name": spec_route["name"], "solved": True,
                        "miles": round(miles, 1), "minutes": round(minutes, 1),
                        "ref_miles": spec_route["ref_miles"],
                        "ref_minutes": spec_route["ref_minutes"],
                        "pct_miles": round(dm, 1), "pct_minutes": round(dt, 1),
                        "within_tolerance": ok})

    n_ok = sum(1 for r in results if r.get("within_tolerance"))
    n_solved = sum(1 for r in results if r["solved"])
    log.info("  %d/%d solved, %d/%d within tolerance",
             n_solved, len(results), n_ok, len(results))
    return {"mode": mode, "solved": n_solved, "within_tolerance": n_ok,
            "total": len(results), "routes": results}
