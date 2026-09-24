"""Ingest the physical-filter layers for a county slice (scope §3, §5.1).

Everything here is driven by `config/sources.yaml → slice` and
`→ physical_layers`; no endpoint, threshold, or field name is hard-coded.

Three acquisition shapes are supported, because the sources genuinely differ:

* **REST feature layers** (flood, wetlands, CCN, roads, buildings) — paged
  server-side with a spatial filter so only the slice is downloaded.
* **ImageServer rasters** (3DEP elevation) — exported over the slice extent.
* **WCS coverages** (NLCD land cover) — the Esri and USGS NLCD ImageServers
  both require a token; MRLC's WCS is open and serves the same product.

Requires arcpy for everything after the download.
"""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Any, Sequence

import requests

from . import config
from .etl import registry_row, write_registry_row

try:  # pragma: no cover
    import arcpy
except ImportError:  # pragma: no cover
    arcpy = None

log = logging.getLogger("li.layers")

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "dsg-dfw-site-selection layer ingest"})


def _require_arcpy() -> None:
    if arcpy is None:
        raise ImportError("arcpy is required for li.layers")


# ---------------------------------------------------------------------------
# Pure helpers - unit-tested without arcpy
# ---------------------------------------------------------------------------

def parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    """'xmin,ymin,xmax,ymax' -> floats, validated."""
    parts = [float(x) for x in str(bbox).split(",")]
    if len(parts) != 4:
        raise ValueError(f"bbox must have 4 values, got {len(parts)}")
    xmin, ymin, xmax, ymax = parts
    if xmin >= xmax or ymin >= ymax:
        raise ValueError(f"degenerate bbox: {bbox}")
    return xmin, ymin, xmax, ymax


def expand_bbox(bbox: str, miles: float) -> tuple[float, float, float, float]:
    """Grow a WGS84 bbox by a buffer in miles.

    Longitude degrees shrink with latitude, so the east-west expansion is
    divided by cos(lat) at the box's mid-latitude. Adequate for a buffer whose
    only job is to stop edge effects at a county line.
    """
    xmin, ymin, xmax, ymax = parse_bbox(bbox)
    dlat = miles / 69.0
    midlat = math.radians((ymin + ymax) / 2.0)
    dlon = miles / (69.0 * max(math.cos(midlat), 0.1))
    return xmin - dlon, ymin - dlat, xmax + dlon, ymax + dlat


def derive_flag(attrs: dict[str, Any], rule: dict[str, Any]) -> int:
    """Evaluate a config-declared derivation rule to 0/1.

    Supports `equals` (exact, case-insensitive) and `contains` (substring).
    Recon 3: NFHL publishes SFHA as "T"/"F" text and has no floodway field at
    all, so both flags must be derived rather than read.
    """
    raw = attrs.get(rule["from"])
    if raw is None:
        return 0
    value = str(raw).strip().upper()
    if "equals" in rule:
        return int(value == str(rule["equals"]).strip().upper())
    if "contains" in rule:
        return int(str(rule["contains"]).strip().upper() in value)
    raise ValueError(f"unsupported derivation rule: {rule}")


def strip_prefix(name: str) -> str:
    """'Wetlands.ATTRIBUTE' -> 'ATTRIBUTE'.

    The NWI service is a joined layer, so its fields arrive dotted; arcpy
    renames them on conversion and the dot does not survive.
    """
    return name.split(".")[-1]


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def rest_count(service: str, bbox: Sequence[float] | None = None,
               where: str = "1=1") -> int:
    params: dict[str, Any] = {"where": where, "returnCountOnly": "true", "f": "json"}
    if bbox:
        params |= {"geometry": ",".join(str(x) for x in bbox),
                   "geometryType": "esriGeometryEnvelope", "inSR": 4326,
                   "spatialRel": "esriSpatialRelIntersects"}
    r = _SESSION.get(f"{service}/query", params=params, timeout=180)
    return int(r.json().get("count", 0))


