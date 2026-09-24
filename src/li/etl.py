"""Ingest and standardization (scope 6.3 tool 2).

Download a source, reproject it to the analysis CRS, map its fields onto the
schema, load it, and record provenance in `DataSourceRegistry`.

The decision-making half of this module is **pure Python and arcpy-free** so it
can be unit-tested in CI: which fields map to what, whether a county is cleared
to ingest, whether a feature count looks like the layer we meant, how a land
value should be flagged. The arcpy half only executes those decisions.

Design rule that follows from recon: **no guessing.** A county with no verified
field map is refused rather than ingested with a plausible-looking default. The
original shared default was wrong for Tarrant in every single field.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from . import config

try:  # pragma: no cover - arcpy is absent in CI by design
    import arcpy
except ImportError:  # pragma: no cover
    arcpy = None

log = logging.getLogger("li.etl")

# Field-map keys accepted that are not columns on the target feature class.
# Empty: alt_parcel_id and city were promoted to real Parcels fields once the
# Tarrant pilot showed both were worth keeping. The hook stays because county
# schemas differ and the next one may carry something we want to pass through.
EXTRA_MAPPABLE: set[str] = set()


class IngestRefused(Exception):
    """Raised when a source is not cleared for ingest. Never a silent skip."""


# ---------------------------------------------------------------------------
# Pure logic - unit-tested without arcpy
# ---------------------------------------------------------------------------

@dataclass
class FieldMapping:
    """The outcome of matching a county's field map against a live schema."""

    mapping: dict[str, str] = field(default_factory=dict)      # schema -> source
    declared_unavailable: list[str] = field(default_factory=list)
    missing_from_source: list[str] = field(default_factory=list)
    unmapped_source_fields: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """A mapping is usable only if every mapped field exists at the source."""
        return not self.missing_from_source

    def summary(self) -> str:
        return (
            f"{len(self.mapping)} mapped, "
            f"{len(self.declared_unavailable)} declared unavailable, "
            f"{len(self.missing_from_source)} missing"
        )


def resolve_field_mapping(
    county_cfg: dict[str, Any], source_fields: Iterable[str]
) -> FieldMapping:
    """Match a county's declared field map against the fields a source actually has.

    Matching is case-insensitive because appraisal districts are inconsistent
    about it, but the value recorded is always the source's own spelling so the
    provenance is exact.
    """
    available = {str(f): str(f) for f in source_fields}
    lower = {k.lower(): v for k, v in available.items()}

    result = FieldMapping(declared_unavailable=list(county_cfg.get("unavailable", []) or []))
    used: set[str] = set()

    for schema_field, source_field in (county_cfg.get("field_map") or {}).items():
        actual = lower.get(str(source_field).lower())
        if actual is None:
            result.missing_from_source.append(f"{schema_field} -> {source_field}")
        else:
            result.mapping[schema_field] = actual
            used.add(actual)

    result.unmapped_source_fields = sorted(set(available) - used)
    return result


def county_config(source_id: str, county: str, sources_cfg: dict | None = None) -> dict[str, Any]:
    """Look up one county's ingest configuration, or raise."""
    cfg = sources_cfg or config.sources()
    src = next((s for s in cfg["sources"] if s["source_id"] == source_id), None)
    if src is None:
        raise IngestRefused(f"{source_id}: no such source in sources.yaml")
    counties = src.get("counties") or {}
    key = county.strip().lower()
    if key not in counties:
        raise IngestRefused(
            f"{source_id}/{county}: no county entry. Known: {sorted(counties) or 'none'}"
        )
    return counties[key]


def assert_ready_to_ingest(county_cfg: dict[str, Any], county: str,
                           allow_unverified: bool = False) -> None:
    """Refuse a county whose field map has not been verified against the source.

    Recon 1.6: the guessed default map was wrong for Tarrant in every field.
    Ingesting on an unverified map writes nulls that look like real data.
    """
    status = county_cfg.get("status")
    if status != "verified" and not allow_unverified:
        raise IngestRefused(
            f"{county}: field map status is '{status}', not 'verified'. "
            f"Verify it against the live source first, or pass allow_unverified "
            f"to ingest deliberately."
        )
    if not county_cfg.get("endpoint"):
        raise IngestRefused(f"{county}: no endpoint configured.")
    if not county_cfg.get("field_map"):
        raise IngestRefused(f"{county}: no field_map configured.")


