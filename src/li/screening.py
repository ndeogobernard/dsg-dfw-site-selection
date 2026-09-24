"""Phase A candidate screening (scope §5.1, D-013 physical-only).

The rule engine is **pure Python and arcpy-free** so every threshold decision
is unit-tested in CI. The arcpy half only measures each parcel against the
layers and hands the numbers to `evaluate`.

Screening here is **physical and infrastructural only** (D-013). There is no
zoning gate: zoning is unobtainable for a large share of the study area, and
gating on it silently discards exactly the cheap unincorporated greenfield a
distribution centre would realistically buy. Industrial context is scored in
Part 3 as C11 and C12 instead.

Two approximations are deliberate and recorded:

* **D-015** — interchange proximity is straight-line, not network drive-time.
  True drive-time is criterion C04; solving a network for every parcel in the
  county just to screen would cost far more than it buys.
* **D-016** — sewer CCN is not applied as a hard filter, because no statewide
  source was located. Every candidate carries `sewer_status` and the filter is
  reported as SKIPPED, so the gap is visible rather than assumed away.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from . import config

try:  # pragma: no cover
    import arcpy
except ImportError:  # pragma: no cover
    arcpy = None

log = logging.getLogger("li.screening")

PASS, FAIL, REVIEW, SKIPPED = "Pass", "Fail", "Review", "Skipped"


# ---------------------------------------------------------------------------
# Pure logic
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Filter:
    """One hard filter: how to read it, how to judge it, what to call it."""

    key: str                 # metric name on the parcel
    label: str               # human name, used in the funnel
    threshold_key: str       # key in screening.yaml
    mode: str                # "min" (>= threshold) or "max" (<= threshold)
    missing: str = "zero"    # "zero": absent means 0;  "review": absent is unknown


def derived_interchange_radius_miles(thresholds: dict[str, Any]) -> float:
    """Straight-line radius standing in for a drive-time threshold (D-015).

    minutes / 60 * mph / circuity. The circuity factor makes the radius
    deliberately smaller than the raw distance the drive would cover, because
    roads do not run straight; erring the other way would admit parcels that
    cannot actually reach an interchange in time.
    """
    ip = thresholds["interchange_proximity"]
    minutes = float(thresholds["max_truck_min_to_interchange"])
    return minutes / 60.0 * float(ip["assumed_speed_mph"]) / float(ip["circuity_factor"])


def filter_order(thresholds: dict[str, Any]) -> list[Filter]:
    """The hard filters, in the order the funnel applies them.

    Acreage runs first on purpose: it takes 758,633 parcels to under a
    thousand, so every spatial measurement afterwards runs on a small set.
    """
    fs = [
        Filter("acres_published", "acreage >= min_acres", "min_acres", "min"),
        Filter("floodway_pct", "floodway coverage", "max_floodway_pct", "max"),
        Filter("sfha_pct", "SFHA coverage", "max_sfha_pct", "max"),
        Filter("wetland_pct", "wetland coverage", "max_wetland_pct", "max"),
        Filter("mean_slope_pct", "mean slope", "max_mean_slope_pct", "max", "review"),
        Filter("developed_pct", "developed land cover", "max_developed_pct", "max", "review"),
    ]
    if thresholds.get("require_water_ccn", True):
        fs.append(Filter("water_ccn", "water CCN service", "require_water_ccn", "min"))
    fs.append(Filter("interchange_miles", "interchange proximity",
                     "_derived_interchange_miles", "max"))
    return fs


def resolve_thresholds(thresholds: dict[str, Any] | None = None) -> dict[str, Any]:
    """screening.yaml plus the values derived from it."""
    t = dict(thresholds or config.screening())
    t["_derived_interchange_miles"] = round(derived_interchange_radius_miles(t), 4)
    return t


def judge(value: Any, f: Filter, thresholds: dict[str, Any]) -> tuple[str, str]:
    """Judge one metric against one filter. Returns (status, detail)."""
    limit = thresholds[f.threshold_key]

    if value is None:
        if f.missing == "review":
            return REVIEW, f"{f.label}: not measurable"
        value = 0

    if f.key == "water_ccn":                    # boolean-ish requirement
        return (PASS, "") if bool(value) else (FAIL, "no water CCN service")

    v = float(value)
    lim = float(limit)
    ok = v >= lim if f.mode == "min" else v <= lim
    if ok:
        return PASS, ""
    comp = ">=" if f.mode == "min" else "<="
    return FAIL, f"{f.label}: {v:g} not {comp} {lim:g}"


def evaluate(metrics: dict[str, Any],
             thresholds: dict[str, Any] | None = None) -> tuple[str, str]:
    """Apply every hard filter in order; report the FIRST failing rule.

    Reporting the first failure rather than all of them is what makes the
    funnel readable: each parcel is attributed to exactly one filter, so the
    drop-offs sum to the starting count.
    """
    t = resolve_thresholds(thresholds)
    review_reason = ""
    for f in filter_order(t):
        status, detail = judge(metrics.get(f.key), f, t)
        if status == FAIL:
            return FAIL, detail
        if status == REVIEW and not review_reason:
            review_reason = detail
    if review_reason:
        return REVIEW, review_reason
    return PASS, ""


def funnel(rows: Iterable[dict[str, Any]],
           thresholds: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Drop-off counts, applying filters in sequence to the survivors.

    Each stage reports how many entered it and how many it removed, so the
    numbers reconcile against the starting count rather than being independent
    tallies of "how many parcels violate X".
    """
    t = resolve_thresholds(thresholds)
    survivors = list(rows)
    out = [{"stage": "start", "label": "parcels in county",
            "entering": len(survivors), "removed": 0, "remaining": len(survivors),
            "threshold": None}]

    for i, f in enumerate(filter_order(t), 1):
        entering = len(survivors)
        kept, removed = [], 0
        for r in survivors:
            status, _ = judge(r.get(f.key), f, t)
            if status == FAIL:
                removed += 1
            else:
                kept.append(r)
        survivors = kept
        out.append({"stage": i, "label": f.label, "entering": entering,
                    "removed": removed, "remaining": len(survivors),
                    "threshold": t[f.threshold_key]})
    return out


