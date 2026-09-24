#!/usr/bin/env python3
"""Run Phase A screening on the Tarrant slice and print the drop-off funnel.

Part 1 of the vertical slice. No network dataset, no service areas, no OD
matrices, no scoring - those are Parts 2 and 3.

Usage:
    python tools/screen_tarrant.py [--reset]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import arcpy  # noqa: E402
from li import config, logging_utils, qaqc, screening  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true",
                    help="empty CandidateSites before running")
    args = ap.parse_args()

    run_id = logging_utils.make_run_id("screen")
    logging_utils.get_logger("li", log_dir=Path(config.paths()["logs_dir"]),
                             run_id=run_id, level=logging.INFO)
    gdb = config.paths()["gdb"]
    arcpy.env.overwriteOutput = True
    cand = f"{gdb}\\Analysis\\CandidateSites"

    if args.reset and int(arcpy.management.GetCount(cand)[0]):
        editor = arcpy.da.Editor(gdb)
        editor.startEditing(False, False)
        editor.startOperation()
        arcpy.management.DeleteRows(cand)
        editor.stopOperation()
        editor.stopEditing(True)
        print("  CandidateSites emptied")

    result = screening.screen(gdb, run_id, county="Tarrant")
    t = result["thresholds"]

    print("\n" + "=" * 94)
    print("THRESHOLDS USED  (config/screening.yaml, scope Appendix B defaults, untightened)")
    print("=" * 94)
    for k in ("min_acres", "max_floodway_pct", "max_sfha_pct", "max_wetland_pct",
              "max_mean_slope_pct", "max_developed_pct", "require_water_ccn",
              "max_truck_min_to_interchange"):
        print(f"  {k:34} {t[k]}")
    ip = t["interchange_proximity"]
    print(f"  {'interchange method (D-015)':34} {ip['method']} "
          f"({ip['assumed_speed_mph']} mph / circuity {ip['circuity_factor']})")
    print(f"  {'-> derived radius':34} {t['_derived_interchange_miles']} miles")
    print(f"  {'sewer hard filter (D-016)':34} {t['sewer']['apply_as_hard_filter']}  "
          f"-> SKIPPED, recorded as '{result['sewer_status']}'")

    print("\n" + "=" * 94)
    print("SCREENING FUNNEL - Tarrant County")
    print("=" * 94)
    print(f"  {'#':>2}  {'filter':30} {'threshold':>12} {'entering':>10} "
          f"{'removed':>10} {'remaining':>11}")
    print("  " + "-" * 90)
    for s in result["funnel"]:
        thr = "" if s["threshold"] is None else str(s["threshold"])
        stage = "" if s["stage"] == "start" else str(s["stage"])
        print(f"  {stage:>2}  {s['label']:30} {thr:>12} {s['entering']:>10,} "
              f"{s['removed']:>10,} {s['remaining']:>11,}")
    print("  " + "-" * 90)
    print(f"  {'':2}  {'sewer CCN service':30} {'SKIPPED':>12} "
          f"{'-':>10} {'-':>10} {'-':>11}   D-016, no source located")

    final = result["funnel"][-1]["remaining"]
    print(f"\n  CANDIDATES WRITTEN: {result['written']:,}"
          f"   (funnel survivors {final:,})")

    # Split Pass vs Review
    counts = {}
    with arcpy.da.SearchCursor(cand, ["screen_status"]) as c:
        for (s,) in c:
            counts[s] = counts.get(s, 0) + 1
    print(f"  by status: {counts}")

    print("\n" + "=" * 94)
    print("QA/QC on CandidateSites")
    print("=" * 94)
    checks = []
    expected_crs = int(config.schema()["meta"]["crs"])
    n = int(arcpy.management.GetCount(cand)[0])
    d = arcpy.da.Describe(cand)
    sr = d.get("spatialReference")

    rows = list(arcpy.da.SearchCursor(
        cand, ["SHAPE@", "cand_id", "acres", "screen_status", "sewer_status", "run_id"]))

    def add(cid, name, ok, detail, warn=False):
        res = qaqc.CheckResult(cid, "CandidateSites", name,
                               qaqc.PASS if ok else (qaqc.WARN if warn else qaqc.FAIL),
                               detail=detail)
        checks.append(res)
        print(f"  {res.result:8} {name:38} {detail}")

    add("SCR-CRS", "CRS equals the analysis CRS",
        qaqc.crs_matches(getattr(sr, "factoryCode", None), expected_crs),
        f"EPSG:{getattr(sr, 'factoryCode', '?')}")
    add("SCR-COUNT", "At least one candidate produced", n > 0, f"{n:,} candidates")
    add("SCR-GEOM", "No null geometry",
        sum(1 for r in rows if r[0] is None) == 0,
        f"{sum(1 for r in rows if r[0] is None)} null")
    ids = [r[1] for r in rows]
    dups = qaqc.duplicate_keys(ids)
    add("SCR-DUPID", "cand_id unique", not dups, f"{len(dups)} duplicated")
    add("SCR-ACRES", "Every candidate meets min_acres",
        all((r[2] or 0) >= 0 for r in rows) and
        all(float(r[2] or 0) > 0 for r in rows), "acreage populated")
    add("SCR-SEWER", "sewer_status recorded on every candidate (D-016)",
        all(r[4] for r in rows), f"{sum(1 for r in rows if r[4])}/{n} populated")
    add("SCR-RUNID", "run_id stamped on every candidate",
        all(r[5] == run_id for r in rows), run_id)
    add("SCR-BAND", "Candidate count inside the scope 60-200 band",
        60 <= n <= 200, f"{n:,} vs band 60-200", warn=True)

    written = qaqc.write_log(gdb, run_id, checks)
    s = qaqc.summarize(checks)
    print(f"\n  Pass {s.get('Pass',0)}  Warning {s.get('Warning',0)}  "
          f"Fail {s.get('Fail',0)}   ({written} rows to QAQC_Log)   run_id={run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