def download_rest(service: str, out_dir: Path, name: str,
                  bbox: Sequence[float] | None, out_fields: Sequence[str],
                  where: str = "1=1", page_size: int = 1000,
                  geom_type: str = "POLYGON") -> list[Path]:
    """Page a REST layer to GeoJSON, filtered to the slice."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    offset, page, t0 = 0, 0, time.time()

    while True:
        params: dict[str, Any] = {
            "where": where,
            "outFields": ",".join(out_fields) if out_fields else "*",
            "returnGeometry": "true",
            "outSR": 4326,
            "resultOffset": offset,
            "resultRecordCount": page_size,
            "f": "geojson",
        }
        if bbox:
            params |= {"geometry": ",".join(str(x) for x in bbox),
                       "geometryType": "esriGeometryEnvelope", "inSR": 4326,
                       "spatialRel": "esriSpatialRelIntersects"}

        # Some servers advertise a maxRecordCount they cannot actually serve for
        # wide geometries - FEMA's NFHL returns HTTP 500 at 500 rows but is fine
        # at 250. Halve the page and retry rather than abandoning the layer.
        payload = None
        size = params["resultRecordCount"]
        for attempt in range(4):
            params["resultRecordCount"] = size
            r = _SESSION.get(f"{service}/query", params=params, timeout=300)
            if r.status_code == 200 and r.text.lstrip().startswith("{"):
                payload = r.json()
                if "error" not in payload:
                    break
            if size <= 50:
                r.raise_for_status()
                raise RuntimeError(f"{name}: server rejected even a 50-row page")
            size = max(50, size // 2)
            log.warning("    %s: HTTP %s at offset %d, retrying with page=%d",
                        name, r.status_code, offset, size)
            time.sleep(1.5 * (attempt + 1))
        if payload is None:
            raise RuntimeError(f"{name}: no usable response at offset {offset}")
        page_size = size
        feats = payload.get("features", [])
        if not feats:
            break
        p = out_dir / f"{name}_{page:04d}.geojson"
        p.write_text(json.dumps(payload), encoding="utf-8")
        written.append(p)
        page += 1
        offset += len(feats)
        if page % 10 == 0:
            log.info("    %s: %d features in %.0fs", name, offset, time.time() - t0)
        if len(feats) < page_size:
            break

    log.info("  %s: downloaded %d features to %d pages in %.0fs",
             name, offset, len(written), time.time() - t0)
    return written



def tile_bbox(bbox, nx: int, ny: int):
    """Split a bbox into an nx by ny grid of sub-bboxes."""
    xmin, ymin, xmax, ymax = bbox
    dx = (xmax - xmin) / nx
    dy = (ymax - ymin) / ny
    return [(xmin + i * dx, ymin + j * dy, xmin + (i + 1) * dx, ymin + (j + 1) * dy)
            for i in range(nx) for j in range(ny)]


def download_rest_tiled(service, out_dir: Path, name: str, bbox,
                        out_fields, where: str = "1=1", page_size: int = 1000,
                        tiles: int = 6, max_offset: int = 2000):
    """Download a layer tile by tile instead of deep-paging one big extent.

    Some services cannot serve a deep `resultOffset` over a wide geometry - the
    FWS wetlands service returns the first couple of pages for the Tarrant
    envelope and then times out at offset 2000, whatever the page size. Tiling
    keeps every request's extent small and its offset shallow, which is the
    difference between a layer that downloads and one that does not.

    A tile that still cannot be drained within `max_offset` is split again.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    total, page, t0 = 0, 0, time.time()
    queue = list(tile_bbox(bbox, tiles, tiles))
    log.info("  %s: %d tiles", name, len(queue))

    while queue:
        tile = queue.pop(0)
        try:
            n_tile = rest_count(service, tile, where)
        except Exception as exc:
            log.warning("    %s: count failed on tile, splitting (%s)", name, type(exc).__name__)
            queue.extend(tile_bbox(tile, 2, 2))
            continue
        if n_tile == 0:
            continue
        if n_tile > max_offset:
            queue.extend(tile_bbox(tile, 2, 2))      # too deep to page; subdivide
            continue

        offset = 0
        while True:
            params = {
                "where": where,
                "outFields": ",".join(out_fields) if out_fields else "*",
                "returnGeometry": "true", "outSR": 4326,
                "resultOffset": offset, "resultRecordCount": page_size,
                "f": "geojson",
                "geometry": ",".join(str(x) for x in tile),
                "geometryType": "esriGeometryEnvelope", "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
            }
            try:
                r = _SESSION.get(f"{service}/query", params=params, timeout=180)
            except Exception as exc:
                log.warning("    %s: %s on tile, splitting", name, type(exc).__name__)
                queue.extend(tile_bbox(tile, 2, 2))
                break
            if r.status_code != 200 or not r.text.lstrip().startswith("{"):
                queue.extend(tile_bbox(tile, 2, 2))
                break
            feats = r.json().get("features", [])
            if not feats:
                break
            p = out_dir / f"{name}_{page:04d}.geojson"
            p.write_text(r.text, encoding="utf-8")
            written.append(p)
            page += 1
            total += len(feats)
            offset += len(feats)
            if page % 10 == 0:
                log.info("    %s: %d features, %d tiles left, %.0fs",
                         name, total, len(queue), time.time() - t0)
            if len(feats) < page_size:
                break

    log.info("  %s: downloaded %d features to %d pages in %.0fs",
             name, total, len(written), time.time() - t0)
    return written

