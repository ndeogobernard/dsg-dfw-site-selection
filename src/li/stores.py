"""DICK'S store set from OpenStreetMap (scope §2.2, S21).

Scope §2.2 wants every DICK'S Sporting Goods, Golf Galaxy, Public Lands and
DICK'S House of Sport location within 600 miles of the MSA centroid, and then
a *served set* of those within a 10-hour truck drive.

S21 names two possible sources: the dicks.com store locator and OpenStreetMap.
OSM is used here. The locator is a commercial site with terms that do not
contemplate scraping, and the sixteen state extracts are already downloaded for
the road network, so this costs nothing extra and stays reproducible from a
clean clone.

The cost of that choice is coverage: OSM's record of a retail chain is
volunteer-contributed and incomplete. The count this produces is a floor, not a
census, and `ingest_stores` reports it as such rather than implying otherwise.
"""

from __future__ import annotations

import logging
import math
import re
import time
from pathlib import Path
from typing import Iterable

from . import config

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

# Banner -> the patterns that identify it. Order matters: House of Sport is a
# DICK'S banner whose name contains "DICK'S", so it has to be tested first or
# every one of them would be filed under the parent brand.
BANNER_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("DICK'S House of Sport", (r"house\s*of\s*sport",)),
    ("Golf Galaxy", (r"golf\s*galaxy",)),
    ("Public Lands", (r"public\s*lands",)),
    ("DICK'S Sporting Goods", (r"dick'?s\s*sporting", r"dick'?s\b")),
]


def normalise(text: str | None) -> str:
    """Lower-case, and fold the apostrophes OSM spells four different ways.

    "DICK'S", "DICK’S", "Dicks" and "DICK`S" all occur in the data. A
    matcher that only knows the straight quote silently misses whole states.
    """
    if not text:
        return ""
    t = str(text)
    for ch in ("’", "‘", "ʼ", "`", "'"):
        t = t.replace(ch, "'")
    return re.sub(r"\s+", " ", t).strip().lower()


def match_banner(*values: str | None) -> str | None:
    """Return the DICK'S banner these OSM tag values identify, or None.

    Checks `name`, `brand` and `operator` together because OSM tags chains
    inconsistently - some nodes carry only `brand`, some only `name`.
    """
    blob = " ".join(normalise(v) for v in values if v)
    if not blob:
        return None
    for banner, patterns in BANNER_PATTERNS:
        for pat in patterns:
            if re.search(pat, blob):
                return banner
    return None


def store_id(osm_id, banner: str) -> str:
    """Stable id, so a re-run does not renumber the store set."""
    short = {"DICK'S Sporting Goods": "DSG", "Golf Galaxy": "GG",
             "Public Lands": "PL", "DICK'S House of Sport": "HOS"}.get(banner, "STR")
    return "%s-%s" % (short, osm_id)


def haversine_miles(lon1, lat1, lon2, lat2) -> float:
    """Great-circle miles. Used only to apply the scope's 600-mile radius."""
    r = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def within_radius(lon, lat, centre, miles) -> bool:
    return haversine_miles(lon, lat, centre[0], centre[1]) <= miles


def osm_where() -> str:
    """A deliberately loose SQL pre-filter; `match_banner` does the real work.

    OGR SQL's LIKE cannot express the apostrophe and spacing variants, so this
    only narrows millions of points to a few thousand candidates and Python
    decides. Filtering tightly here would push the matching rules into a SQL
    string where they cannot be tested.
    """
    like = []
    for col in ("name", "brand", "operator"):
        for frag in ("%ick%", "%olf Galax%", "%ublic Land%", "%ouse of Sport%"):
            like.append("%s LIKE '%s'" % (col, frag))
    return " OR ".join(like)


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

def _fld(feat, name: str) -> str:
    """Read a field that may not exist on this layer.

    GDAL's osmconf promotes a tag to a column only if it can be a valid column
    name, and the `addr:*` tags do not always survive that. A missing column
    raises rather than returning empty, so every optional tag is read through
    here - an absent address is not a reason to lose the store.
    """
    try:
        return feat.GetFieldAsString(name) or ""
    except Exception:
        return ""