def feature_count_ok(actual: int, expected: int | None, tolerance_pct: float = 5.0
                     ) -> tuple[bool, str]:
    """Sanity-check a feature count against what the config expects.

    This is the check that distinguishes TADParcels (758,633) from the
    identically-shaped TCProperty (110). Schema does not identify a layer.
    """
    if not expected:
        return True, f"{actual:,} features (no expected count configured)"
    if expected <= 0:
        return True, f"{actual:,} features"
    delta_pct = abs(actual - expected) / expected * 100
    ok = delta_pct <= tolerance_pct
    verdict = "within" if ok else "OUTSIDE"
    return ok, (f"{actual:,} features vs expected {expected:,} "
                f"({delta_pct:.1f}% {verdict} {tolerance_pct}% tolerance)")


def classify_land_value(value: float | None) -> str:
    """Flag how an appraised land value should be treated downstream (D-008).

    A zero is exempt / right-of-way / government land, not free land. Flagging
    it here is what stops C10 normalizing it to the best possible score.
    """
    if value is None:
        return "Missing"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "Invalid"
    if v < 0:
        return "Invalid"
    if v == 0:
        return "ZeroExempt"
    return "Valued"


def acreage_delta_pct(geometry_acres: float | None,
                      published_acres: float | None) -> float | None:
    """Percent disagreement between geometry-derived and CAD-published acreage."""
    if geometry_acres is None or published_acres in (None, 0):
        return None
    try:
        g, p = float(geometry_acres), float(published_acres)
    except (TypeError, ValueError):
        return None
    if p <= 0:
        return None
    return abs(g - p) / p * 100.0


def paged_query_params(offset: int, page_size: int, out_fields: Sequence[str],
                       where: str = "1=1") -> dict[str, Any]:
    """Query parameters for one page of an ArcGIS REST layer.

    `maxRecordCount` is 1,000 on TADParcels, so paging is mandatory; a single
    unpaged request silently returns the first page and looks successful.
    """
    return {
        "where": where,
        "outFields": ",".join(out_fields) if out_fields else "*",
        "returnGeometry": "true",
        "outSR": 4326,
        "resultOffset": offset,
        "resultRecordCount": page_size,
        "f": "geojson",
    }


def registry_row(source: dict[str, Any], county_cfg: dict[str, Any] | None,
                 download_date: datetime | None = None,
                 notes: str = "") -> dict[str, Any]:
    """Build the DataSourceRegistry row for an ingested source (scope 4.3)."""
    dt = download_date or datetime.now(timezone.utc)
    native = (county_cfg or {}).get("native_crs") or source.get("native_crs")
    return {
        "source_id": source["source_id"],
        "provider": source.get("provider", ""),
        "dataset": source.get("dataset", ""),
        "url": (county_cfg or {}).get("endpoint") or source.get("endpoint") or source.get("portal", ""),
        "vintage": str(source.get("vintage") or (county_cfg or {}).get("verified_on") or ""),
        "download_date": dt.replace(tzinfo=None),
        "license": source.get("license", ""),
        "native_crs": str(native or "unknown"),
        "transformation": (county_cfg or {}).get("transformation") or "",
        "notes": notes[:1000],
    }


# ---------------------------------------------------------------------------
# arcpy-dependent execution
# ---------------------------------------------------------------------------

def _require_arcpy() -> None:
    if arcpy is None:
        raise ImportError("arcpy is required for li.etl execution functions.")


