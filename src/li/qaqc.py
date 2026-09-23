"""QA/QC checks (scope 6.3 tool 3, thresholds from scope Section 10).

Evaluation logic is **pure and arcpy-free** so the thresholds can be unit-tested
in CI; the arcpy half only gathers the counts and writes `QAQC_Log`.

A check reports `Pass`, `Fail`, `Warning` or `Skipped`. `Skipped` exists because
a check whose input is not loaded yet must be visibly absent rather than
silently counted as passing — a green log that is green because nothing ran is
worse than a red one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable, Sequence

from . import config

try:  # pragma: no cover
    import arcpy
except ImportError:  # pragma: no cover
    arcpy = None

log = logging.getLogger("li.qaqc")

PASS, FAIL, WARN, SKIP = "Pass", "Fail", "Warning", "Skipped"


# ---------------------------------------------------------------------------
# Pure logic
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    check_id: str
    layer: str
    check_name: str
    result: str
    affected_cnt: int = 0
    threshold: float | None = None
    detail: str = ""

    @property
    def passed(self) -> int:
        """SHORT for the QAQC_Log table. A warning is not a pass."""
        return 1 if self.result == PASS else 0

    def as_row(self, run_id: str, when: datetime | None = None) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "run_id": run_id,
            "layer": self.layer,
            "check_name": self.check_name,
            "result": self.result,
            "affected_cnt": int(self.affected_cnt),
            "threshold": self.threshold,
            "passed": self.passed,
            "check_timestamp": when or datetime.now(),
            "detail": self.detail[:1000],
        }


def evaluate(count: int, threshold: float | None, *, mode: str = "max",
             warn_only: bool = False) -> str:
    """Compare an observed count against a threshold.

    mode="max": count must be <= threshold (e.g. zero null geometries).
    mode="min": count must be >= threshold (e.g. at least N features loaded).
    """
    if threshold is None:
        return PASS
    if mode == "min":
        ok = count >= threshold
    else:
        ok = count <= threshold
    if ok:
        return PASS
    return WARN if warn_only else FAIL


def null_rate(values: Iterable[Any]) -> tuple[int, int, float]:
    """(null_or_blank, total, percent). Blank strings count as null."""
    total = nulls = 0
    for v in values:
        total += 1
        if v is None or (isinstance(v, str) and not v.strip()):
            nulls += 1
    return nulls, total, (100.0 * nulls / total if total else 0.0)


def duplicate_keys(values: Iterable[Any]) -> dict[Any, int]:
    """Keys appearing more than once, with their counts. Nulls are ignored."""
    seen: dict[Any, int] = {}
    for v in values:
        if v is None or (isinstance(v, str) and not v.strip()):
            continue
        seen[v] = seen.get(v, 0) + 1
    return {k: n for k, n in seen.items() if n > 1}


def domain_violations(values: Iterable[Any], allowed: Iterable[Any]) -> dict[Any, int]:
    """Values outside a coded domain. Nulls are not violations."""
    allowed_set = {str(a) for a in allowed}
    bad: dict[Any, int] = {}
    for v in values:
        if v is None or (isinstance(v, str) and not v.strip()):
            continue
        if str(v) not in allowed_set:
            bad[v] = bad.get(v, 0) + 1
    return bad


def out_of_range(values: Iterable[float | None], lo: float, hi: float) -> int:
    n = 0
    for v in values:
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            n += 1
            continue
        if fv < lo or fv > hi:
            n += 1
    return n


def acreage_disagreements(pairs: Iterable[tuple[float | None, float | None]],
                          tolerance_pct: float) -> int:
    """Count parcels where geometry and published acreage disagree beyond tolerance.

    Not an error - deed acreage and digitised geometry routinely differ. It is
    reported so the size of the disagreement is known, because D-008 screens on
    the published figure.
    """
    from .etl import acreage_delta_pct
    n = 0
    for geom, pub in pairs:
        d = acreage_delta_pct(geom, pub)
        if d is not None and d > tolerance_pct:
            n += 1
    return n


def crs_matches(actual: int | None, expected: int) -> bool:
    return actual is not None and int(actual) == int(expected)


# ---------------------------------------------------------------------------
# Check definitions (scope Section 10)
# ---------------------------------------------------------------------------

def parcel_check_plan(thresholds: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The §10 checks that apply to an ingested parcel layer."""
    t = thresholds or {}
    return [
        {"id": "ING-CRS", "name": "CRS equals the analysis CRS", "threshold": 0, "mode": "max"},
        {"id": "ING-GEOM-NULL", "name": "Null geometry", "threshold": 0, "mode": "max"},
        {"id": "ING-GEOM-INVALID", "name": "Invalid geometry", "threshold": 0, "mode": "max"},
        {"id": "ING-DUP-KEY", "name": "Duplicate parcel_id", "threshold": 0, "mode": "max"},
        {"id": "ING-KEY-NULL", "name": "Null parcel_id", "threshold": 0, "mode": "max"},
        {"id": "ING-COUNT", "name": "Feature count matches the expected layer",
         "threshold": t.get("min_features", 1), "mode": "min"},
        {"id": "ING-ACRES-NULL", "name": "Null published acreage",
         "threshold": t.get("max_null_acres_pct", 1.0), "mode": "max", "warn_only": True},
        {"id": "ING-VALUE-NULL", "name": "Null appraised land value",
         "threshold": t.get("max_null_value_pct", 1.0), "mode": "max", "warn_only": True},
        {"id": "ING-VALUE-ZERO", "name": "Zero appraised land value (exempt/ROW)",
         "threshold": t.get("max_zero_value_pct", 15.0), "mode": "max", "warn_only": True},
        {"id": "ING-ACRES-DELTA", "name": "Geometry vs published acreage disagreement",
         "threshold": t.get("max_acres_delta_pct", 25.0), "mode": "max", "warn_only": True},
        {"id": "ING-DOMAIN-ZC", "name": "zoning_confidence domain violations",
         "threshold": 0, "mode": "max"},
    ]