def scan_extracts(slugs=None, cfg=None, centre=None, radius_miles=None):
    """Find candidate store features across the OSM extracts.

    Reads both `points` and `multipolygons`: OSM maps a big-box store as a node
    in some places and as a building outline in others, and taking only one
    layer loses roughly half of them.
    """
    from osgeo import gdal, ogr

    cfg = cfg or config.sources()["road_network"]
    src = config.sources()
    centre = centre or tuple(src["study_area"]["msa_centroid_wgs84"])
    radius_miles = radius_miles or float(src["study_area"]["store_search_radius_miles"])
    raw = Path(config.paths()["raw_dir"]) / "osm"
    conf = Path(cfg.get("osmconf", "config/osmconf.ini")).resolve()

    gdal.UseExceptions()
    gdal.SetConfigOption("OSM_CONFIG_FILE", str(conf))
    gdal.SetConfigOption("OGR_INTERLEAVED_READING", "YES")

    where = osm_where()
    found, seen = [], set()
    t0 = time.time()

    for slug in (slugs or [s["slug"] for s in cfg["states"]]):
        pbf = raw / ("%s-latest.osm.pbf" % slug)
        if not pbf.exists():
            log.warning("  %s: extract missing, skipped", slug)
            continue
        n_state = 0
        for layer_name in ("points", "multipolygons"):
            tmp = Path(config.paths()["interim_dir"]) / "osm" / (
                "_stores_%s_%s.gpkg" % (slug, layer_name))
            tmp.parent.mkdir(parents=True, exist_ok=True)
            if tmp.exists():
                tmp.unlink()
            try:
                gdal.VectorTranslate(str(tmp), str(pbf), options=gdal.VectorTranslateOptions(
                    format="GPKG", layers=[layer_name], layerName="s", where=where))
            except Exception as exc:
                log.warning("  %s/%s: %s", slug, layer_name, type(exc).__name__)
                continue
            ds = ogr.Open(str(tmp))
            lyr = ds.GetLayerByName("s") if ds else None
            if lyr is not None:
                for feat in lyr:
                    banner = match_banner(_fld(feat, "name"),
                                          _fld(feat, "brand"),
                                          _fld(feat, "operator"))
                    if not banner:
                        continue
                    g = feat.GetGeometryRef()
                    if g is None:
                        continue
                    c = g.Centroid()
                    lon, lat = c.GetX(), c.GetY()
                    if not within_radius(lon, lat, centre, radius_miles):
                        continue
                    oid = _fld(feat, "osm_id") or feat.GetFID()
                    sid = store_id(oid, banner)
                    if sid in seen:
                        continue
                    seen.add(sid)
                    found.append({
                        "store_id": sid, "banner": banner,
                        "name": (_fld(feat, "name") or banner)[:150],
                        "address": " ".join(x for x in (
                            _fld(feat, "addr:housenumber"),
                            _fld(feat, "addr:street")) if x)[:200],
                        "city": _fld(feat, "addr:city")[:100],
                        "state": _fld(feat, "addr:state")[:2],
                        "zip": _fld(feat, "addr:postcode")[:10],
                        "lon": lon, "lat": lat,
                        "source": "OpenStreetMap %s/%s" % (slug, layer_name),
                        "osm_layer": layer_name, "state_slug": slug,
                    })
                    n_state += 1
            ds = None
            tmp.unlink(missing_ok=True)
        if n_state:
            log.info("  %-14s %3d stores", slug, n_state)

    log.info("  %d stores within %.0f miles, %.0fs", len(found), radius_miles,
             time.time() - t0)
    return found


def ingest_stores(gdb=None, run_id="", slugs=None, truncate=True):
    """Write the matched stores into Market/Stores_DSG."""
    import arcpy

    gdb = gdb or config.paths()["gdb"]
    dest = gdb + "\\Market\\Stores_DSG"
    target_crs = int(config.schema()["meta"]["crs"])
    sr_in = arcpy.SpatialReference(4326)
    sr_out = arcpy.SpatialReference(target_crs)

    rows = scan_extracts(slugs=slugs)
    if not rows:
        raise RuntimeError("no stores matched - the pre-filter or the matcher "
                           "is wrong; refusing to write an empty store set")

    arcpy.env.overwriteOutput = True
    if truncate and int(arcpy.management.GetCount(dest)[0]):
        arcpy.management.TruncateTable(dest)

    fields = ["SHAPE@", "store_id", "banner", "name", "address", "city",
              "state", "zip", "lat", "lon", "source", "served_flag", "source_id"]
    editor = arcpy.da.Editor(gdb)
    editor.startEditing(False, False)
    editor.startOperation()
    try:
        with arcpy.da.InsertCursor(dest, fields) as cur:
            for r in rows:
                pt = arcpy.PointGeometry(arcpy.Point(r["lon"], r["lat"]),
                                         sr_in).projectAs(sr_out)
                cur.insertRow([pt, r["store_id"], r["banner"], r["name"],
                               r["address"], r["city"], r["state"], r["zip"],
                               r["lat"], r["lon"], r["source"], 0, "S21"])
        editor.stopOperation()
        editor.stopEditing(True)
    except Exception:
        editor.abortOperation()
        editor.stopEditing(False)
        raise

    by_banner = {}
    for r in rows:
        by_banner[r["banner"]] = by_banner.get(r["banner"], 0) + 1
    log.info("  Stores_DSG: %d loaded", len(rows))
    for b, n in sorted(by_banner.items(), key=lambda x: -x[1]):
        log.info("    %-26s %3d", b, n)
    return {"target": "Stores_DSG", "loaded": len(rows), "by_banner": by_banner,
            "rows": rows}