# ---------------------------------------------------------------------------
# Slice extent
# ---------------------------------------------------------------------------

def build_slice_boundary(gdb: str, out_name: str = "SliceBoundary") -> str:
    """County boundary buffered by the configured distance, in the analysis CRS."""
    _require_arcpy()
    cfg = config.sources()["slice"]
    target_crs = int(config.schema()["meta"]["crs"])
    raw = Path(config.paths()["raw_dir"]) / "slice"
    interim = Path(config.paths()["interim_dir"])

    pages = download_rest(cfg["boundary_service"], raw, "boundary",
                          bbox=None, out_fields=["COUNTY"], page_size=100)
    from .etl import geojson_to_feature_class
    county = geojson_to_feature_class(pages, gdb, "_slice_county", target_crs,
                                      interim_dir=interim)
    out = f"{gdb}\\{out_name}"
    if arcpy.Exists(out):
        arcpy.management.Delete(out)
    arcpy.analysis.PairwiseBuffer(county, out, f"{cfg['buffer_miles']} Miles")
    arcpy.management.Delete(county)
    log.info("  slice boundary: county + %s mi buffer", cfg["buffer_miles"])
    return out


# ---------------------------------------------------------------------------
# Vector layer ingest
# ---------------------------------------------------------------------------

def ingest_vector(key: str, gdb: str | None = None, run_id: str = "",
                  where: str = "1=1") -> dict[str, Any]:
    """Download, reproject, field-map and load one configured vector layer."""
    _require_arcpy()
    from .etl import geojson_to_feature_class

    srcs = config.sources()
    cfg = srcs["physical_layers"][key]
    if cfg.get("acquisition") != "AUTO" or not cfg.get("service"):
        return {"layer": key, "status": "SKIPPED",
                "reason": cfg.get("status") or "no service configured"}

    gdb = gdb or config.paths()["gdb"]
    target = cfg["target"]
    target_crs = int(config.schema()["meta"]["crs"])
    bbox = expand_bbox(srcs["slice"]["bbox_wgs84"], srcs["slice"]["buffer_miles"])
    raw = Path(config.paths()["raw_dir"]) / srcs["slice"]["name"] / key
    interim = Path(config.paths()["interim_dir"])

    log.info("=" * 68)
    log.info("ingest %s -> %s", key, target)

    available = rest_count(cfg["service"], bbox, where)
    log.info("  %d features in slice at source", available)
    if available == 0:
        return {"layer": key, "status": "EMPTY", "loaded": 0}

    cached = sorted(raw.glob(f"{key}_*.geojson"))
    if cached:
        pages = cached
    elif cfg.get("tiles"):
        pages = download_rest_tiled(
            cfg["service"], raw, key, bbox, cfg.get("out_fields") or [],
            where=where, page_size=int(cfg.get("page_size", 1000)),
            tiles=int(cfg["tiles"]), max_offset=int(cfg.get("max_offset", 2000)))
    else:
        pages = download_rest(
            cfg["service"], raw, key, bbox, cfg.get("out_fields") or [],
            where=where, page_size=int(cfg.get("page_size", 1000)))

    geom = arcpy.da.Describe(f"{gdb}\\{_dataset_of(target)}\\{target}"
                             if _dataset_of(target) else f"{gdb}\\{target}"
                             )["shapeType"].upper()
    staged = geojson_to_feature_class(pages, gdb, f"_stage_{key}", target_crs,
                                      interim_dir=interim, geometry_type=geom)
    n_staged = int(arcpy.management.GetCount(staged)[0])

    loaded = _append_mapped(staged, gdb, target, cfg, srcs)
    arcpy.management.Delete(staged)

    write_registry_row(gdb, registry_row(
        {"source_id": cfg["source_id"], "provider": cfg.get("provider", ""),
         "dataset": cfg.get("dataset", ""), "endpoint": cfg["service"],
         "license": cfg.get("license", ""), "native_crs": cfg.get("native_crs")},
        None, notes=f"slice={srcs['slice']['name']}; {available} in slice; run_id={run_id}"))

    log.info("  loaded %s rows into %s", f"{loaded:,}", target)
    return {"layer": key, "status": "OK", "at_source": available,
            "staged": n_staged, "loaded": loaded, "target": target}