def sewer_is_a_filter(thresholds: dict[str, Any] | None = None) -> bool:
    """D-016: false while no statewide sewer-CCN source exists."""
    t = thresholds or config.screening()
    return bool(t.get("sewer", {}).get("apply_as_hard_filter", False))


def sewer_status_value(thresholds: dict[str, Any] | None = None) -> str:
    t = thresholds or config.screening()
    return str(t.get("sewer", {}).get("status_when_unknown",
                                      "Unknown - pending D-016 search"))


# ---------------------------------------------------------------------------
# arcpy measurement + run
# ---------------------------------------------------------------------------

def _require_arcpy():
    if arcpy is None:
        raise ImportError("arcpy is required for li.screening measurement")


def _fc(gdb, name):
    ds = config.schema()["feature_classes"].get(name, {}).get("dataset")
    return f"{gdb}\\{ds}\\{name}" if ds else f"{gdb}\\{name}"


def _pct_overlap(zones, zone_id, class_fc, where, workspace, tag):
    """Percent of each zone covered by a class layer.

    The class layer is dissolved first: NFHL polygons overlap one another
    (a floodway sits inside an SFHA), and TabulateIntersection sums overlapping
    class area, which can push a parcel past 100% coverage and fail it for
    geometry bookkeeping rather than flood risk.
    """
    lyr = f"cls_{tag}"
    if arcpy.Exists(lyr):
        arcpy.management.Delete(lyr)
    arcpy.management.MakeFeatureLayer(class_fc, lyr, where)
    n = int(arcpy.management.GetCount(lyr)[0])
    if n == 0:
        arcpy.management.Delete(lyr)
        return {}

    diss = f"{workspace}\\_diss_{tag}"
    tab = f"{workspace}\\_tab_{tag}"
    for p in (diss, tab):
        if arcpy.Exists(p):
            arcpy.management.Delete(p)
    arcpy.analysis.PairwiseDissolve(lyr, diss)
    arcpy.analysis.TabulateIntersection(zones, zone_id, diss, tab)

    out = {}
    with arcpy.da.SearchCursor(tab, [zone_id, "PERCENTAGE"]) as c:
        for zid, pct in c:
            out[zid] = max(out.get(zid, 0.0), float(pct or 0.0))
    for p in (lyr, diss, tab):
        if arcpy.Exists(p):
            arcpy.management.Delete(p)
    log.info("    %-22s %d source polys -> %d parcels with overlap", tag, n, len(out))
    return out


