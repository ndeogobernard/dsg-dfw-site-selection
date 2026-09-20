#!/usr/bin/env python3
"""Sync curated hub files out to the spoke repositories.

The hub is authoritative. Each spoke is a focused extract of hub files,
republished as a standalone repository. `tools/spokes.yaml` is the single
source of truth for which hub files feed which spoke, so a re-sync is
deterministic rather than remembered.

This script only copies files the manifest names. It never deletes anything in
a spoke and never touches a spoke's own README, CI, or git state - those are
the spoke's own content.

Usage:
    python tools/sync_spokes.py --list
    python tools/sync_spokes.py --dry-run
    python tools/sync_spokes.py --spoke arcgis-location-intelligence-toolbox
    python tools/sync_spokes.py                  # sync all
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

import yaml

HUB = Path(__file__).resolve().parents[1]
MANIFEST = HUB / "tools" / "spokes.yaml"
DEFAULT_PARENT = HUB.parent          # spokes live beside the hub


def load_manifest() -> list[dict]:
    with open(MANIFEST, encoding="utf-8") as fh:
        return yaml.safe_load(fh)["spokes"]


def sync_one(spoke: dict, parent: Path, dry_run: bool) -> tuple[int, int, list[str]]:
    root = parent / spoke["name"]
    copied = unchanged = 0
    missing: list[str] = []

    for d in spoke.get("dirs", []) or []:
        target = root / d
        if not dry_run:
            target.mkdir(parents=True, exist_ok=True)
            keep = target / ".gitkeep"
            if not any(target.iterdir()):
                keep.touch()

    for entry in spoke.get("files", []) or []:
        src = HUB / entry["from"]
        dst = root / entry["to"]
        if not src.exists():
            missing.append(entry["from"])
            continue
        if dst.exists() and filecmp.cmp(src, dst, shallow=False):
            unchanged += 1
            continue
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        copied += 1
        print(f"    {'would copy' if dry_run else 'copied'}  {entry['from']} -> {entry['to']}")

    return copied, unchanged, missing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spoke", help="sync only this spoke")
    ap.add_argument("--parent", default=str(DEFAULT_PARENT),
                    help="directory holding the spoke repos (default: beside the hub)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list", action="store_true", help="list spokes and exit")
    args = ap.parse_args()

    spokes = load_manifest()
    if args.list:
        for s in spokes:
            n_files = len(s.get("files", []) or [])
            n_pend = len(s.get("pending", []) or [])
            print(f"  {s['name']:44} {s['kind']:9} {n_files:2} files, {n_pend} pending")
        return 0

    if args.spoke:
        spokes = [s for s in spokes if s["name"] == args.spoke]
        if not spokes:
            print(f"No such spoke: {args.spoke}")
            return 1

    parent = Path(args.parent).resolve()
    total_missing: list[str] = []
    for s in spokes:
        print(f"\n{s['name']}  ({s['kind']})")
        copied, unchanged, missing = sync_one(s, parent, args.dry_run)
        print(f"    {copied} copied, {unchanged} already current")
        if missing:
            total_missing += missing
            for m in missing:
                print(f"    MISSING IN HUB: {m}")
        pending = s.get("pending", []) or []
        if pending:
            print(f"    {len(pending)} pending (not yet created in the hub)")

    if total_missing:
        print(f"\n{len(total_missing)} manifest entries missing from the hub - "
              f"fix the manifest or the hub.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
