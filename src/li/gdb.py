"""Geodatabase construction from config/schema.yaml (scope Section 4).

Builds, in dependency order: file geodatabase, domains, feature datasets,
feature classes, standalone tables, subtypes, relationship classes, topology,
and attribute rules. Also seeds the two configuration-driven reference tables
(CriteriaDefinitions, WeightScenarios) so the delivered GDB is self-describing.

Requires arcpy. Imported lazily so the rest of the package stays CI-testable.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from . import config

try:  # pragma: no cover - arcpy is not installed in CI
    import arcpy
except ImportError:  # pragma: no cover
    arcpy = None

log = logging.getLogger("li.gdb")

# Feature-class geometry keywords accepted by CreateFeatureclass
_GEOM = {"POINT", "MULTIPOINT", "POLYLINE", "POLYGON"}


def _require_arcpy() -> None:
    if arcpy is None:
        raise ImportError(
            "arcpy is required for li.gdb. Run this from the ArcGIS Pro Python "
            "environment (arcgispro-py3 or a clone of it)."
        )


# ---------------------------------------------------------------------------
# Field helpers
# ---------------------------------------------------------------------------

def expand_generated_fields(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand a `generated_fields` block into explicit field definitions.

    Used for the 22 criterion columns on SiteScores (c01_raw..c11_raw,
    c01_s..c11_s) so the schema file stays readable and the criterion count
    lives in exactly one place.
    """
    out: list[dict[str, Any]] = []
    for gen in spec.get("generated_fields", []) or []:
        count = int(gen["count"])
        for i in range(1, count + 1):
            field = {
                "name": gen["pattern"].format(i=i),
                "type": gen.get("type", "DOUBLE"),
            }
            if "alias" in gen:
                field["alias"] = gen["alias"].format(i=i)
            if "domain" in gen:
                field["domain"] = gen["domain"]
            if "length" in gen:
                field["length"] = gen["length"]
            out.append(field)
    return out


