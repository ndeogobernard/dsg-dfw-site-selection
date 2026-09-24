#!/usr/bin/env python3
"""Download and ingest the OSM road network, then build RoadNetwork_ND.

Stage B of the vertical slice Part 2. Source is OpenStreetMap via Geofabrik
per D-004.

Usage:
    python tools/ingest_roads.py --download-only
    python tools/ingest_roads.py --extract-only
    python tools/ingest_roads.py                 # download + extract + build
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from li import config, logging_utils, roads  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download-only", action="store_true")
    ap.add_argument("--extract-only", action="store_true")
    ap.add_argument("--load-only", action="store_true")
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--states", help="comma-separated slugs, default all 16")
    args = ap.parse_args()

    run_id = logging_utils.make_run_id("roads")
    logging_utils.get_logger("li", log_dir=Path(config.paths()["logs_dir"]),
                             run_id=run_id, level=logging.INFO)
    log = logging.getLogger("li.roads_cli")
    cfg = roads.road_cfg()
    slugs = args.states.split(",") if args.states else roads.state_slugs(cfg)

    log.info("=" * 92)
    log.info("ROAD NETWORK INGEST  run_id=%s  source=%s", run_id, cfg["dataset"])
    log.info("  %d states, %.1f GB to fetch", len(slugs),
             sum(s["mb"] for s in cfg["states"]) / 1000.0)
    log.info("  licence: %s", cfg["license"])

    if args.build_only:
        r = roads.build_network(run_id=run_id)
        log.info("built %s over %s segments: %s", r["nd"],
                 format(r["segments"], ","), ", ".join(r["attributes"]))
        return 0

    if args.load_only:
        roads.load_roads(run_id=run_id, cfg=cfg)
        r = roads.build_network(run_id=run_id)
        log.info("built %s over %s segments: %s", r["nd"],
                 format(r["segments"], ","), ", ".join(r["attributes"]))
        return 0

    if not args.extract_only:
        roads.download_extracts(slugs=slugs, cfg=cfg)
        if args.download_only:
            log.info("download complete; stopping (--download-only)")
            return 0

    results = roads.extract_all(cfg=cfg, slugs=slugs)

    log.info("=" * 92)
    log.info("EXTRACT SUMMARY")
    log.info("  %-28s %10s %10s", "layer", "segments", "dropped")
    for r in results:
        log.info("  %-28s %10s %10s", Path(r["gpkg"]).stem,
                 format(r["kept"], ","), format(r["skipped"], ","))
    log.info("  %-28s %10s", "TOTAL", format(sum(r["kept"] for r in results), ","))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