def _warn_if_patchy(metric, measured, total, tolerance=0.02):
    """Say so, loudly, when a raster metric covered less than it should.

    An unmeasured metric becomes Review rather than Pass, so patchy coverage
    never admits a bad parcel - but it does quietly swell the candidate list
    with parcels nobody actually screened. That belongs in the log, not in a
    reader's surprise later.
    """
    if total and measured < total * (1.0 - tolerance):
        log.warning("    %s measured only %d of %d parcels (%.1f%%) - the rest "
                    "become Review, not Pass", metric, measured, total,
                    100.0 * measured / total)


def measure_parcels(gdb, work_fc, zone_id="parcel_id"):
    """Measure every physical metric the filters need, for one working set."""
    _require_arcpy()
    arcpy.CheckOutExtension("Spatial")
    ws = gdb
    m = {}

    # Zone rasterization keeps only cells whose centre falls inside the parcel,
    # so at a coarse cell a narrow parcel measures as nothing at all. See
    # `raster_zonal` in config/screening.yaml.
    cell = float(config.screening().get("raster_zonal", {})
                 .get("processing_cell_ft", 30))
    arcpy.env.cellSize = cell

    flood = _fc(gdb, "FloodZones_NFHL")
    if arcpy.Exists(flood) and int(arcpy.management.GetCount(flood)[0]):
        m["floodway_pct"] = _pct_overlap(work_fc, zone_id, flood,
                                         "floodway_flag = 1", ws, "floodway")
        m["sfha_pct"] = _pct_overlap(work_fc, zone_id, flood,
                                     "sfha_flag = 1", ws, "sfha")
    else:
        log.warning("    FloodZones_NFHL empty - flood metrics unavailable")
        m["floodway_pct"], m["sfha_pct"] = {}, {}

    wet = _fc(gdb, "Wetlands_NWI")
    if arcpy.Exists(wet) and int(arcpy.management.GetCount(wet)[0]):
        m["wetland_pct"] = _pct_overlap(work_fc, zone_id, wet, "1=1", ws, "wetland")
    else:
        log.warning("    Wetlands_NWI empty - wetland metric unavailable")
        m["wetland_pct"] = {}

    # Mean percent slope
    slope_r = f"{gdb}\\Slope_pct"
    m["mean_slope_pct"] = {}
    if arcpy.Exists(slope_r):
        tab = f"{ws}\\_tab_slope"
        if arcpy.Exists(tab):
            arcpy.management.Delete(tab)
        arcpy.sa.ZonalStatisticsAsTable(work_fc, zone_id, slope_r, tab, "DATA", "MEAN")
        with arcpy.da.SearchCursor(tab, [zone_id, "MEAN"]) as c:
            m["mean_slope_pct"] = {z: float(v) for z, v in c if v is not None}
        arcpy.management.Delete(tab)
        n_zone = int(arcpy.management.GetCount(work_fc)[0])
        log.info("    %-22s mean slope for %d of %d parcels", "slope",
                 len(m["mean_slope_pct"]), n_zone)
        _warn_if_patchy("mean slope", len(m["mean_slope_pct"]), n_zone)
    else:
        log.warning("    Slope_pct missing - slope metric unavailable (parcels -> Review)")

    # Developed land cover
    m["developed_pct"] = {}
    nlcd = f"{gdb}\\LandCover_NLCD"
    if arcpy.Exists(nlcd):
        dev = [int(v) for v in config.screening()["nlcd_developed_classes"]]
        tab = f"{ws}\\_tab_nlcd"
        if arcpy.Exists(tab):
            arcpy.management.Delete(tab)
        arcpy.sa.TabulateArea(work_fc, zone_id, nlcd, "Value", tab, cell)
        cols = [f.name for f in arcpy.ListFields(tab) if f.name.upper().startswith("VALUE_")]
        devcols = [c for c in cols if int(c.split("_")[1]) in dev]
        with arcpy.da.SearchCursor(tab, [zone_id] + cols) as c:
            idx = {n: i + 1 for i, n in enumerate(cols)}
            for row in c:
                total = sum(float(row[i] or 0) for i in range(1, len(cols) + 1))
                d = sum(float(row[idx[x]] or 0) for x in devcols)
                m["developed_pct"][row[0]] = (100.0 * d / total) if total else 0.0
        arcpy.management.Delete(tab)
        n_zone = int(arcpy.management.GetCount(work_fc)[0])
        log.info("    %-22s classes %s over %d of %d parcels", "developed", dev,
                 len(m["developed_pct"]), n_zone)
        _warn_if_patchy("developed land cover", len(m["developed_pct"]), n_zone)
    else:
        log.warning("    LandCover_NLCD missing - developed metric unavailable "
                    "(parcels -> Review)")

    # Water CCN service - parcel centre inside a CCN service area
    m["water_ccn"] = {}
    ccn = _fc(gdb, "WaterCCN")
    if arcpy.Exists(ccn) and int(arcpy.management.GetCount(ccn)[0]):
        lyr = "parc_ccn"
        if arcpy.Exists(lyr):
            arcpy.management.Delete(lyr)
        arcpy.management.MakeFeatureLayer(work_fc, lyr)
        arcpy.management.SelectLayerByLocation(lyr, "HAVE_THEIR_CENTER_IN", ccn)
        with arcpy.da.SearchCursor(lyr, [zone_id]) as c:
            for (z,) in c:
                m["water_ccn"][z] = 1
        arcpy.management.Delete(lyr)
        log.info("    %-22s %d parcels centred in a CCN area", "water_ccn",
                 len(m["water_ccn"]))
    else:
        log.warning("    WaterCCN empty - water metric unavailable")

    # Straight-line distance to nearest interchange (D-015)
    m["interchange_miles"] = {}
    ix = _fc(gdb, "Interchanges")
    if arcpy.Exists(ix) and int(arcpy.management.GetCount(ix)[0]):
        near = f"{ws}\\_near_work"
        if arcpy.Exists(near):
            arcpy.management.Delete(near)
        arcpy.management.CopyFeatures(work_fc, near)
        arcpy.analysis.Near(near, ix, method="PLANAR")
        with arcpy.da.SearchCursor(near, [zone_id, "NEAR_DIST"]) as c:
            for z, d in c:
                if d is not None and d >= 0:
                    m["interchange_miles"][z] = float(d) / 5280.0   # ftUS -> miles
        arcpy.management.Delete(near)
        vals = list(m["interchange_miles"].values())
        log.info("    %-22s %d parcels, %.2f-%.2f mi", "interchange", len(vals),
                 min(vals) if vals else 0, max(vals) if vals else 0)
    else:
        log.warning("    Interchanges empty - proximity metric unavailable")

    return m