def rest_layer_fields(endpoint: str, session=None) -> list[str]:
    """Field names published by an ArcGIS REST layer."""
    import requests
    s = session or requests.Session()
    meta = s.get(endpoint, params={"f": "json"}, timeout=120).json()
    return [f["name"] for f in meta.get("fields", []) if f["type"] != "esriFieldTypeGeometry"]


def rest_feature_count(endpoint: str, where: str = "1=1", session=None) -> int:
    import requests
    s = session or requests.Session()
    r = s.get(f"{endpoint}/query",
              params={"where": where, "returnCountOnly": "true", "f": "json"}, timeout=120)
    return int(r.json().get("count", 0))


def download_rest_layer(endpoint: str, out_dir: Path, out_name: str,
                        out_fields: Sequence[str], where: str = "1=1",
                        page_size: int = 1000, max_pages: int | None = None,
                        session=None) -> list[Path]:
    """Page an ArcGIS REST layer to GeoJSON files in `out_dir`.

    Raw pages are written unmodified: the raw directory is the faithful record
    of what the provider served, and nothing edits it afterwards.
    """
    import requests
    s = session or requests.Session()
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    offset, page = 0, 0
    t0 = time.time()

    while True:
        params = paged_query_params(offset, page_size, out_fields, where)
        r = s.get(f"{endpoint}/query", params=params, timeout=300)
        r.raise_for_status()
        payload = r.json()
        feats = payload.get("features", [])
        if not feats:
            break
        path = out_dir / f"{out_name}_{page:04d}.geojson"
        path.write_text(json.dumps(payload), encoding="utf-8")
        written.append(path)
        page += 1
        offset += len(feats)
        if page % 25 == 0:
            log.info("    %s: %d features in %.0fs", out_name, offset, time.time() - t0)
        if len(feats) < page_size:
            break
        if max_pages and page >= max_pages:
            log.warning("    %s: stopped at max_pages=%d (%d features)",
                        out_name, max_pages, offset)
            break

    log.info("  downloaded %d features to %d files in %.0fs",
             offset, len(written), time.time() - t0)
    return written


