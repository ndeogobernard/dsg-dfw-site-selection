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
from .roads import travel_mode

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

    od = arcpy.nax.OriginDestinationCostMatrix(_nd(gdb, net))
    od.travelMode = travel_mode(mode, net)
    od.timeUnits = arcpy.nax.TimeUnits.Minutes
    od.distanceUnits = arcpy.nax.DistanceUnits.Miles
    od.defaultImpedanceCutoff = cutoff
    od.lineShapeType = arcpy.nax.LineShapeType.NoLines

    pt = arcpy.PointGeometry(arcpy.Point(*centre),
                             arcpy.SpatialReference(4326)).projectAs(
                                 arcpy.SpatialReference(target_crs))
    with od.insertCursor(arcpy.nax.OriginDestinationCostMatrixInputDataType.Origins,
                         ["SHAPE@", "Name"]) as cur:
        cur.insertRow([pt, "MSA_CENTROID"])
    with od.insertCursor(
            arcpy.nax.OriginDestinationCostMatrixInputDataType.Destinations,
            ["SHAPE@", "Name"]) as cur:
        for sid, shp in stores:
            cur.insertRow([shp, sid])

    res = od.solve()
    if not res.solveSucceeded:
        raise RuntimeError("served-set solve failed: %s" % "; ".join(
            str(m) for m in res.solverMessages(arcpy.nax.MessageSeverity.All))[:300])

    order = [sid for sid, _ in stores]
    reached = {}
    with res.searchCursor(
            arcpy.nax.OriginDestinationCostMatrixOutputDataType.Lines,
            ["DestinationOID", "Total_Minutes", "Total_Miles"]) as c:
        for doid, minutes, miles in c:
            sid = order[int(doid) - 1]
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

    tm = travel_mode(mode, net)
    written, failed, t0 = 0, [], time.time()

    for bi, group in enumerate(_chunks(cands, batch), 1):
        sa = arcpy.nax.ServiceArea(_nd(gdb, net))
        sa.travelMode = tm
        sa.timeUnits = arcpy.nax.TimeUnits.Minutes
        sa.distanceUnits = arcpy.nax.DistanceUnits.Miles
        sa.defaultImpedanceCutoffs = breaks
        sa.outputType = arcpy.nax.ServiceAreaOutputType.Polygons
        sa.geometryAtOverlap = getattr(
            arcpy.nax.ServiceAreaOverlapGeometry, spec["geometry_at_overlaps"].title())
        sa.polygonDetail = getattr(
            arcpy.nax.ServiceAreaPolygonDetail, spec["polygon_detail"].title())
        sa.polygonBufferDistance = float(
            str(spec["polygon_trim_distance"]).split()[0])

        with sa.insertCursor(arcpy.nax.ServiceAreaInputDataType.Facilities,
                             ["SHAPE@", "Name"]) as cur:
            for cid, pt in group:
                cur.insertRow([pt, cid])

        res = sa.solve()
        if not res.solveSucceeded:
            failed.extend(cid for cid, _ in group)
            log.warning("  batch %d failed: %s", bi, "; ".join(
                str(m) for m in res.solverMessages(
                    arcpy.nax.MessageSeverity.Error))[:200])
            continue

        editor = arcpy.da.Editor(gdb)
        editor.startEditing(False, False)
        editor.startOperation()
        try:
            with arcpy.da.InsertCursor(
                    dest, ["SHAPE@", "cand_id", "break_min", "run_id"]) as ic, \
                 res.searchCursor(arcpy.nax.ServiceAreaOutputDataType.Polygons,
                                  ["SHAPE@", "FacilityName", "ToBreak"]) as sc:
                for shp, fname, to_break in sc:
                    if shp is None:
                        continue
                    ic.insertRow([shp, fname, float(to_break), run_id])
                    written += 1
            editor.stopOperation()
            editor.stopEditing(True)
        except Exception:
            editor.abortOperation()
            editor.stopEditing(False)
            raise
        log.info("  batch %2d: %d facilities, %d polygons so far, %.0fs",
                 bi, len(group), written, time.time() - t0)

    log.info("  ServiceAreas_%s: %d polygons for %d candidates in %.0fs",
             mode, written, len(cands) - len(failed), time.time() - t0)
    if failed:
        log.warning("  %d candidates produced no service area: %s",
                    len(failed), ", ".join(failed[:10]))
    return {"target": "ServiceAreas_%s" % mode, "polygons": written,
            "facilities": len(cands), "failed": failed, "breaks": breaks}


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

    tm = travel_mode(spec["mode"], net)
    store_order = [sid for sid, _ in stores]
    written, t0 = 0, time.time()
    reached_per_cand: dict[str, int] = {}

    for bi, group in enumerate(_chunks(cands, batch), 1):
        od = arcpy.nax.OriginDestinationCostMatrix(_nd(gdb, net))
        od.travelMode = tm
        od.timeUnits = arcpy.nax.TimeUnits.Minutes
        od.distanceUnits = arcpy.nax.DistanceUnits.Miles
        od.lineShapeType = arcpy.nax.LineShapeType.NoLines
        if spec.get("cutoff_min"):
            od.defaultImpedanceCutoff = float(spec["cutoff_min"])

        with od.insertCursor(
                arcpy.nax.OriginDestinationCostMatrixInputDataType.Origins,
                ["SHAPE@", "Name"]) as cur:
            for cid, pt in group:
                cur.insertRow([pt, cid])
        with od.insertCursor(
                arcpy.nax.OriginDestinationCostMatrixInputDataType.Destinations,
                ["SHAPE@", "Name"]) as cur:
            for sid, shp in stores:
                cur.insertRow([shp, sid])

        res = od.solve()
        if not res.solveSucceeded:
            log.warning("  batch %d failed: %s", bi, "; ".join(
                str(m) for m in res.solverMessages(
                    arcpy.nax.MessageSeverity.Error))[:200])
            continue

        cand_order = [cid for cid, _ in group]
        editor = arcpy.da.Editor(gdb)
        editor.startEditing(False, False)
        editor.startOperation()
        try:
            with arcpy.da.InsertCursor(
                    dest, ["cand_id", "store_id", "truck_minutes",
                           "truck_miles", "run_id"]) as ic, \
                 res.searchCursor(
                     arcpy.nax.OriginDestinationCostMatrixOutputDataType.Lines,
                     ["OriginOID", "DestinationOID",
                      "Total_Minutes", "Total_Miles"]) as sc:
                for ooid, doid, minutes, miles in sc:
                    if minutes is None:
                        continue
                    cid = cand_order[int(ooid) - 1]
                    ic.insertRow([cid, store_order[int(doid) - 1],
                                  float(minutes), float(miles), run_id])
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