def _dataset_of(fc_name: str) -> str | None:
    return config.schema()["feature_classes"].get(fc_name, {}).get("dataset")


def _append_mapped(staged: str, gdb: str, target: str,
                   cfg: dict[str, Any], srcs: dict[str, Any]) -> int:
    """Insert staged features into the target, applying map and derivations."""
    ds = _dataset_of(target)
    dest = f"{gdb}\\{ds}\\{target}" if ds else f"{gdb}\\{target}"

    staged_fields = {f.name.upper(): f.name for f in arcpy.ListFields(staged)}
    dest_fields = {f.name for f in arcpy.ListFields(dest)}

    mapping: dict[str, str] = {}
    for schema_field, src in (cfg.get("field_map") or {}).items():
        actual = staged_fields.get(strip_prefix(str(src)).upper())
        if actual and schema_field in dest_fields:
            mapping[schema_field] = actual
    # Any out_field whose name matches a destination field, mapped implicitly.
    for src in (cfg.get("out_fields") or []):
        nm = strip_prefix(str(src))
        lowered = nm.lower()
        if lowered in dest_fields and lowered not in mapping:
            actual = staged_fields.get(nm.upper())
            if actual:
                mapping[lowered] = actual

    derives = cfg.get("derive") or {}
    derive_fields = [f for f in derives if f in dest_fields]
    derive_srcs = {f: staged_fields.get(strip_prefix(str(r["from"])).upper())
                   for f, r in derives.items() if f in dest_fields}

    read = ["SHAPE@"] + list(mapping.values()) + [
        v for v in derive_srcs.values() if v and v not in mapping.values()]
    read = list(dict.fromkeys(read))
    write = ["SHAPE@"] + list(mapping) + derive_fields
    if "source_id" in dest_fields:
        write.append("source_id")

    n = 0
    editor = arcpy.da.Editor(gdb)
    editor.startEditing(with_undo=False, multiuser_mode=False)
    editor.startOperation()
    try:
        with arcpy.da.SearchCursor(staged, read) as sc, \
             arcpy.da.InsertCursor(dest, write) as ic:
            idx = {f: i for i, f in enumerate(read)}
            for row in sc:
                attrs = {f: row[idx[f]] for f in read if f != "SHAPE@"}
                out = [row[0]]
                out += [row[idx[mapping[f]]] for f in mapping]
                out += [derive_flag({derives[f]["from"]: attrs.get(derive_srcs[f])},
                                    derives[f]) for f in derive_fields]
                if "source_id" in dest_fields:
                    out.append(cfg["source_id"])
                ic.insertRow(tuple(out))
                n += 1
        editor.stopOperation()
        editor.stopEditing(save_changes=True)
    except Exception:
        editor.abortOperation()
        editor.stopEditing(save_changes=False)
        raise
    return n