def combine_geojson_pages(paths: Sequence[Path], out_dir: Path,
                          chunk: int = 50) -> list[Path]:
    """Concatenate downloaded pages into a few larger FeatureCollections.

    `JSONToFeatures` carries a second or two of fixed overhead per call, so
    running it 759 times to load one county dominates the entire ingest.
    Concatenating first turns that into ~15 calls. The original pages are left
    untouched on disk - they are the raw record.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    combined: list[Path] = []
    for i in range(0, len(paths), chunk):
        feats: list[dict] = []
        for page in paths[i:i + chunk]:
            feats.extend(json.loads(page.read_text(encoding="utf-8")).get("features", []))
        out = out_dir / f"combined_{i // chunk:03d}.geojson"
        out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}),
                       encoding="utf-8")
        combined.append(out)
    log.info("  combined %d pages into %d files", len(paths), len(combined))
    return combined


def geojson_to_feature_class(paths: Sequence[Path], out_gdb: str, out_name: str,
                             target_crs: int, interim_dir: Path | None = None,
                             chunk: int = 50, geometry_type: str = "POLYGON") -> str:
    """Convert downloaded GeoJSON pages into one projected feature class.

    `geometry_type` must match the source: JSONToFeatures writes an empty class
    of the requested type rather than failing when they disagree, so a wrong
    value here produces a silently empty result.
    """
    _require_arcpy()
    if interim_dir is not None and len(paths) > chunk:
        paths = combine_geojson_pages(paths, interim_dir / out_name, chunk)

    scratch = f"{out_gdb}\\_pages_{out_name}"
    parts: list[str] = []
    for i, p in enumerate(paths):
        tmp = f"{scratch}_{i:04d}"
        if arcpy.Exists(tmp):
            arcpy.management.Delete(tmp)
        arcpy.conversion.JSONToFeatures(str(p), tmp, geometry_type)
        parts.append(tmp)
        if (i + 1) % 5 == 0:
            log.info("    converted %d/%d", i + 1, len(paths))

    merged = f"{out_gdb}\\_merged_{out_name}"
    if arcpy.Exists(merged):
        arcpy.management.Delete(merged)
    arcpy.management.Merge(parts, merged)

    out = f"{out_gdb}\\{out_name}"
    if arcpy.Exists(out):
        arcpy.management.Delete(out)
    arcpy.management.Project(merged, out, arcpy.SpatialReference(int(target_crs)))

    for p in parts + [merged]:
        if arcpy.Exists(p):
            arcpy.management.Delete(p)
    return out


def write_registry_row(gdb: str, row: dict[str, Any]) -> None:
    """Append one provenance row to DataSourceRegistry."""
    _require_arcpy()
    tbl = f"{gdb}\\DataSourceRegistry"
    if not arcpy.Exists(tbl):
        log.warning("DataSourceRegistry not found; provenance not recorded")
        return
    fields = list(row)
    with arcpy.da.InsertCursor(tbl, fields) as cur:
        cur.insertRow(tuple(row[f] for f in fields))
    log.info("  DataSourceRegistry += %s", row.get("source_id"))


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def ingest_county_parcels(
    county: str,
    run_id: str,
    source_id: str = "S01",
    gdb: str | None = None,
    raw_root: str | Path | None = None,
    max_pages: int | None = None,
    allow_unverified: bool = False,
    reuse_download: bool = True,
) -> dict[str, Any]:
    """Download, standardize, and load one county's parcels.

    Returns a summary dict. Raises IngestRefused rather than proceeding on an
    unverified field map - a wrong map writes nulls that look like real data.
    """
    _require_arcpy()
    import requests

    paths = config.paths()
    gdb = gdb or paths["gdb"]
    raw_root = Path(raw_root or paths["raw_dir"])
    sources = config.sources()
    source = next(s for s in sources["sources"] if s["source_id"] == source_id)
    ccfg = county_config(source_id, county, sources)
    assert_ready_to_ingest(ccfg, county, allow_unverified)

    endpoint = ccfg["endpoint"]
    session = requests.Session()
    session.headers.update({"User-Agent": "dsg-dfw-site-selection ingest"})

    log.info("=" * 70)
    log.info("IngestAndStandardize  %s / %s", source_id, county)
    log.info("endpoint: %s", endpoint)

    # 1 - confirm the layer is the one we meant
    available = rest_layer_fields(endpoint, session)
    total = rest_feature_count(endpoint, session=session)
    ok, msg = feature_count_ok(total, ccfg.get("expected_feature_count"),
                              ccfg.get("feature_count_tolerance_pct", 5.0))
    log.info("feature count: %s", msg)
    if not ok and not allow_unverified:
        raise IngestRefused(
            f"{county}: {msg}. This is how a lookalike layer gets ingested - "
            f"confirm the endpoint before proceeding."
        )

    # 2 - map fields against what the source actually publishes
    fm = resolve_field_mapping(ccfg, available)
    log.info("field mapping: %s", fm.summary())
    for miss in fm.missing_from_source:
        log.error("  MISSING AT SOURCE: %s", miss)
    if not fm.ok:
        raise IngestRefused(f"{county}: field map does not match the live source.")
    for f in fm.declared_unavailable:
        log.info("  declared unavailable (expected null): %s", f)

    # 3 - download raw, unmodified
    raw_dir = raw_root / county.lower()
    existing = sorted(raw_dir.glob(f"{county.lower()}_parcels_*.geojson"))
    if reuse_download and existing:
        log.info("reusing %d existing raw pages in %s", len(existing), raw_dir)
        pages = existing
    else:
        pages = download_rest_layer(
            endpoint, raw_dir, f"{county.lower()}_parcels",
            out_fields=sorted(set(fm.mapping.values())),
            page_size=int(ccfg.get("max_record_count", 1000)),
            max_pages=max_pages, session=session)
    if not pages:
        raise IngestRefused(f"{county}: download produced no features.")

    # 4 - convert and reproject to the analysis CRS
    target_crs = int(config.schema()["meta"]["crs"])
    staged = geojson_to_feature_class(
        pages, gdb, f"_stage_{county.lower()}_parcels", target_crs,
        interim_dir=Path(paths["interim_dir"]))
    staged_count = int(arcpy.management.GetCount(staged)[0])
    log.info("staged %s features in EPSG:%s", f"{staged_count:,}", target_crs)

    # 5 - append into Parcels through the field map
    loaded = append_to_parcels(staged, gdb, fm, source_id, county)

    # 6 - provenance
    write_registry_row(gdb, registry_row(
        source, ccfg, notes=(
            f"county={county}; {msg}; {fm.summary()}; "
            f"unavailable={','.join(fm.declared_unavailable) or 'none'}; run_id={run_id}")))

    arcpy.management.Delete(staged)

    summary = {
        "county": county,
        "source_id": source_id,
        "available_at_source": total,
        "downloaded": staged_count,
        "loaded": loaded,
        "mapped_fields": len(fm.mapping),
        "declared_unavailable": fm.declared_unavailable,
        "raw_dir": str(raw_dir),
        "run_id": run_id,
    }
    log.info("=" * 70)
    for k, v in summary.items():
        log.info("%-22s %s", k, v)
    return summary


def append_to_parcels(staged: str, gdb: str, fm: FieldMapping,
                      source_id: str, county: str) -> int:
    """Insert staged features into Parcels, applying the field map.

    Written with cursors rather than arcpy Append so that the derived fields -
    land_val_flag and zoning_confidence - are set explicitly and visibly at the
    moment of load, rather than being left to a later pass that might not run.
    """
    _require_arcpy()
    target = f"{gdb}\Cadastral\Parcels"
    schema_fields = [f for f in fm.mapping if f not in EXTRA_MAPPABLE]
    src_fields = [fm.mapping[f] for f in schema_fields]

    out_fields = ["SHAPE@", *schema_fields, "county", "source_id",
                  "land_val_flag", "zoning_confidence", "zoning_conf_st"]
    present = {f.name for f in arcpy.ListFields(target)}
    out_fields = [f for f in out_fields if f == "SHAPE@" or f in present]

    lv_i = schema_fields.index("appraised_land_val") if "appraised_land_val" in schema_fields else None
    n = 0
    # Parcels carries attribute rules (calc_Parcel_Acres and friends), and a
    # class with rules cannot be written outside an edit session - inserting
    # directly raises "Objects in this class cannot be updated outside an edit
    # session". The session is also what lets the rules fire on insert, which
    # is how acres, land_val_per_acre and acres_delta_pct get populated at all.
    editor = arcpy.da.Editor(gdb)
    editor.startEditing(with_undo=False, multiuser_mode=False)
    editor.startOperation()
    try:
        with arcpy.da.SearchCursor(staged, ["SHAPE@", *src_fields]) as sc, \
             arcpy.da.InsertCursor(target, out_fields) as ic:
            for row in sc:
                values = {f: row[i + 1] for i, f in enumerate(schema_fields)}
                land_val = row[lv_i + 1] if lv_i is not None else None
                extras = {
                    "county": county.title(),
                    "source_id": source_id,
                    "land_val_flag": classify_land_value(land_val),
                    # Zoning is joined in a later step; until then the honest
                    # value is Unknown, which is also the default subtype
                    # (D-013 Q2).
                    "zoning_confidence": "Unknown",
                    "zoning_conf_st": 4,
                }
                out = []
                for f in out_fields:
                    if f == "SHAPE@":
                        out.append(row[0])
                    elif f in values:
                        out.append(values[f])
                    else:
                        out.append(extras.get(f))
                ic.insertRow(tuple(out))
                n += 1
                if n % 50000 == 0:
                    log.info("    appended %s rows", f"{n:,}")
        editor.stopOperation()
        editor.stopEditing(save_changes=True)
    except Exception:
        editor.abortOperation()
        editor.stopEditing(save_changes=False)
        raise
    log.info("appended %s rows into Parcels", f"{n:,}")
    return n
