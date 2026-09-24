#!/usr/bin/env python3
"""Stage B validation and Stage C network analysis on the Tarrant slice.

    python tools/run_network_analysis.py --validate        # Stage B route checks
    python tools/run_network_analysis.py --stores          # ingest the store set
    python tools/run_network_analysis.py --stage-c         # served set + SAs + OD
    python tools/run_network_analysis.py --all
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import arcpy  # noqa: E402
from li import config, logging_utils, network, qaqc, roads, stores  # noqa: E402


def _qa(checks, cid, target, name, ok, detail, warn=False):
    r = qaqc.CheckResult(cid, target, name,
                         qaqc.PASS if ok else (qaqc.WARN if warn else qaqc.FAIL),
                         detail=detail)
    checks.append(r)
    print("  %-8s %-46s %s" % (r.result, name, detail))
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--stores", action="store_true")
    ap.add_argument("--stage-c", action="store_true")
    ap.add_argument("--od-only", action="store_true",
                    help="rebuild only the OD matrix, reusing the service areas")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    if args.all:
        args.validate = args.stores = args.stage_c = True

    run_id = logging_utils.make_run_id("network")
    logging_utils.get_logger("li", log_dir=Path(config.paths()["logs_dir"]),
                             run_id=run_id, level=logging.INFO)
    gdb = config.paths()["gdb"]
    net = config.network()
    checks = []

    if args.validate:
        print("\n" + "=" * 94)
        print("STAGE B - ROUTE VALIDATION")
        print("=" * 94)
        for mode in ("Driving", "Truck"):
            v = roads.validate_routes(gdb, net, mode)
            print("\n  %s: %d/%d solved, %d/%d within +/-%s%%" % (
                mode, v["solved"], v["total"], v["within_tolerance"], v["total"],
                net["validation_routes"]["tolerance_pct"]))
            for r in v["routes"]:
                if r["solved"]:
                    print("    %-26s %7.1f mi (ref %4s)  %7.1f min (ref %4s)  %s"
                          % (r["name"], r["miles"], r["ref_miles"], r["minutes"],
                             r["ref_minutes"],
                             "ok" if r["within_tolerance"] else "OFF"))
                else:
                    print("    %-26s DID NOT SOLVE" % r["name"])
            _qa(checks, "NET-SOLVE-%s" % mode[:3].upper(), net["build"]["nd_name"],
                "%s: every reference route solves" % mode,
                v["solved"] == v["total"], "%d/%d" % (v["solved"], v["total"]))
            _qa(checks, "NET-TIME-%s" % mode[:3].upper(), net["build"]["nd_name"],
                "%s: times within tolerance" % mode,
                v["within_tolerance"] == v["total"],
                "%d/%d" % (v["within_tolerance"], v["total"]), warn=True)

    if args.stores:
        print("\n" + "=" * 94)
        print("STORE SET (scope 2.2, S21 via OpenStreetMap)")
        print("=" * 94)
        s = stores.ingest_stores(gdb, run_id=run_id)
        for b, n in sorted(s["by_banner"].items(), key=lambda x: -x[1]):
            print("  %-26s %4d" % (b, n))
        print("  %-26s %4d" % ("TOTAL", s["loaded"]))
        _qa(checks, "STR-COUNT", "Stores_DSG", "Store set is non-empty",
            s["loaded"] > 0, "%d stores" % s["loaded"])
        _qa(checks, "STR-SCOPE", "Stores_DSG",
            "Store count near the scope's '100+' expectation",
            s["loaded"] >= 100, "%d found (OSM coverage is a floor)" % s["loaded"],
            warn=True)

    if args.od_only:
        print("\n" + "=" * 94)
        print("OD MATRIX ONLY")
        print("=" * 94)
        od = network.build_od_stores(gdb, run_id=run_id, net=net)
        print("  OD_Cand_to_Stores    %s pairs, %d candidates x %d served stores"
              % (format(od["pairs"], ","), od["candidates"], od["served_stores"]))
        _qa(checks, "OD-COVER", "OD_Cand_to_Stores",
            "Every candidate reaches at least one store",
            not od["unreachable"], "%d unreachable" % len(od["unreachable"]))
        per = od["reached_per_cand"]
        vals = sorted(per.values())
        print("  stores reached per candidate: min %d  median %d  max %d"
              % (vals[0], vals[len(vals) // 2], vals[-1]))
        _qa(checks, "OD-DEST", "OD_Cand_to_Stores",
            "No candidate reaches more stores than are served",
            vals[-1] <= od["served_stores"],
            "max %d vs %d served" % (vals[-1], od["served_stores"]))
        with arcpy.da.SearchCursor(gdb + "\\OD_Cand_to_Stores",
                                   ["truck_minutes", "truck_miles"]) as c:
            rows = [(m, mi) for m, mi in c if m is not None]
        mins = sorted(r[0] for r in rows)
        implausible = [r for r in rows if r[1] > 0 and (r[1] / (r[0] / 60.0)) > 80]
        print("  truck minutes: min %.0f  median %.0f  max %.0f"
              % (mins[0], mins[len(mins) // 2], mins[-1]))
        _qa(checks, "OD-SPEED", "OD_Cand_to_Stores",
            "No pair implies an average speed above 80 mph", not implausible,
            "%d implausible of %s" % (len(implausible), format(len(rows), ",")))
        _qa(checks, "OD-CUTOFF", "OD_Cand_to_Stores",
            "No pair exceeds the 10-hour cutoff",
            mins[-1] <= float(net["od_matrices"]["stores"]["cutoff_min"]),
            "max %.0f min" % mins[-1])

    if args.stage_c:
        print("\n" + "=" * 94)
        print("STAGE C - SERVED SET, SERVICE AREAS, OD MATRIX")
        print("=" * 94)

        ss = network.compute_served_set(gdb, run_id=run_id, net=net)
        print("\n  served set: %d of %d stores within %.0f truck-minutes "
              "of the MSA centroid" % (ss["served"], ss["stores"], ss["cutoff_min"]))
        _qa(checks, "SRV-ANY", "StoreServiceSet", "At least one store is served",
            ss["served"] > 0, "%d served, %d beyond the cutoff"
            % (ss["served"], ss["unreached"]))

        # Driving only. The 138-candidate Truck isochrones of scope 5.2 feed no
        # criterion in criteria.yaml and cost hours at 60/120/240 minutes over a
        # sixteen-state network; the truck reach that the served set actually
        # rests on is centred on the MSA centroid and is produced below. D-020.
        sa = network.build_service_areas(gdb, run_id=run_id, mode="Driving", net=net)
        print("  ServiceAreas_Driving %5d polygons, %3d facilities, %d failed"
              % (sa["polygons"], sa["facilities"], len(sa["failed"])))
        _qa(checks, "SA-DRI", "ServiceAreas_Driving",
            "Driving service areas for every candidate", not sa["failed"],
            "%d polygons, %d candidates with none"
            % (sa["polygons"], len(sa["failed"])))
        _qa(checks, "SA-BREAKS", "ServiceAreas_Driving",
            "One polygon per candidate per break",
            sa["polygons"] == sa["facilities"] * len(sa["breaks"]),
            "%d vs %d expected"
            % (sa["polygons"], sa["facilities"] * len(sa["breaks"])))
        _qa(checks, "SA-REACH-FULL", "ServiceAreas_Driving",
            "Every candidate reaches the largest break",
            not sa["marooned"],
            "%d marooned: %s" % (len(sa["marooned"]),
                                 ", ".join("%s@%.2fmin" % m
                                           for m in sa["marooned"][:5])),
            warn=True)

        reach = network.build_served_reach(gdb, run_id=run_id, net=net)
        print("  ServiceAreas_Truck   %5d reach polygons from the MSA centroid"
              % reach["polygons"])
        for b in reach["bands"]:
            print("    <= %4.0f truck-min   %3d stores" % (b, reach["stores_per_band"][b]))
        print("    beyond             %3d stores" % reach["beyond"])
        _qa(checks, "SA-REACH", "ServiceAreas_Truck",
            "Truck reach bands produced from the MSA centroid",
            reach["polygons"] == len(reach["bands"]),
            "%d of %d bands" % (reach["polygons"], len(reach["bands"])))

        od = network.build_od_stores(gdb, run_id=run_id, net=net)
        print("  OD_Cand_to_Stores    %s pairs, %d candidates x %d served stores"
              % (format(od["pairs"], ","), od["candidates"], od["served_stores"]))
        _qa(checks, "OD-COVER", "OD_Cand_to_Stores",
            "Every candidate reaches at least one store",
            not od["unreachable"],
            "%d unreachable" % len(od["unreachable"]))

        per = od["reached_per_cand"]
        if per:
            vals = sorted(per.values())
            print("  stores reached per candidate: min %d  median %d  max %d"
                  % (vals[0], vals[len(vals) // 2], vals[-1]))
            _qa(checks, "OD-EVEN", "OD_Cand_to_Stores",
                "All candidates reach the same store count",
                vals[0] == vals[-1],
                "min %d, max %d" % (vals[0], vals[-1]), warn=True)

        with arcpy.da.SearchCursor(gdb + "\\OD_Cand_to_Stores",
                                   ["truck_minutes", "truck_miles"]) as c:
            rows = [(m, mi) for m, mi in c if m is not None]
        if rows:
            mins = sorted(r[0] for r in rows)
            implausible = [r for r in rows if r[1] > 0 and (r[1] / (r[0] / 60.0)) > 80]
            print("  truck minutes: min %.0f  median %.0f  max %.0f"
                  % (mins[0], mins[len(mins) // 2], mins[-1]))
            _qa(checks, "OD-SPEED", "OD_Cand_to_Stores",
                "No pair implies an average speed above 80 mph",
                not implausible, "%d implausible of %s"
                % (len(implausible), format(len(rows), ",")))
            _qa(checks, "OD-CUTOFF", "OD_Cand_to_Stores",
                "No pair exceeds the 10-hour cutoff",
                mins[-1] <= float(net["od_matrices"]["stores"]["cutoff_min"]),
                "max %.0f min" % mins[-1])

    if checks:
        written = qaqc.write_log(gdb, run_id, checks)
        s = qaqc.summarize(checks)
        print("\n  QA: Pass %d  Warning %d  Fail %d   (%d rows to QAQC_Log)  run_id=%s"
              % (s.get("Pass", 0), s.get("Warning", 0), s.get("Fail", 0),
                 written, run_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