# ---------------------------------------------------------------------------
# Rasters
# ---------------------------------------------------------------------------

def _slice_extent_in(crs: int):
    """Slice bbox as an arcpy Extent in the requested CRS."""
    srcs = config.sources()
    xmin, ymin, xmax, ymax = expand_bbox(srcs["slice"]["bbox_wgs84"],
                                         srcs["slice"]["buffer_miles"])
    wgs = arcpy.SpatialReference(4326)
    tgt = arcpy.SpatialReference(int(crs))
    ll = arcpy.PointGeometry(arcpy.Point(xmin, ymin), wgs).projectAs(tgt).firstPoint
    ur = arcpy.PointGeometry(arcpy.Point(xmax, ymax), wgs).projectAs(tgt).firstPoint
    return arcpy.Extent(ll.X, ll.Y, ur.X, ur.Y)


def ingest_elevation_slope(gdb=None, run_id=""):
    """Export 3DEP elevation over the slice and derive percent slope.

    The DEM is exported ALREADY IN the analysis CRS. Slope derived in
    geographic coordinates is wrong: degrees of longitude and the vertical unit
    are not commensurable, and the error varies with latitude.
    """
    _require_arcpy()
    srcs = config.sources()
    cfg = srcs["physical_layers"]["elevation"]
    gdb = gdb or config.paths()["gdb"]
    target_crs = int(config.schema()["meta"]["crs"])

    log.info("=" * 68)
    log.info("ingest elevation -> Slope_pct")
    arcpy.CheckOutExtension("Spatial")

    raw = Path(config.paths()["raw_dir"]) / srcs["slice"]["name"] / "elevation"
    raw.mkdir(parents=True, exist_ok=True)
    tif = raw / "dem_slice.tif"

    ext = _slice_extent_in(target_crs)
    cell_m = float(cfg.get("export_cell_size_m", 10))
    cell_ft = cell_m * float(cfg.get("z_factor_to_xy", 3.28084))
    cap = int(cfg.get("max_export_px", 8000))
    chunk = int(cfg.get("export_chunk_px", 2000))
    cols = int(math.ceil((ext.XMax - ext.XMin) / cell_ft))
    rows = int(math.ceil((ext.YMax - ext.YMin) / cell_ft))
    if cols > cap or rows > cap:
        raise RuntimeError(
            "elevation: %d x %d exceeds the service cap of %d px - raise "
            "export_cell_size_m in config/sources.yaml" % (cols, rows, cap))

    if not tif.exists():
        # `exportImage` with an explicit bbox and size, rather than
        # MakeImageServerLayer + CopyRaster, which returned a 1 x 1 raster.
        #
        # The whole slice in one request is inside the service's declared 8000
        # px cap but still times out at the gateway (HTTP 504) - the cap is a
        # limit on the answer, not a promise the service can compute it. Export
        # in `export_chunk_px` blocks and mosaic them instead.
        nx = int(math.ceil(cols / chunk))
        ny = int(math.ceil(rows / chunk))
        dx = (ext.XMax - ext.XMin) / nx
        dy = (ext.YMax - ext.YMin) / ny
        parts, t0 = [], time.time()
        log.info("  DEM %d x %d px at %.2f ft -> %d x %d tiles",
                 cols, rows, cell_ft, nx, ny)
        for i in range(nx):
            for j in range(ny):
                part = raw / ("dem_%02d_%02d.tif" % (i, j))
                if not part.exists():
                    x0, x1 = ext.XMin + i * dx, ext.XMin + (i + 1) * dx
                    y0, y1 = ext.YMin + j * dy, ext.YMin + (j + 1) * dy
                    params = {
                        "bbox": "%f,%f,%f,%f" % (x0, y0, x1, y1),
                        "bboxSR": target_crs, "imageSR": target_crs,
                        "size": "%d,%d" % (int(math.ceil((x1 - x0) / cell_ft)),
                                           int(math.ceil((y1 - y0) / cell_ft))),
                        "format": "tiff", "pixelType": cfg.get("pixel_type", "F32"),
                        "interpolation": "RSP_BilinearInterpolation",
                        "noData": "", "f": "image",
                    }
                    # A tile near the size limit renders in ~80s against a ~90s
                    # gateway timeout, so a 504 here is a race rather than a
                    # rejection - the same request usually succeeds on retry.
                    last = ""
                    for attempt in range(int(cfg.get("export_retries", 3))):
                        r = _SESSION.get(cfg["service"] + "/exportImage",
                                         params=params, timeout=300)
                        ct = r.headers.get("content-type", "")
                        if r.status_code == 200 and "image" in ct:
                            break
                        last = "HTTP %s %s %s" % (r.status_code, ct, r.text[:150])
                    else:
                        raise RuntimeError("exportImage failed on tile %d,%d "
                                           "after %s attempts: %s"
                                           % (i, j, cfg.get("export_retries", 3), last))
                    part.write_bytes(r.content)
                parts.append(part)
        log.info("  fetched %d DEM tiles, %.1f MB in %.0fs", len(parts),
                 sum(p.stat().st_size for p in parts) / 1e6, time.time() - t0)

        if len(parts) == 1:
            parts[0].replace(tif)
        else:
            if arcpy.Exists(str(tif)):
                arcpy.management.Delete(str(tif))
            arcpy.management.MosaicToNewRaster(
                [str(p) for p in parts], str(raw), tif.name,
                arcpy.SpatialReference(target_crs),
                "32_BIT_FLOAT", cell_ft, 1, "LAST", "FIRST")

    dem = arcpy.Raster(str(tif))
    if dem.width < 2 or dem.height < 2:
        raise RuntimeError("elevation: DEM came back %d x %d - refusing to "
                           "derive slope from it" % (dem.width, dem.height))

    slope_out = gdb + "\\Slope_pct"
    if arcpy.Exists(slope_out):
        arcpy.management.Delete(slope_out)

    # Elevation is in metres, x/y in US survey feet. Without the z-factor every
    # slope would be understated by 3.28x and flat-looking terrain would pass.
    z_factor = float(cfg.get("z_factor_to_xy", 3.28084))
    slope = arcpy.sa.Slope(dem, "PERCENT_RISE", z_factor)
    slope.save(slope_out)

    # A raster written by `save()` carries no statistics, so `.minimum` and
    # `.maximum` come back as None and the summary log raises. Build them.
    arcpy.management.CalculateStatistics(slope_out)
    r = arcpy.Raster(slope_out)
    lo = None if r.minimum is None else float(r.minimum)
    hi = None if r.maximum is None else float(r.maximum)
    if r.width < 2 or r.height < 2:
        raise RuntimeError("elevation: Slope_pct is %d x %d" % (r.width, r.height))

    write_registry_row(gdb, registry_row(
        {"source_id": cfg["source_id"], "provider": cfg.get("provider", ""),
         "dataset": cfg.get("dataset", ""), "endpoint": cfg["service"],
         "license": cfg.get("license", ""), "native_crs": target_crs},
        None, notes="slope PERCENT_RISE at %s m, z-factor %s; run_id=%s"
                    % (cell_m, z_factor, run_id)))

    log.info("  Slope_pct %d x %d, cell %.2f ft, range %s-%s pct",
             r.width, r.height, r.meanCellWidth,
             "?" if lo is None else "%.1f" % lo,
             "?" if hi is None else "%.1f" % hi)
    return {"layer": "elevation", "status": "OK", "target": "Slope_pct",
            "cols": r.width, "rows": r.height,
            "min_pct": None if lo is None else round(lo, 2),
            "max_pct": None if hi is None else round(hi, 2)}


