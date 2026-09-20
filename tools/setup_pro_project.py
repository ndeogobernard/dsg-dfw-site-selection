#!/usr/bin/env python3
"""Create and wire up pro/DFW_DSG.aprx.

A blank .aprx cannot be authored from nothing by arcpy - arcpy.mp.ArcGISProject
opens an existing file, it does not create one. ArcGIS Pro does ship a blank
project used by its routing-service tools, so this copies that and configures
it, which keeps the project reproducible from the repo rather than depending on
someone remembering the right sequence of clicks.

Idempotent: re-running rebuilds the project from the template.

Usage:
    python tools/setup_pro_project.py [--force]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import arcpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from li import config  # noqa: E402

BLANK = Path(
    r"C:\Program Files\ArcGIS\Pro\Resources\ArcToolBox\Services"
    r"\routingservices\data\Blank.aprx"
)


def write_empty_atbx(path: Path, alias: str, title: str, descr: str) -> None:
    """Write an empty ArcGIS Pro .atbx toolbox.

    An .atbx is a zip archive containing a `toolbox.content` manifest and a
    `toolbox.content.rc` string table, with one folder per tool. With no tools,
    those two members are the whole file.
    """
    import json
    import zipfile

    content = {
        "version": "1.0",
        "alias": alias,
        "displayname": "$rc:title",
        "description": "$rc:descr",
        "toolsets": {"<root>": {"tools": []}},
    }
    rc = {"map": {"descr": descr, "title": title}}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("toolbox.content", json.dumps(content, indent=4))
        z.writestr("toolbox.content.rc", json.dumps(rc, indent=4))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="overwrite an existing .aprx")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    pro_dir = repo / "pro"
    aprx_path = pro_dir / "DFW_DSG.aprx"
    paths = config.paths()
    gdb = Path(paths["gdb"])
    pyt = repo / "toolbox" / "LocationIntelligence.pyt"

    if aprx_path.exists() and not args.force:
        print(f"{aprx_path} already exists. Re-run with --force to rebuild.")
        return 1
    if not BLANK.exists():
        print(f"ERROR: blank project template not found at {BLANK}")
        print("Create the project by hand in Pro (File > New Project) and save it to pro/.")
        return 2

    pro_dir.mkdir(parents=True, exist_ok=True)
    if aprx_path.exists():
        aprx_path.unlink()
    shutil.copy2(BLANK, aprx_path)
    print(f"copied blank template -> {aprx_path}")

    # The stock Blank.aprx points at a Blank.atbx and Blank.gdb that are not
    # actually shipped beside it, so those entries are replaced rather than
    # inherited. A project must have a valid default toolbox - updateToolboxes
    # raises "No valid default toolbox was set" otherwise - and Pro 3.5's arcpy
    # has no CreateToolbox tool. An .atbx is a zip holding a JSON manifest, so
    # an empty one is written directly.
    atbx = pro_dir / "DFW_DSG.atbx"
    if not atbx.exists():
        write_empty_atbx(atbx, alias="dfwdsg", title="DFW_DSG",
                         descr="Project toolbox for the DICK'S DFW site-selection project.")
        print(f"default toolbox      -> {atbx}")

    aprx = arcpy.mp.ArcGISProject(str(aprx_path))

    # Home folder is the project folder, so everything the project writes by
    # default lands inside the repo rather than in the template's temp folder.
    aprx.homeFolder = str(pro_dir)

    # Default geodatabase. The GDB lives outside the repo (config/paths.yaml),
    # so this is stored absolute by necessity - see docs/DECISIONS.md D-010.
    if gdb.exists():
        aprx.updateDatabases([{"databasePath": str(gdb), "isDefaultDatabase": True}])
        print(f"defaultGeodatabase   -> {gdb}")
    else:
        print(f"WARNING: {gdb} does not exist yet - run BuildGeodatabaseSchema first.")
        print("         Clearing the template's dangling database entry.")
        aprx.updateDatabases([])

    # Toolboxes: the project's own .atbx as default, plus the Python toolbox.
    tbx = [{"toolboxPath": str(atbx), "isDefaultToolbox": True}]
    if pyt.exists():
        tbx.append({"toolboxPath": str(pyt), "isDefaultToolbox": False})
        print(f"python toolbox       -> {pyt}")
    else:
        print(f"WARNING: {pyt} not found - Python toolbox not added.")
    aprx.updateToolboxes(tbx)

    # Folder connections: the repo (configs, toolbox, outputs) and the data root.
    wanted = [repo, Path(paths["data_root"])]
    folders = aprx.folderConnections
    have = {Path(f["connectionString"]).resolve() for f in folders}
    for p in wanted:
        if p.exists() and p.resolve() not in have:
            folders.append({"connectionString": str(p), "alias": p.name, "isHomeFolder": False})
            print(f"folder connection    -> {p}")
    aprx.updateFolderConnections(folders, validate=False)

    # Name the default map for the work it will hold.
    for m in aprx.listMaps():
        m.name = "DFW Site Selection"
        break

    aprx.save()
    del aprx
    print(f"\nsaved {aprx_path}  ({aprx_path.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