# ---------------------------------------------------------------------------
# arcpy-dependent execution
# ---------------------------------------------------------------------------

def _require_arcpy() -> None:
    if arcpy is None:
        raise ImportError("arcpy is required for li.qaqc execution functions.")


def run_parcel_checks(fc: str, gdb: str, expected_crs: int,
                      expected_min_features: int = 1,
                      thresholds: dict[str, Any] | None = None) -> list[CheckResult]:
    """Run the §10 parcel checks against a loaded feature class."""
    _require_arcpy()
    results: list[CheckResult] = []
    layer = fc.split("\\")[-1]
    plan = {c["id"]: c for c in parcel_check_plan(
        {**(thresholds or {}), "min_features": expected_min_features})}

    def add(cid: str, count: int, detail: str, result: str | None = None) -> None:
        spec = plan[cid]
        results.append(CheckResult(
            check_id=cid, layer=layer, check_name=spec["name"],
            result=result or evaluate(count, spec["threshold"], mode=spec.get("mode", "max"),
                                      warn_only=spec.get("warn_only", False)),
            affected_cnt=count, threshold=spec["threshold"], detail=detail))

    desc = arcpy.da.Describe(fc)
    sr = desc.get("spatialReference")
    actual_crs = getattr(sr, "factoryCode", None)
    add("ING-CRS", 0 if crs_matches(actual_crs, expected_crs) else 1,
        f"actual EPSG:{actual_crs}, expected EPSG:{expected_crs}")

    total = int(arcpy.management.GetCount(fc)[0])
    add("ING-COUNT", total, f"{total:,} features loaded")

    names = {f.name for f in arcpy.ListFields(fc)}
    read = [n for n in ("parcel_id", "acres", "acres_published", "appraised_land_val",
                        "zoning_confidence") if n in names]
    rows = list(arcpy.da.SearchCursor(fc, ["SHAPE@", *read]))
    idx = {n: i + 1 for i, n in enumerate(read)}

    null_geom = sum(1 for r in rows if r[0] is None)
    add("ING-GEOM-NULL", null_geom, f"{null_geom} of {total:,}")

    invalid = 0
    for r in rows:
        g = r[0]
        if g is not None and (g.area == 0 or g.partCount == 0):
            invalid += 1
    add("ING-GEOM-INVALID", invalid, f"{invalid} zero-area or empty geometries")

    if "parcel_id" in idx:
        keys = [r[idx["parcel_id"]] for r in rows]
        dups = duplicate_keys(keys)
        add("ING-DUP-KEY", sum(dups.values()) - len(dups) if dups else 0,
            f"{len(dups)} duplicated key values" if dups else "no duplicates")
        nulls, tot, pct = null_rate(keys)
        add("ING-KEY-NULL", nulls, f"{nulls} of {tot:,} ({pct:.2f}%)")

    if "acres_published" in idx:
        vals = [r[idx["acres_published"]] for r in rows]
        _, tot, pct = null_rate(vals)
        add("ING-ACRES-NULL", round(pct, 3), f"{pct:.2f}% null of {tot:,}")

    if "appraised_land_val" in idx:
        from .etl import classify_land_value
        flags = [classify_land_value(r[idx["appraised_land_val"]]) for r in rows]
        n = len(flags) or 1
        miss = 100.0 * flags.count("Missing") / n
        zero = 100.0 * flags.count("ZeroExempt") / n
        add("ING-VALUE-NULL", round(miss, 3), f"{miss:.2f}% missing")
        add("ING-VALUE-ZERO", round(zero, 3),
            f"{zero:.2f}% zero - exempt/ROW, excluded from C10 per D-008")

    if "acres" in idx and "acres_published" in idx:
        pairs = [(r[idx["acres"]], r[idx["acres_published"]]) for r in rows]
        tol = (thresholds or {}).get("acres_delta_tolerance_pct", 5.0)
        n_bad = acreage_disagreements(pairs, tol)
        pct = 100.0 * n_bad / (len(pairs) or 1)
        add("ING-ACRES-DELTA", round(pct, 3),
            f"{n_bad:,} parcels ({pct:.2f}%) disagree by more than {tol}%")

    if "zoning_confidence" in idx:
        allowed = config.schema()["domains"]["dm_ZoningConfidence"]["values"]
        bad = domain_violations([r[idx["zoning_confidence"]] for r in rows], allowed)
        add("ING-DOMAIN-ZC", sum(bad.values()),
            f"{len(bad)} distinct invalid values" if bad else "all values in domain")

    return results


def write_log(gdb: str, run_id: str, results: Sequence[CheckResult]) -> int:
    """Append results to QAQC_Log (scope 4.3)."""
    _require_arcpy()
    tbl = f"{gdb}\\QAQC_Log"
    if not arcpy.Exists(tbl):
        log.warning("QAQC_Log not found; results not persisted")
        return 0
    if not results:
        return 0
    fields = list(results[0].as_row(run_id))
    with arcpy.da.InsertCursor(tbl, fields) as cur:
        for r in results:
            row = r.as_row(run_id)
            cur.insertRow(tuple(row[f] for f in fields))
    return len(results)


def summarize(results: Sequence[CheckResult]) -> dict[str, int]:
    out = {PASS: 0, FAIL: 0, WARN: 0, SKIP: 0}
    for r in results:
        out[r.result] = out.get(r.result, 0) + 1
    return out
