#!/usr/bin/env python3
"""Ingest the physical-filter layers for the configured slice, then QA each.

Part 1 of the vertical slice. Does not build the network dataset, service
areas, OD matrices or scores - those are Parts 2 and 3.

Usage:
    python tools/ingest_physical_layers.py [--only flood,wetlands] [--fresh]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import arcpy  # noqa: E402
from li import config, layers, logging_utils, qaqc  # noqa: E402

ORDER = ["flood", "wetlands", "water_ccn", "sewer_ccn", "buildings",
         "interchanges", "elevation", "land_cover"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated subset")
    ap.add_argument("--fresh", action="store_true", help="ignore cached downloads")
    args = ap.parse_args()

    run_id = logging_utils.make_run_id("layers")
    logging_utils.get_logger("li", log_dir=Path(config.paths()["logs_dir"]),
                             run_id=run_id, level=logging.INFO)
    log = logging.getLogger("li.ingest")

    gdb = config.paths()["gdb"]
    wanted = [k for k in ORDER if not args.only or k in args.only.split(",")]
    arcpy.env.overwriteOutput = True

    if args.fresh:
        raw = Path(config.paths()["raw_dir"]) / config.sources()["slice"]["name"]
        if raw.exists():
            import shutil
            shutil.rmtree(raw)
            log.info("cleared cached downloads at %s", raw)

    log.info("PHYSICAL-LAYER INGEST  run_id=%s  slice=%s",
             run_id, config.sources()["slice"]["name"])

    results = []
    t0 = time.time()
    for key in wanted:
        t = time.time()
        try:
            if key == "elevation":
                r = layers.ingest_elevation_slope(gdb, run_id)
            elif key == "land_cover":
                r = layers.ingest_land_cover(gdb, run_id)
            elif key == "interchanges":
                r = layers.ingest_interchanges(gdb, run_id)
            else:
                r = layers.ingest_vector(key, gdb, run_id)
        except Exception as exc:                     # keep going; report honestly
            log.error("%s FAILED: %s", key, exc)
            log.debug(traceback.format_exc())
            r = {"layer": key, "status": "FAILED", "error": str(exc)[:200]}
        r["seconds"] = round(time.time() - t, 1)
        results.append(r)

    print("\n" + "=" * 92)
    print("INGEST SUMMARY")
    print("=" * 92)
    print(f"  {'layer':14} {'status':8} {'target':22} {'loaded':>9}  {'secs':>7}  note")
    for r in results:
        print(f"  {r['layer']:14} {r['status']:8} {str(r.get('target','')):22} "
              f"{str(r.get('loaded', r.get('cols','-'))):>9}  {r['seconds']:>7}  "
              f"{r.get('reason', r.get('error',''))[:34]}")
    print(f"  total {time.time() - t0:.0f}s")

    # QA the vector layers that actually loaded
    print("\n" + "=" * 92)
    print("QA/QC")
    print("=" * 92)
    checks = []
    expected_crs = int(config.schema()["meta"]["crs"])
    for r in results:
        if r["status"] != "OK" or not r.get("loaded"):
            continue
        tgt = r["target"]
        ds = config.schema()["feature_classes"].get(tgt, {}).get("dataset")
        fc = f"{gdb}\\{ds}\\{tgt}" if ds else f"{gdb}\\{tgt}"
        if not arcpy.Exists(fc):
            continue
        d = arcpy.da.Describe(fc)
        sr = d.get("spatialReference")
        crs_ok = qaqc.crs_matches(getattr(sr, "factoryCode", None), expected_crs)
        n = int(arcpy.management.GetCount(fc)[0])
        nulls = sum(1 for row in arcpy.da.SearchCursor(fc, ["SHAPE@"]) if row[0] is None)
        res = qaqc.CheckResult(
            f"LYR-{tgt[:12].upper()}", tgt, "CRS + geometry + count",
            qaqc.PASS if (crs_ok and nulls == 0 and n > 0) else qaqc.FAIL,
            affected_cnt=nulls,
            detail=f"{n:,} features, EPSG:{getattr(sr,'factoryCode','?')}, {nulls} null geometry")
        checks.append(res)
        print(f"  {res.result:8} {tgt:22} {res.detail}")

    for r in results:
        if r["status"] in ("SKIPPED", "FAILED"):
            res = qaqc.CheckResult(f"LYR-{r['layer'][:12].upper()}", r["layer"],
                                   "layer available", qaqc.SKIP if r["status"] == "SKIPPED" else qaqc.FAIL,
                                   detail=r.get("reason", r.get("error", "")))
            checks.append(res)
            print(f"  {res.result:8} {r['layer']:22} {res.detail[:70]}")

    written = qaqc.write_log(gdb, run_id, checks)
    print(f"\n  {written} rows written to QAQC_Log   run_id={run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
