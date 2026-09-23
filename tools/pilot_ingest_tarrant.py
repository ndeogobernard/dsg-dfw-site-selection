#!/usr/bin/env python3
"""Pilot ingest: Tarrant County parcels only, then QA/QC.

Deliberately one county. The other ten are not cleared for ingest and the tool
refuses them; this run exists to prove the pipeline end to end on the one
county whose field map has been verified against the live source.

Usage:
    python tools/pilot_ingest_tarrant.py [--max-pages N] [--fresh]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from li import config, etl, logging_utils, qaqc  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=0,
                    help="stop after N pages (0 = all)")
    ap.add_argument("--fresh", action="store_true",
                    help="re-download even if raw pages already exist")
    args = ap.parse_args()

    run_id = logging_utils.make_run_id("pilot")
    log_dir = Path(config.paths()["logs_dir"])
    logging_utils.get_logger("li", log_dir=log_dir, run_id=run_id, level=logging.INFO)
    log = logging.getLogger("li.pilot")

    t0 = time.time()
    log.info("PILOT INGEST - Tarrant County only")
    log.info("run_id %s | git %s", run_id, logging_utils.git_commit()[:10])

    summary = etl.ingest_county_parcels(
        county="tarrant",
        run_id=run_id,
        source_id="S01",
        max_pages=args.max_pages or None,
        reuse_download=not args.fresh,
    )
    log.info("ingest finished in %.1f min", (time.time() - t0) / 60)

    gdb = config.paths()["gdb"]
    fc = str(Path(gdb) / "Cadastral" / "Parcels")
    expected_crs = int(config.schema()["meta"]["crs"])

    log.info("running QA/QC")
    results = qaqc.run_parcel_checks(fc, gdb, expected_crs,
                                     expected_min_features=1)
    written = qaqc.write_log(gdb, run_id, results)
    counts = qaqc.summarize(results)

    print("\n" + "=" * 86)
    print("QA/QC RESULTS")
    print("=" * 86)
    for r in results:
        print(f"  {r.result:<8} {r.check_id:<18} {r.check_name:<44} {r.detail}")
    print("-" * 86)
    print(f"  Pass {counts.get('Pass', 0)}   Warning {counts.get('Warning', 0)}   "
          f"Fail {counts.get('Fail', 0)}   ({written} rows written to QAQC_Log)")
    print("=" * 86)
    print("\nINGEST SUMMARY")
    for k, v in summary.items():
        print(f"  {k:<22} {v}")
    print(f"  {'total_minutes':<22} {(time.time() - t0) / 60:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