def ingest_land_cover(gdb=None, run_id=""):
    """Fetch the NLCD coverage for the slice over WCS and project it in."""
    _require_arcpy()
    srcs = config.sources()
    cfg = srcs["physical_layers"]["land_cover"]
    gdb = gdb or config.paths()["gdb"]
    target_crs = int(config.schema()["meta"]["crs"])
    raw = Path(config.paths()["raw_dir"]) / srcs["slice"]["name"] / "land_cover"
    raw.mkdir(parents=True, exist_ok=True)

    log.info("=" * 68)
    log.info("ingest land_cover -> LandCover_NLCD")

    native = int(cfg.get("native_crs", 5070))
    sub_crs = int(cfg.get("subsetting_crs", 4326))
    out_crs = int(cfg.get("output_crs", native))
    ax_x, ax_y = cfg.get("subset_axes", ["Long", "Lat"])
    ext = _slice_extent_in(sub_crs)
    tif = raw / "nlcd_slice.tif"

    if not tif.exists():
        # Subset in `subsetting_crs` and demand `output_crs` back. The coverage
        # is published in 3857 and GeoServer cannot write a Pseudo-Mercator
        # GeoTIFF, so a GetCoverage without `outputCrs` fails outright.
        crs_uri = "http://www.opengis.net/def/crs/EPSG/0/%d"
        params = {
            "service": "WCS", "version": "2.0.1", "request": "GetCoverage",
            "coverageId": cfg["coverage_id"], "format": "image/geotiff",
            "subset": ["%s(%f,%f)" % (ax_x, ext.XMin, ext.XMax),
                       "%s(%f,%f)" % (ax_y, ext.YMin, ext.YMax)],
            "subsettingCrs": crs_uri % sub_crs,
            "outputCrs": crs_uri % out_crs,
        }
        r = _SESSION.get(cfg["service"], params=params, timeout=600)
        ct = r.headers.get("content-type", "")
        if r.status_code != 200 or "xml" in ct:
            raise RuntimeError("WCS GetCoverage failed: HTTP %s %s %s"
                               % (r.status_code, ct, r.text[:300]))
        tif.write_bytes(r.content)
        log.info("  fetched %.1f MB from WCS", len(r.content) / 1e6)

    out = gdb + "\\LandCover_NLCD"
    if arcpy.Exists(out):
        arcpy.management.Delete(out)
    arcpy.management.ProjectRaster(str(tif), out,
                                   arcpy.SpatialReference(target_crs), "NEAREST")

    r = arcpy.Raster(out)
    write_registry_row(gdb, registry_row(
        {"source_id": cfg["source_id"], "provider": cfg.get("provider", ""),
         "dataset": cfg.get("dataset", ""), "endpoint": cfg["service"],
         "license": cfg.get("license", ""), "native_crs": out_crs},
        None, notes="WCS coverage %s subset in EPSG:%d, returned as EPSG:%d; "
                    "run_id=%s" % (cfg["coverage_id"], sub_crs, out_crs, run_id)))

    log.info("  LandCover_NLCD %d x %d, values %s-%s",
             r.width, r.height, r.minimum, r.maximum)
    return {"layer": "land_cover", "status": "OK", "target": "LandCover_NLCD",
            "cols": r.width, "rows": r.height}


