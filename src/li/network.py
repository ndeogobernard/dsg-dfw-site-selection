"""Service areas and OD matrices on RoadNetwork_ND (scope §5.2).

Everything here needs arcpy and a built network dataset. The decisions that can
be made without one - which breaks, which cutoffs, which mode - live in
`config/network.yaml` and are read, never hard-coded.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from . import config
from .roads import na_params, total_field

log = logging.getLogger(__name__)


def _nd(gdb, net):
    return gdb + "\\" + net["build"]["dataset"] + "\\" + net["build"]["nd_name"]


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def candidate_points(gdb, where="1=1"):
    """Candidate centroids as (cand_id, PointGeometry).

    The centroid of a parcel is not necessarily inside it, and for the
    corridor-shaped parcels D-017 turned up it frequently is not. `labelPoint`
    is guaranteed to fall within the polygon, so the network locates the
    facility on the parcel rather than on whatever happens to lie at the
    centre of its bounding shape.
    """
    import arcpy

    out = []
    fc = gdb + "\\Analysis\\CandidateSites"
    with arcpy.da.SearchCursor(fc, ["cand_id", "SHAPE@"], where) as c:
        for cid, shp in c:
            if shp is None:
                continue
            out.append((cid, arcpy.PointGeometry(shp.labelPoint,
                                                 shp.spatialReference)))
    return out


def store_points(gdb, where="1=1"):
    import arcpy

    out = []
    fc = gdb + "\\Market\\Stores_DSG"
    with arcpy.da.SearchCursor(fc, ["store_id", "SHAPE@"], where) as c:
        for sid, shp in c:
            if shp is not None:
                out.append((sid, shp))
    return out


# ---------------------------------------------------------------------------
# Served set - scope §2.2
# ---------------------------------------------------------------------------

def compute_served_set(gdb=None, run_id="", net=None):
    """Flag stores within a 10-hour truck drive of the MSA centroid.

    Scope §2.2 defines the served set from the MSA CENTROID, not from each
    candidate. That matters: it keeps the store set fixed across all 138
    candidates, so every candidate is scored against the same demand points and
    the OD matrix is comparable between them. Deriving it per candidate would
    let a site look good by serving fewer stores.
    """
    import arcpy

    net = net or config.network()
    gdb = gdb or config.paths()["gdb"]
    src = config.sources()
    cutoff = float(net["od_matrices"]["stores"]["cutoff_min"])
    mode = net["od_matrices"]["stores"]["mode"]
    centre = src["study_area"]["msa_centroid_wgs84"]
    target_crs = int(config.schema()["meta"]["crs"])

    stores = store_points(gdb)
    if not stores:
        raise RuntimeError("Stores_DSG is empty - run the store ingest first")

    log.info("=" * 68)
    log.info("served set: %s within %.0f min (%s) of the MSA centroid",
             format(len(stores), ","), cutoff, mode)

    p = na_params(mode, net)
    arcpy.env.overwriteOutput = True
    arcpy.CheckOutExtension("Network")
    lyr = arcpy.na.MakeODCostMatrixLayer(
        in_network_dataset=_nd(gdb, net),
        out_network_analysis_layer="served_od",
        impedance_attribute=p["impedance"],
        default_cutoff=cutoff,
        accumulate_attribute_name=p["accumulate"],
        UTurn_policy=p["uturn"],
        restriction_attribute_name=p["restrictions"],
        output_path_shape="NO_LINES").getOutput(0)
    sub = arcpy.na.GetNAClassNames(lyr)

    pt_fc = arcpy.management.CreateFeatureclass(
        "in_memory", "msa_centroid", "POINT",
        spatial_reference=arcpy.SpatialReference(target_crs))[0]
    arcpy.management.AddField(pt_fc, "Name", "TEXT", field_length=40)
    pt = arcpy.PointGeometry(arcpy.Point(*centre),
                             arcpy.SpatialReference(4326)).projectAs(
                                 arcpy.SpatialReference(target_crs))
    with arcpy.da.InsertCursor(pt_fc, ["SHAPE@", "Name"]) as cur:
        cur.insertRow([pt, "MSA_CENTROID"])

    arcpy.na.AddLocations(lyr, sub["Origins"], pt_fc, "Name Name #",
                          "5000 Meters", append="CLEAR")
    arcpy.na.AddLocations(lyr, sub["Destinations"],
                          gdb + "\\Market\\Stores_DSG", "Name store_id #",
                          "5000 Meters", append="CLEAR")
    arcpy.management.Delete(pt_fc)
    arcpy.na.Solve(lyr, "SKIP")

    f_time = total_field(p["time_attribute"])
    f_dist = total_field(p["distance_attribute"])
    reached = {}
    lines = lyr.listLayers(sub["ODLines"])[0]
    with arcpy.da.SearchCursor(lines, ["Name", f_time, f_dist]) as c:
        for nm, minutes, miles in c:
            # classic OD names each line "<origin> - <destination>"
            sid = str(nm).split(" - ", 1)[-1]
            if minutes is not None:
                reached[sid] = (float(minutes), float(miles))

    editor = arcpy.da.Editor(gdb)
    editor.startEditing(False, False)
    editor.startOperation()
    try:
        with arcpy.da.UpdateCursor(gdb + "\\Market\\Stores_DSG",
                                   ["store_id", "served_flag"]) as c:
            for row in c:
                row[1] = 1 if row[0] in reached else 0
                c.updateRow(row)
        editor.stopOperation()
        editor.stopEditing(True)
    except Exception:
        editor.abortOperation()
        editor.stopEditing(False)
        raise

    # StoreServiceSet is the run-stamped record of WHICH stores were served and
    # how far away they were (scope §5.2, tool 7). Stores_DSG.served_flag is the
    # current state; this table is the history, so a later run with different
    # speeds or a bigger store set can be compared against this one.
    ss = gdb + "\\StoreServiceSet"
    editor = arcpy.da.Editor(gdb)
    editor.startEditing(False, False)
    editor.startOperation()
    try:
        with arcpy.da.InsertCursor(
                ss, ["run_id", "store_id", "served_flag", "truck_minutes"]) as ic:
            for sid, _ in stores:
                hit = reached.get(sid)
                ic.insertRow([run_id, sid, 1 if hit else 0,
                              hit[0] if hit else None])
        editor.stopOperation()
        editor.stopEditing(True)
    except Exception:
        editor.abortOperation()
        editor.stopEditing(False)
        raise

    times = sorted(v[0] for v in reached.values())
    log.info("  served %d of %d stores", len(reached), len(stores))
    if times:
        log.info("  truck minutes from centroid: min %.0f  median %.0f  max %.0f",
                 times[0], times[len(times) // 2], times[-1])
    return {"stores": len(stores), "served": len(reached),
            "unreached": len(stores) - len(reached), "cutoff_min": cutoff,
            "reached": reached}


# ---------------------------------------------------------------------------
# Service areas - scope §5.2
# ---------------------------------------------------------------------------

def build_service_areas(gdb=None, run_id="", mode="Driving", net=None):
    """Isochrones around candidate sites, batched for memory."""
    import arcpy

    net = net or config.network()
    gdb = gdb or config.paths()["gdb"]
    spec = net["service_areas"][mode]
    breaks = [float(b) for b in spec["breaks_min"]]
    batch = int(net["service_areas"].get("batch_size", 50))
    dest = gdb + "\\Analysis\\ServiceAreas_%s" % mode

    cands = candidate_points(gdb)
    if not cands:
        raise RuntimeError("no candidate sites")

    log.info("=" * 68)
    log.info("service areas: %s mode, breaks %s min, %d facilities in batches of %d",
             mode, breaks, len(cands), batch)

    arcpy.env.overwriteOutput = True
    if int(arcpy.management.GetCount(dest)[0]):
        editor = arcpy.da.Editor(gdb)
        editor.startEditing(False, False)
        editor.startOperation()
        arcpy.management.DeleteRows(dest)
        editor.stopOperation()
        editor.stopEditing(True)

    p = na_params(mode, net)
    sa_cfg = net["service_areas"]
    poly_type = {"STANDARD": "DETAILED_POLYS",
                 "GENERALIZED": "SIMPLE_POLYS"}[spec["polygon_detail"]]
    trim = str(spec["polygon_trim_distance"])
    arcpy.CheckOutExtension("Network")

    lyr = arcpy.na.MakeServiceAreaLayer(
        in_network_dataset=_nd(gdb, net),
        out_network_analysis_layer="sa_%s" % mode,
        impedance_attribute=p["impedance"],
        travel_from_to="TRAVEL_FROM",
        default_break_values=" ".join(str(int(b)) for b in breaks),
        polygon_type=poly_type,
        merge=sa_cfg["merge"],
        nesting_type=sa_cfg["nesting"],
        line_type="NO_LINES",
        accumulate_attribute_name=p["accumulate"],
        UTurn_policy=p["uturn"],
        restriction_attribute_name=p["restrictions"],
        polygon_trim="TRIM_POLYS",
        poly_trim_value=trim).getOutput(0)
    sub = arcpy.na.GetNAClassNames(lyr)
    written, failed, t0 = 0, [], time.time()

    for bi, group in enumerate(_chunks(cands, batch), 1):
        fac = arcpy.management.CreateFeatureclass(
            "in_memory", "fac_%d" % bi, "POINT",
            spatial_reference=arcpy.SpatialReference(
                int(config.schema()["meta"]["crs"])))[0]
        arcpy.management.AddField(fac, "Name", "TEXT", field_length=64)
        with arcpy.da.InsertCursor(fac, ["SHAPE@", "Name"]) as cur:
            for cid, pt in group:
                cur.insertRow([pt, cid])
        arcpy.na.AddLocations(lyr, sub["Facilities"], fac, "Name Name #",
                              "5000 Meters", append="CLEAR")
        arcpy.management.Delete(fac)

        try:
            arcpy.na.Solve(lyr, "SKIP")
        except Exception as exc:
            failed.extend(cid for cid, _ in group)
            log.warning("  batch %d failed: %s", bi, str(exc)[:200])
            continue

        polys = lyr.listLayers(sub["SAPolygons"])[0]
        editor = arcpy.da.Editor(gdb)
        editor.startEditing(False, False)
        editor.startOperation()
        try:
            with arcpy.da.InsertCursor(
                    dest, ["SHAPE@", "cand_id", "break_min", "run_id"]) as ic,                  arcpy.da.SearchCursor(polys, ["SHAPE@", "Name", "ToBreak"]) as sc:
                for shp, nm, to_break in sc:
                    if shp is None:
                        continue
                    # classic SA names each polygon "<facility> : 0 - 30"
                    cid = str(nm).split(" : ", 1)[0]
                    ic.insertRow([shp, cid, float(to_break), run_id])
                    written += 1
            editor.stopOperation()
            editor.stopEditing(True)
        except Exception:
            editor.abortOperation()
            editor.stopEditing(False)
            raise
        log.info("  batch %2d: %d facilities, %d polygons so far, %.0fs",
                 bi, len(group), written, time.time() - t0)

    # A candidate whose largest polygon falls short of the largest break is
    # marooned on a disconnected piece of network - it did not fail, it just
    # ran out of road. TAR-00758 snapped to "Perimeter Road", an isolated
    # 2.44-mile private stub that intersects nothing, so its reach capped at
    # 2.44 minutes instead of 45. The solve reports success either way, and any
    # workforce figure computed from that polygon would be meaningless.
    marooned = []
    import collections as _c
    biggest = _c.defaultdict(float)
    with arcpy.da.SearchCursor(dest, ["cand_id", "break_min"],
                               "run_id = '%s'" % run_id) as c:
        for cid, b in c:
            biggest[cid] = max(biggest[cid], float(b or 0))
    for cid, _pt in cands:
        if biggest.get(cid, 0.0) < max(breaks) - 0.001:
            marooned.append((cid, round(biggest.get(cid, 0.0), 2)))
    if marooned:
        log.warning("  %d candidate(s) could not reach the largest break (%s min): %s",
                    len(marooned), max(breaks),
                    ", ".join("%s capped at %.2f" % m for m in marooned[:10]))

    log.info("  ServiceAreas_%s: %d polygons for %d candidates in %.0fs",
             mode, written, len(cands) - len(failed), time.time() - t0)
    if failed:
        log.warning("  %d candidates produced no service area: %s",
                    len(failed), ", ".join(failed[:10]))
    return {"target": "ServiceAreas_%s" % mode, "polygons": written,
            "facilities": len(cands), "failed": failed, "breaks": breaks,
            "marooned": marooned}


# ---------------------------------------------------------------------------
# OD matrix - scope §5.2
# ---------------------------------------------------------------------------

def build_od_stores(gdb=None, run_id="", net=None):
    """Truck drive time and distance from every candidate to every served store."""
    import arcpy

    net = net or config.network()
    gdb = gdb or config.paths()["gdb"]
    spec = net["od_matrices"]["stores"]
    batch = int(net["od_matrices"].get("batch_size", 50))
    # A standalone table, not a feature class in the Analysis dataset - the OD
    # rows carry no geometry (lineShapeType is NoLines, because 138 x N
    # cross-country polylines would be gigabytes of shape for no analytical use).
    dest = gdb + "\\OD_Cand_to_Stores"

    cands = candidate_points(gdb)
    stores = store_points(gdb, "served_flag = 1")
    if not stores:
        raise RuntimeError("no served stores - run compute_served_set first")

    log.info("=" * 68)
    log.info("OD matrix: %d candidates x %d served stores = %s pairs (%s mode)",
             len(cands), len(stores), format(len(cands) * len(stores), ","),
             spec["mode"])

    arcpy.env.overwriteOutput = True
    if int(arcpy.management.GetCount(dest)[0]):
        editor = arcpy.da.Editor(gdb)
        editor.startEditing(False, False)
        editor.startOperation()
        arcpy.management.DeleteRows(dest)
        editor.stopOperation()
        editor.stopEditing(True)

    p = na_params(spec["mode"], net)
    arcpy.CheckOutExtension("Network")
    written, t0 = 0, time.time()
    reached_per_cand: dict[str, int] = {}

    lyr = arcpy.na.MakeODCostMatrixLayer(
        in_network_dataset=_nd(gdb, net),
        out_network_analysis_layer="od_stores",
        impedance_attribute=p["impedance"],
        default_cutoff=float(spec["cutoff_min"]) if spec.get("cutoff_min") else None,
        accumulate_attribute_name=p["accumulate"],
        UTurn_policy=p["uturn"],
        restriction_attribute_name=p["restrictions"],
        output_path_shape="NO_LINES").getOutput(0)
    sub = arcpy.na.GetNAClassNames(lyr)
    f_time = total_field(p["time_attribute"])
    f_dist = total_field(p["distance_attribute"])

    # Destinations are the same for every batch, so they are loaded once - but
    # they must be the SERVED set, not every store. Passing the whole feature
    # class here put 7 unserved stores into the matrix and let a candidate
    # "reach" 145 of 143 stores, which is what exposed it. Scope §5.2 says
    # candidates -> Stores_DSG (served set).
    served_lyr = "od_served_stores"
    if arcpy.Exists(served_lyr):
        arcpy.management.Delete(served_lyr)
    arcpy.management.MakeFeatureLayer(gdb + "\\Market\\Stores_DSG",
                                      served_lyr, "served_flag = 1")
    n_dest = int(arcpy.management.GetCount(served_lyr)[0])
    if n_dest != len(stores):
        raise RuntimeError("served-store layer has %d rows but store_points "
                           "returned %d" % (n_dest, len(stores)))
    arcpy.na.AddLocations(lyr, sub["Destinations"], served_lyr,
                          "Name store_id #", "5000 Meters", append="CLEAR")
    arcpy.management.Delete(served_lyr)

    for bi, group in enumerate(_chunks(cands, batch), 1):
        orig = arcpy.management.CreateFeatureclass(
            "in_memory", "orig_%d" % bi, "POINT",
            spatial_reference=arcpy.SpatialReference(
                int(config.schema()["meta"]["crs"])))[0]
        arcpy.management.AddField(orig, "Name", "TEXT", field_length=64)
        with arcpy.da.InsertCursor(orig, ["SHAPE@", "Name"]) as cur:
            for cid, pt in group:
                cur.insertRow([pt, cid])
        arcpy.na.AddLocations(lyr, sub["Origins"], orig, "Name Name #",
                              "5000 Meters", append="CLEAR")
        arcpy.management.Delete(orig)

        try:
            arcpy.na.Solve(lyr, "SKIP")
        except Exception as exc:
            log.warning("  batch %d failed: %s", bi, str(exc)[:200])
            continue

        lines = lyr.listLayers(sub["ODLines"])[0]
        editor = arcpy.da.Editor(gdb)
        editor.startEditing(False, False)
        editor.startOperation()
        try:
            with arcpy.da.InsertCursor(
                    dest, ["cand_id", "store_id", "truck_minutes",
                           "truck_miles", "run_id"]) as ic,                  arcpy.da.SearchCursor(lines, ["Name", f_time, f_dist]) as sc:
                for nm, minutes, miles in sc:
                    if minutes is None:
                        continue
                    cid, sid = str(nm).split(" - ", 1)
                    ic.insertRow([cid, sid, float(minutes), float(miles), run_id])
                    reached_per_cand[cid] = reached_per_cand.get(cid, 0) + 1
                    written += 1
            editor.stopOperation()
            editor.stopEditing(True)
        except Exception:
            editor.abortOperation()
            editor.stopEditing(False)
            raise
        log.info("  batch %2d: %s pairs written, %.0fs", bi,
                 format(written, ","), time.time() - t0)

    missing = [cid for cid, _ in cands if cid not in reached_per_cand]
    log.info("  OD_Cand_to_Stores: %s pairs for %d candidates in %.0fs",
             format(written, ","), len(reached_per_cand), time.time() - t0)
    if missing:
        log.warning("  %d candidates reached NO store: %s", len(missing),
                    ", ".join(missing[:10]))
    return {"target": "OD_Cand_to_Stores", "pairs": written,
            "candidates": len(cands), "served_stores": len(stores),
            "reached_per_cand": reached_per_cand, "unreachable": missing}


def build_served_reach(gdb=None, run_id="", net=None, bands=None):
    """Truck-time reach from the MSA centroid, and the stores inside each band.

    This is the geometry behind the served-set rule in scope 2.2: the served
    set is defined by truck time from the MSA CENTROID, so the isochrone that
    explains it is centred there too.

    It is deliberately NOT the 138-candidate `ServiceAreas_Truck` of scope 5.2.
    Those are a cartographic product - no criterion in `criteria.yaml` depends
    on them, C01/C02 use the Driving areas and the store criterion uses the OD
    table - and at 60/120/240 minutes over a sixteen-state network they cost
    hours. One facility answers the question the served set actually poses.
    """
    import arcpy

    net = net or config.network()
    gdb = gdb or config.paths()["gdb"]
    src = config.sources()
    spec = net["service_areas"]["Truck"]
    bands = [float(b) for b in (bands or list(spec["breaks_min"]) +
                                [net["od_matrices"]["stores"]["cutoff_min"]])]
    centre = src["study_area"]["msa_centroid_wgs84"]
    target_crs = int(config.schema()["meta"]["crs"])
    dest = gdb + "\\Analysis\\ServiceAreas_Truck"
    p = na_params("Truck", net)

    log.info("=" * 68)
    log.info("served reach: Truck bands %s min from the MSA centroid", bands)

    arcpy.env.overwriteOutput = True
    arcpy.CheckOutExtension("Network")
    if int(arcpy.management.GetCount(dest)[0]):
        editor = arcpy.da.Editor(gdb)
        editor.startEditing(False, False)
        editor.startOperation()
        arcpy.management.DeleteRows(dest)
        editor.stopOperation()
        editor.stopEditing(True)

    lyr = arcpy.na.MakeServiceAreaLayer(
        in_network_dataset=_nd(gdb, net),
        out_network_analysis_layer="sa_reach",
        impedance_attribute=p["impedance"],
        travel_from_to="TRAVEL_FROM",
        default_break_values=" ".join(str(int(b)) for b in bands),
        polygon_type="SIMPLE_POLYS",
        merge="NO_MERGE",
        nesting_type=net["service_areas"]["nesting"],
        line_type="NO_LINES",
        UTurn_policy=p["uturn"],
        restriction_attribute_name=p["restrictions"],
        polygon_trim="TRIM_POLYS",
        poly_trim_value=str(spec["polygon_trim_distance"])).getOutput(0)
    sub = arcpy.na.GetNAClassNames(lyr)

    fac = arcpy.management.CreateFeatureclass(
        "in_memory", "reach_fac", "POINT",
        spatial_reference=arcpy.SpatialReference(target_crs))[0]
    arcpy.management.AddField(fac, "Name", "TEXT", field_length=64)
    pt = arcpy.PointGeometry(arcpy.Point(*centre),
                             arcpy.SpatialReference(4326)).projectAs(
                                 arcpy.SpatialReference(target_crs))
    with arcpy.da.InsertCursor(fac, ["SHAPE@", "Name"]) as cur:
        cur.insertRow([pt, "MSA_CENTROID"])
    arcpy.na.AddLocations(lyr, sub["Facilities"], fac, "Name Name #",
                          "5000 Meters", append="CLEAR")
    arcpy.management.Delete(fac)

    t0 = time.time()
    arcpy.na.Solve(lyr, "SKIP")
    polys = lyr.listLayers(sub["SAPolygons"])[0]

    written = 0
    editor = arcpy.da.Editor(gdb)
    editor.startEditing(False, False)
    editor.startOperation()
    try:
        with arcpy.da.InsertCursor(
                dest, ["SHAPE@", "cand_id", "break_min", "run_id"]) as ic, \
             arcpy.da.SearchCursor(polys, ["SHAPE@", "Name", "ToBreak"]) as sc:
            for shp, nm, to_break in sc:
                if shp is None:
                    continue
                ic.insertRow([shp, "MSA_CENTROID", float(to_break), run_id])
                written += 1
        editor.stopOperation()
        editor.stopEditing(True)
    except Exception:
        editor.abortOperation()
        editor.stopEditing(False)
        raise

    # Which stores land in which band, from the OD times already computed.
    per_band = {b: 0 for b in bands}
    beyond = 0
    with arcpy.da.SearchCursor(gdb + "\\StoreServiceSet",
                               ["truck_minutes", "run_id"],
                               "run_id = '%s'" % run_id) as c:
        for minutes, _ in c:
            if minutes is None:
                beyond += 1
                continue
            for b in bands:
                if minutes <= b:
                    per_band[b] += 1
                    break
            else:
                beyond += 1

    log.info("  %d reach polygons in %.0fs", written, time.time() - t0)
    for b in bands:
        log.info("    <= %4.0f min   %3d stores", b, per_band[b])
    log.info("    beyond       %3d stores", beyond)
    return {"target": "ServiceAreas_Truck", "polygons": written,
            "bands": bands, "stores_per_band": per_band, "beyond": beyond}