def all_fields(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Explicit fields followed by generated fields."""
    return list(spec.get("fields", []) or []) + expand_generated_fields(spec)


def _add_field(table: str, field: dict[str, Any]) -> None:
    ftype = field["type"].upper()
    arcpy.management.AddField(
        in_table=table,
        field_name=field["name"],
        field_type=ftype,
        field_length=field.get("length") if ftype == "TEXT" else None,
        field_alias=field.get("alias"),
        field_is_nullable="NULLABLE" if field.get("nullable", True) else "NON_NULLABLE",
        field_domain=field.get("domain"),
    )
    if field.get("default") is not None:
        arcpy.management.AssignDefaultToField(
            in_table=table,
            field_name=field["name"],
            default_value=str(field["default"]),
        )


def _add_fields(table: str, spec: dict[str, Any]) -> int:
    fields = all_fields(spec)
    for field in fields:
        _add_field(table, field)
    return len(fields)


# ---------------------------------------------------------------------------
# Build steps
# ---------------------------------------------------------------------------

def create_gdb(gdb_path: str | Path, overwrite: bool = False) -> str:
    """Create the file geodatabase, optionally replacing an existing one."""
    _require_arcpy()
    gdb_path = Path(gdb_path)
    if arcpy.Exists(str(gdb_path)):
        if not overwrite:
            raise RuntimeError(
                f"{gdb_path} already exists. Re-run with overwrite=True to replace it."
            )
        log.warning("Deleting existing geodatabase %s", gdb_path)
        arcpy.management.Delete(str(gdb_path))

    gdb_path.parent.mkdir(parents=True, exist_ok=True)
    log.info("Creating file geodatabase %s", gdb_path)
    arcpy.management.CreateFileGDB(str(gdb_path.parent), gdb_path.name)
    return str(gdb_path)


def create_domains(gdb: str, domains: dict[str, Any]) -> int:
    """Create coded-value and range domains (scope 4.4)."""
    existing = {d.name for d in arcpy.da.ListDomains(gdb)}
    made = 0
    for name, spec in (domains or {}).items():
        if name in existing:
            log.info("  domain %s already exists, skipping", name)
            continue
        dtype = spec.get("type", "coded").lower()
        arcpy.management.CreateDomain(
            in_workspace=gdb,
            domain_name=name,
            domain_description=spec.get("description", name),
            field_type=spec.get("field_type", "TEXT").upper(),
            domain_type="CODED" if dtype == "coded" else "RANGE",
        )
        if dtype == "coded":
            for code, desc in (spec.get("values") or {}).items():
                arcpy.management.AddCodedValueToDomain(gdb, name, str(code), str(desc))
        else:
            arcpy.management.SetValueForRangeDomain(
                gdb, name, spec["min"], spec["max"]
            )
        made += 1
        log.info("  domain %s (%s)", name, dtype)
    return made


def create_feature_datasets(gdb: str, datasets: dict[str, str], sr: Any) -> int:
    made = 0
    for name in (datasets or {}):
        path = f"{gdb}\\{name}"
        if arcpy.Exists(path):
            log.info("  feature dataset %s already exists, skipping", name)
            continue
        arcpy.management.CreateFeatureDataset(gdb, name, sr)
        made += 1
        log.info("  feature dataset %s", name)
    return made


def _apply_subtypes(table: str, spec: dict[str, Any]) -> None:
    """Set the subtype field, add subtypes, and assign per-subtype defaults."""
    field = spec.get("subtype_field")
    subtypes = spec.get("subtypes") or {}
    if not field or not subtypes:
        return

    arcpy.management.SetSubtypeField(table, field)
    for label, sub in subtypes.items():
        code = int(sub["code"])
        arcpy.management.AddSubtype(table, code, label)
        for fld, value in (sub.get("defaults") or {}).items():
            arcpy.management.AssignDefaultToField(
                in_table=table,
                field_name=fld,
                default_value=str(value),
                subtype_code=[str(code)],
            )
    if spec.get("default_subtype") is not None:
        arcpy.management.SetDefaultSubtype(table, int(spec["default_subtype"]))
    log.info("    subtypes on %s: %d", field, len(subtypes))


def create_feature_classes(
    gdb: str, feature_classes: dict[str, Any], sr: Any
) -> dict[str, str]:
    """Create every feature class and return a name -> full path index."""
    index: dict[str, str] = {}
    for name, spec in (feature_classes or {}).items():
        geom = spec["geometry"].upper()
        if geom not in _GEOM:
            raise ValueError(f"{name}: unsupported geometry '{geom}'")

        dataset = spec.get("dataset")
        out_path = f"{gdb}\\{dataset}" if dataset else gdb
        fc_path = f"{out_path}\\{name}"
        index[name] = fc_path

        if arcpy.Exists(fc_path):
            log.info("  feature class %s already exists, skipping", name)
            continue

        arcpy.management.CreateFeatureclass(
            out_path=out_path,
            out_name=name,
            geometry_type=geom,
            spatial_reference=sr,
            out_alias=spec.get("alias"),
        )
        n = _add_fields(fc_path, spec)
        log.info("  feature class %-24s %-9s %2d fields", name, geom, n)
        _apply_subtypes(fc_path, spec)
    return index


def create_tables(gdb: str, tables: dict[str, Any]) -> dict[str, str]:
    """Create standalone tables at the GDB root (they cannot live in datasets)."""
    index: dict[str, str] = {}
    for name, spec in (tables or {}).items():
        tbl_path = f"{gdb}\\{name}"
        index[name] = tbl_path
        if arcpy.Exists(tbl_path):
            log.info("  table %s already exists, skipping", name)
            continue
        arcpy.management.CreateTable(gdb, name, out_alias=spec.get("alias"))
        n = _add_fields(tbl_path, spec)
        log.info("  table         %-24s %2d fields", name, n)
        _apply_subtypes(tbl_path, spec)
    return index


def add_global_ids(index: dict[str, str], batch: int = 25) -> int:
    """Add GlobalID fields to every feature class and table.

    Required by attribute rules (ERROR 002710 without them) and by AGOL sync /
    offline use for the hosted layers in scope 7.4, so it is applied uniformly
    rather than only to the classes that carry rules.
    """
    targets = sorted(index.values())
    done = 0
    for i in range(0, len(targets), batch):
        chunk = targets[i : i + batch]
        arcpy.management.AddGlobalIDs(chunk)
        done += len(chunk)
    log.info("  GlobalIDs added to %d datasets", done)
    return done


def create_relationships(
    gdb: str, relationships: Iterable[dict[str, Any]], index: dict[str, str]
) -> int:
    """Create simple relationship classes at the GDB root (scope 4.5)."""
    made = 0
    for rel in relationships or []:
        name = rel["name"]
        rel_path = f"{gdb}\\{name}"
        if arcpy.Exists(rel_path):
            log.info("  relationship %s already exists, skipping", name)
            continue

        origin = index.get(rel["origin"])
        dest = index.get(rel["destination"])
        if not origin or not dest:
            log.warning(
                "  relationship %s skipped - missing %s",
                name,
                rel["origin"] if not origin else rel["destination"],
            )
            continue

        arcpy.management.CreateRelationshipClass(
            origin_table=origin,
            destination_table=dest,
            out_relationship_class=rel_path,
            relationship_type="SIMPLE",
            forward_label=rel.get("forward_label", "to destination"),
            backward_label=rel.get("backward_label", "to origin"),
            message_direction="NONE",
            cardinality=rel.get("cardinality", "ONE_TO_MANY"),
            attributed="NONE",
            origin_primary_key=rel["primary_key"],
            origin_foreign_key=rel["foreign_key"],
        )
        made += 1
        log.info("  relationship  %-24s %s -> %s", name, rel["origin"], rel["destination"])
    return made


def create_topologies(
    gdb: str, topologies: Iterable[dict[str, Any]], index: dict[str, str]
) -> int:
    """Create topology, add participating classes, and add rules (scope 4.5)."""
    made = 0
    for topo in topologies or []:
        name = topo["name"]
        ds_path = f"{gdb}\\{topo['dataset']}"
        topo_path = f"{ds_path}\\{name}"
        if arcpy.Exists(topo_path):
            log.info("  topology %s already exists, skipping", name)
            continue

        arcpy.management.CreateTopology(
            ds_path, name, float(topo.get("cluster_tolerance", 0.1))
        )
        for fc_name in topo.get("feature_classes", []):
            fc_path = index.get(fc_name)
            if fc_path:
                arcpy.management.AddFeatureClassToTopology(topo_path, fc_path, 1, 1)

        for rule in topo.get("rules", []):
            origin = index.get(rule["origin"])
            if not origin:
                continue
            arcpy.management.AddRuleToTopology(
                in_topology=topo_path,
                rule_type=rule["rule"],
                in_featureclass=origin,
            )
        made += 1
        log.info(
            "  topology      %-24s %d classes, %d rules",
            name,
            len(topo.get("feature_classes", [])),
            len(topo.get("rules", [])),
        )
    return made


def create_attribute_rules(
    gdb: str, rules: Iterable[dict[str, Any]], index: dict[str, str]
) -> int:
    """Add calculation and constraint attribute rules (scope 4.5)."""
    made = 0
    for rule in rules or []:
        table = index.get(rule["table"])
        if not table:
            log.warning("  attribute rule %s skipped - %s missing", rule["name"], rule["table"])
            continue

        rtype = rule.get("type", "CALCULATION").upper()
        triggers = ";".join(rule.get("triggers", ["INSERT", "UPDATE"]))
        try:
            arcpy.management.AddAttributeRule(
                in_table=table,
                name=rule["name"],
                type=rtype,
                script_expression=rule["script"],
                is_editable="EDITABLE",
                triggering_events=triggers,
                error_number=rule.get("error_number"),
                error_message=rule.get("error_message"),
                description=rule.get("description"),
                field=rule.get("field"),
                exclude_from_client_evaluation=(
                    "EXCLUDE" if rule.get("exclude_from_client_evaluation") else "INCLUDE"
                ),
            )
            made += 1
            log.info("  attr rule     %-24s %s on %s", rule["name"], rtype, rule["table"])
        except arcpy.ExecuteError:
            # An existing rule of the same name raises; treat as idempotent.
            log.warning("  attr rule %s: %s", rule["name"], arcpy.GetMessages(2).strip())
    return made


# ---------------------------------------------------------------------------
# Seeding the configuration-driven reference tables
# ---------------------------------------------------------------------------

def seed_criteria_definitions(gdb: str, criteria_cfg: dict[str, Any]) -> int:
    """Populate CriteriaDefinitions from config/criteria.yaml."""
    tbl = f"{gdb}\\CriteriaDefinitions"
    if not arcpy.Exists(tbl):
        return 0
    norm = criteria_cfg.get("normalization", {})
    norm_label = (
        f"{norm.get('method', 'winsorize_minmax')} "
        f"[{norm.get('winsorize_lower_pct', 5)},{norm.get('winsorize_upper_pct', 95)}] "
        f"-> {norm.get('scale_min', 0)}-{norm.get('scale_max', 100)}"
    )
    fields = ["criterion_id", "name", "description", "unit", "direction", "normalization", "source_id"]
    rows = 0
    with arcpy.da.InsertCursor(tbl, fields) as cur:
        for c in criteria_cfg.get("criteria", []):
            cur.insertRow(
                (
                    c["id"],
                    c["name"],
                    " ".join(str(c.get("description", "")).split())[:1000],
                    c.get("unit"),
                    c.get("direction"),
                    norm_label,
                    ",".join(c.get("sources", [])),
                )
            )
            rows += 1
    log.info("  seeded CriteriaDefinitions: %d rows", rows)
    return rows


def seed_weight_scenarios(gdb: str, weights: dict[str, Any]) -> int:
    """Populate WeightScenarios from config/weights.json."""
    tbl = f"{gdb}\\WeightScenarios"
    if not arcpy.Exists(tbl):
        return 0
    rows = 0
    with arcpy.da.InsertCursor(tbl, ["scenario", "criterion_id", "weight"]) as cur:
        for scenario, criteria_weights in weights.items():
            for criterion_id, weight in criteria_weights.items():
                cur.insertRow((scenario, criterion_id, float(weight)))
                rows += 1
    log.info("  seeded WeightScenarios: %d rows", rows)
    return rows


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def build_schema(
    out_gdb: str | Path | None = None,
    schema_cfg: dict[str, Any] | None = None,
    crs: int | None = None,
    overwrite: bool = False,
    seed_reference_tables: bool = True,
) -> dict[str, Any]:
    """Build the complete geodatabase schema. Returns a summary dict."""
    _require_arcpy()

    schema_cfg = schema_cfg or config.schema()
    meta = schema_cfg.get("meta", {})
    out_gdb = str(out_gdb or config.paths()["gdb"])
    sr = arcpy.SpatialReference(int(crs or meta.get("crs", 6584)))

    log.info("=" * 70)
    log.info("BuildGeodatabaseSchema  schema v%s  scope v%s",
             meta.get("schema_version"), meta.get("scope_version"))
    log.info("Target : %s", out_gdb)
    log.info("CRS    : %s (%s)", sr.name, sr.linearUnitName)
    log.info("=" * 70)

    create_gdb(out_gdb, overwrite=overwrite)

    with arcpy.EnvManager(workspace=out_gdb, overwriteOutput=False,
                          XYTolerance=meta.get("xy_tolerance"),
                          XYResolution=meta.get("xy_resolution")):
        log.info("Domains")
        n_domains = create_domains(out_gdb, schema_cfg.get("domains", {}))

        log.info("Feature datasets")
        n_ds = create_feature_datasets(out_gdb, schema_cfg.get("feature_datasets", {}), sr)

        log.info("Feature classes")
        fc_index = create_feature_classes(out_gdb, schema_cfg.get("feature_classes", {}), sr)

        log.info("Tables")
        tbl_index = create_tables(out_gdb, schema_cfg.get("tables", {}))

        index = {**fc_index, **tbl_index}

        n_gid = 0
        if meta.get("global_ids", True):
            log.info("Global IDs")
            n_gid = add_global_ids(index)

        log.info("Relationship classes")
        n_rel = create_relationships(out_gdb, schema_cfg.get("relationships", []), index)

        log.info("Topology")
        n_topo = create_topologies(out_gdb, schema_cfg.get("topologies", []), index)

        log.info("Attribute rules")
        n_rules = create_attribute_rules(out_gdb, schema_cfg.get("attribute_rules", []), index)

        n_crit = n_wt = 0
        if seed_reference_tables:
            log.info("Seeding reference tables")
            n_crit = seed_criteria_definitions(out_gdb, config.criteria())
            n_wt = seed_weight_scenarios(out_gdb, config.weights())

        arcpy.management.Compact(out_gdb)

    summary = {
        "gdb": out_gdb,
        "crs": f"{sr.factoryCode} {sr.name}",
        "domains": n_domains,
        "feature_datasets": n_ds,
        "feature_classes": len(fc_index),
        "tables": len(tbl_index),
        "global_ids": n_gid,
        "relationships": n_rel,
        "topologies": n_topo,
        "attribute_rules": n_rules,
        "criteria_rows": n_crit,
        "weight_rows": n_wt,
    }
    log.info("=" * 70)
    for key, value in summary.items():
        log.info("%-18s %s", key, value)
    log.info("=" * 70)
    return summary