# ---------------------------------------------------------------------------
# Interchanges
# ---------------------------------------------------------------------------

def ingest_interchanges(gdb=None, run_id=""):
    """Derive interchange points from limited-access centrelines.

    An interchange is approximated as a crossing between two DIFFERENT
    limited-access routes (FHWA functional system 1 Interstate, 2 Other
    Freeway/Expressway). Self-crossings of a single route - loops, and divided
    carriageways digitised as separate features - are excluded, or every ramp
    pair would register as its own interchange.
    """
    _require_arcpy()
    from .etl import geojson_to_feature_class

    srcs = config.sources()
    cfg = srcs["physical_layers"]["interchanges"]
    gdb = gdb or config.paths()["gdb"]
    target_crs = int(config.schema()["meta"]["crs"])
    bbox = expand_bbox(srcs["slice"]["bbox_wgs84"], srcs["slice"]["buffer_miles"])
    raw = Path(config.paths()["raw_dir"]) / srcs["slice"]["name"] / "interchanges"
    interim = Path(config.paths()["interim_dir"])

    fsys = cfg["derive"]["limited_access_f_system"]
    where = "F_SYSTEM IN (" + ",".join(str(int(v)) for v in fsys) + ")"

    log.info("=" * 68)
    log.info("ingest interchanges -> Interchanges   (%s)", where)

    n_src = rest_count(cfg["service"], bbox, where)
    log.info("  %d limited-access segments in slice", n_src)
    if n_src == 0:
        return {"layer": "interchanges", "status": "EMPTY", "loaded": 0}

    pages = sorted(raw.glob("interchanges_*.geojson")) or download_rest(
        cfg["service"], raw, "interchanges", bbox, cfg.get("out_fields") or [],
        where=where, page_size=int(cfg.get("page_size", 1000)))

    lines = geojson_to_feature_class(pages, gdb, "_stage_lim_access", target_crs,
                                     interim_dir=interim,
                                     geometry_type="POLYLINE")

    pts = gdb + "\\_ix_points"
    if arcpy.Exists(pts):
        arcpy.management.Delete(pts)
    arcpy.analysis.Intersect([lines, lines], pts, "ALL", None, "POINT")

    flds = {f.name.upper(): f.name for f in arcpy.ListFields(pts)}
    a = flds.get("HWY") or flds.get("RIA_RTE_ID")
    b = flds.get("HWY_1") or flds.get("RIA_RTE_ID_1")

    kept = gdb + "\\_ix_distinct"
    if arcpy.Exists(kept):
        arcpy.management.Delete(kept)
    if a and b:
        lyr = "ixlyr"
        if arcpy.Exists(lyr):
            arcpy.management.Delete(lyr)
        arcpy.management.MakeFeatureLayer(pts, lyr, "%s <> %s" % (a, b))
        arcpy.management.CopyFeatures(lyr, kept)
        arcpy.management.Delete(lyr)
    else:
        arcpy.management.CopyFeatures(pts, kept)

    # `Intersect` with POINT output returns MULTIPOINT geometry - two routes can
    # cross more than once, and every crossing lands in one feature. Inserting
    # that into a point class fails deep in arcpy with a bare `AttributeError:
    # __len__`, so explode to singlepart BEFORE de-duplicating. Exploding first
    # also makes the 50 ft tolerance mean what it says: one point per crossing.
    singles = gdb + "\\_ix_single"
    if arcpy.Exists(singles):
        arcpy.management.Delete(singles)
    arcpy.management.MultipartToSinglepart(kept, singles)
    arcpy.management.Delete(kept)
    kept = singles

    arcpy.management.DeleteIdentical(kept, ["Shape"], "50 Feet")

    dest = gdb + "\\Transportation\\Interchanges"
    read = ["SHAPE@"] + [x for x in (a, b) if x]
    n = 0
    editor = arcpy.da.Editor(gdb)
    editor.startEditing(with_undo=False, multiuser_mode=False)
    editor.startOperation()
    try:
        with arcpy.da.SearchCursor(kept, read) as sc, \
             arcpy.da.InsertCursor(dest, ["SHAPE@", "interchange_id", "route_a",
                                          "route_b", "interchange_type",
                                          "source_id"]) as ic:
            for i, row in enumerate(sc, 1):
                ra = str(row[1])[:50] if len(row) > 1 and row[1] is not None else ""
                rb = str(row[2])[:50] if len(row) > 2 and row[2] is not None else ""
                ic.insertRow((row[0], "IX-%05d" % i, ra, rb,
                              "limited-access crossing", cfg["source_id"]))
                n += 1
        editor.stopOperation()
        editor.stopEditing(save_changes=True)
    except Exception:
        editor.abortOperation()
        editor.stopEditing(save_changes=False)
        raise

    for p in (lines, pts, kept):
        if arcpy.Exists(p):
            arcpy.management.Delete(p)

    write_registry_row(gdb, registry_row(
        {"source_id": cfg["source_id"], "provider": cfg.get("provider", ""),
         "dataset": cfg.get("dataset", ""), "endpoint": cfg["service"],
         "license": cfg.get("license", ""), "native_crs": cfg.get("native_crs")},
        None, notes="derived from %s; %d segments -> %d interchanges; run_id=%s"
                    % (where, n_src, n, run_id)))

    log.info("  derived %d interchange points", n)
    return {"layer": "interchanges", "status": "OK", "target": "Interchanges",
            "segments": n_src, "loaded": n}