def screen(gdb=None, run_id="", county="Tarrant"):
    """Run Phase A screening and write CandidateSites. Returns the funnel."""
    _require_arcpy()
    gdb = gdb or config.paths()["gdb"]
    t = resolve_thresholds()
    parcels = _fc(gdb, "Parcels")
    cand = _fc(gdb, "CandidateSites")

    log.info("=" * 74)
    log.info("SCREENING  run_id=%s  county=%s", run_id, county)
    log.info("thresholds in force:")
    shown = ["min_acres", "max_floodway_pct", "max_sfha_pct", "max_wetland_pct",
             "max_mean_slope_pct", "max_developed_pct", "require_water_ccn",
             "max_truck_min_to_interchange", "_derived_interchange_miles"]
    for k in shown:
        log.info("    %-32s %s", k, t[k])
    log.info("    %-32s %s", "sewer hard filter (D-016)", sewer_is_a_filter(t))

    total = int(arcpy.management.GetCount(parcels)[0])

    # Acreage first: 758,633 -> under a thousand, so the spatial work is cheap.
    work = f"{gdb}\\_screen_work"
    if arcpy.Exists(work):
        arcpy.management.Delete(work)
    lyr = "parc_acre"
    if arcpy.Exists(lyr):
        arcpy.management.Delete(lyr)
    arcpy.management.MakeFeatureLayer(
        parcels, lyr, f"acres_published >= {float(t['min_acres'])}")
    n_acre = int(arcpy.management.GetCount(lyr)[0])
    arcpy.management.CopyFeatures(lyr, work)
    arcpy.management.Delete(lyr)
    log.info("  acreage pre-filter: %s of %s parcels", f"{n_acre:,}", f"{total:,}")

    log.info("  measuring physical metrics")
    metrics = measure_parcels(gdb, work)

    rows = []
    with arcpy.da.SearchCursor(work, ["parcel_id", "acres_published", "acres",
                                      "SHAPE@XY", "SHAPE@"]) as c:
        for pid, acres_pub, acres_geom, xy, shp in c:
            rows.append({
                "parcel_id": pid,
                "acres_published": acres_pub,
                "acres": acres_geom,
                "xy": xy,
                "shape": shp,
                "floodway_pct": metrics["floodway_pct"].get(pid, 0.0),
                "sfha_pct": metrics["sfha_pct"].get(pid, 0.0),
                "wetland_pct": metrics["wetland_pct"].get(pid, 0.0),
                "mean_slope_pct": metrics["mean_slope_pct"].get(pid),
                "developed_pct": metrics["developed_pct"].get(pid),
                "water_ccn": metrics["water_ccn"].get(pid, 0),
                "interchange_miles": metrics["interchange_miles"].get(pid),
            })

    # Funnel over the FULL county: stage 1 is the acreage filter itself, so the
    # numbers reconcile from the starting parcel count rather than from the
    # already-reduced working set.
    steps = funnel(rows, t)
    steps[0] = {"stage": "start", "label": "parcels in county",
                "entering": total, "removed": 0, "remaining": total, "threshold": None}
    steps[1]["entering"] = total
    steps[1]["removed"] = total - n_acre
    steps[1]["remaining"] = n_acre

    sewer_val = sewer_status_value(t)
    n_written = 0
    editor = arcpy.da.Editor(gdb)
    editor.startEditing(with_undo=False, multiuser_mode=False)
    editor.startOperation()
    try:
        flds = ["SHAPE@", "cand_id", "parcel_ids", "origin_type", "acres",
                "zoning_class", "screen_status", "screen_reason",
                "centroid_x", "centroid_y", "run_id", "sewer_status"]
        with arcpy.da.InsertCursor(cand, flds) as ic:
            for i, r in enumerate(sorted(rows, key=lambda x: -float(x["acres_published"] or 0)), 1):
                status, reason = evaluate(r, t)
                if status == FAIL:
                    continue                      # only survivors are written
                ic.insertRow((r["shape"], f"{county[:3].upper()}-{i:05d}",
                              r["parcel_id"], "Parcel",
                              float(r["acres_published"] or 0), "Unknown",
                              status, reason[:200],
                              r["xy"][0], r["xy"][1], run_id, sewer_val))
                n_written += 1
        editor.stopOperation()
        editor.stopEditing(save_changes=True)
    except Exception:
        editor.abortOperation()
        editor.stopEditing(save_changes=False)
        raise

    arcpy.management.Delete(work)
    log.info("  wrote %d candidates (Pass + Review)", n_written)
    return {"funnel": steps, "written": n_written, "thresholds": t,
            "total_parcels": total, "sewer_status": sewer_val}
