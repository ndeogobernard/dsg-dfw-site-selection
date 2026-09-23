# -*- coding: utf-8 -*-
"""LocationIntelligence - ArcGIS Python toolbox.

Site-selection analysis for a DICK'S Sporting Goods regional distribution
center in the Dallas-Fort Worth MSA. Implements scope Section 6.3.

Tools are thin wrappers: parameter definition, validation, and logging live
here, while all real work lives in the importable `li` package under src/ so
it can be unit-tested and called from run_pipeline.py without ArcGIS.

Implemented
    1  BuildGeodatabaseSchema
    2  IngestAndStandardize
    3  RunQAQC

Planned (scope 6.3)
    4  BuildNetworkDataset         9  ComputeCriteriaScores
    5  ScreenCandidateSites       10  WeightedSuitability
    6  BuildServiceAreas          11  SensitivityRunner
    7  BuildODMatrices            12  ExportSiteProfiles
    8  ComputeWorkforceMetrics    13  PublishToAGOL (optional)
"""

import importlib
import os
import sys
from pathlib import Path

import arcpy

# Make src/ importable regardless of where the toolbox is opened from.
_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import li  # noqa: E402
from li import config, etl as li_etl, gdb as li_gdb, logging_utils, qaqc as li_qaqc  # noqa: E402

# ArcGIS caches toolbox modules between runs; reload so edits take effect
# without restarting Pro.
for _mod in (li, config, li_gdb, li_etl, li_qaqc, logging_utils):
    importlib.reload(_mod)

TOOLBOX_VERSION = li.__version__


class Toolbox(object):
    def __init__(self):
        self.label = "Location Intelligence"
        self.alias = "locationintelligence"
        self.description = (
            "Site-selection toolbox for the DICK'S Sporting Goods DFW "
            "regional distribution center study."
        )
        self.tools = [BuildGeodatabaseSchema, IngestAndStandardize, RunQAQC]


class BuildGeodatabaseSchema(object):
    """Tool 1 - create the analysis geodatabase exactly per config/schema.yaml."""

    def __init__(self):
        self.label = "1 - Build Geodatabase Schema"
        self.description = (
            "Creates DFW_DSG_SiteSelection.gdb with all feature datasets, "
            "feature classes, tables, fields, domains, subtypes, relationship "
            "classes, topology, and attribute rules defined in "
            "config/schema.yaml (scope Section 4). Seeds CriteriaDefinitions "
            "and WeightScenarios from config/criteria.yaml and "
            "config/weights.json so the delivered geodatabase is "
            "self-describing."
        )
        self.category = "1 - Geodatabase"
        self.canRunInBackground = False

    # -- parameters ---------------------------------------------------------
    def getParameterInfo(self):
        schema_yaml = arcpy.Parameter(
            displayName="Schema definition (schema.yaml)",
            name="schema_yaml",
            datatype="DEFile",
            parameterType="Required",
            direction="Input",
        )
        schema_yaml.filter.list = ["yaml", "yml"]
        default_schema = _REPO / "config" / "schema.yaml"
        if default_schema.exists():
            schema_yaml.value = str(default_schema)

        out_gdb = arcpy.Parameter(
            displayName="Output geodatabase",
            name="out_gdb",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Output",
        )
        try:
            out_gdb.value = config.paths()["gdb"]
        except Exception:
            pass

        crs = arcpy.Parameter(
            displayName="Analysis coordinate system",
            name="crs",
            datatype="GPSpatialReference",
            parameterType="Optional",
            direction="Input",
        )

        overwrite = arcpy.Parameter(
            displayName="Overwrite existing geodatabase",
            name="overwrite",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        overwrite.value = False

        seed = arcpy.Parameter(
            displayName="Seed CriteriaDefinitions and WeightScenarios from config",
            name="seed_reference_tables",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        seed.value = True

        return [schema_yaml, out_gdb, crs, overwrite, seed]

    def isLicensed(self):
        return True

    # -- validation ---------------------------------------------------------
    def updateParameters(self, parameters):
        """Default the CRS to the value declared in the schema file."""
        schema_param, _, crs_param = parameters[0], parameters[1], parameters[2]
        if schema_param.altered and not crs_param.altered and schema_param.valueAsText:
            try:
                cfg = config.load_yaml(schema_param.valueAsText)
                code = cfg.get("meta", {}).get("crs")
                if code:
                    crs_param.value = arcpy.SpatialReference(int(code))
            except Exception:
                pass
        return

    def updateMessages(self, parameters):
        schema_param, gdb_param, _, overwrite_param, _seed = parameters

        if schema_param.valueAsText and not Path(schema_param.valueAsText).exists():
            schema_param.setErrorMessage("Schema file not found.")

        if gdb_param.valueAsText:
            target = gdb_param.valueAsText
            if not target.lower().endswith(".gdb"):
                gdb_param.setErrorMessage("Output must be a file geodatabase (.gdb).")
            elif arcpy.Exists(target) and not overwrite_param.value:
                gdb_param.setWarningMessage(
                    "This geodatabase already exists. Existing datasets will be "
                    "kept and only missing ones created. Tick 'Overwrite' to "
                    "rebuild it from scratch - that deletes all data in it."
                )
        return

    # -- execute ------------------------------------------------------------
    def execute(self, parameters, messages):
        schema_yaml = parameters[0].valueAsText
        out_gdb = parameters[1].valueAsText
        crs_param = parameters[2].value
        overwrite = bool(parameters[3].value)
        seed = bool(parameters[4].value)

        run_id = logging_utils.make_run_id("schema")
        log_dir = Path(config.paths()["logs_dir"])
        logging_utils.get_logger("li", log_dir=log_dir, run_id=run_id)

        crs_code = None
        if crs_param is not None:
            crs_code = getattr(crs_param, "factoryCode", None) or None

        arcpy.AddMessage(f"run_id           {run_id}")
        arcpy.AddMessage(f"toolbox version  {TOOLBOX_VERSION}")
        arcpy.AddMessage(f"git commit       {logging_utils.git_commit(_REPO)[:10]}")
        arcpy.AddMessage(f"log              {log_dir / (run_id + '.log')}")

        try:
            config.validate_weights()
            arcpy.AddMessage("weights.json validated: all scenarios sum to 1.00")
        except Exception as exc:
            arcpy.AddError(str(exc))
            raise arcpy.ExecuteError(str(exc))

        summary = li_gdb.build_schema(
            out_gdb=out_gdb,
            schema_cfg=config.load_yaml(schema_yaml),
            crs=crs_code,
            overwrite=overwrite,
            seed_reference_tables=seed,
        )

        arcpy.AddMessage("-" * 58)
        for key, value in summary.items():
            arcpy.AddMessage(f"{key:<18} {value}")
        arcpy.AddMessage("-" * 58)
        return

    def postExecute(self, parameters):
        return


class IngestAndStandardize(object):
    """Tool 2 - download a source, reproject it, map its fields, and load it."""

    def __init__(self):
        self.label = "2 - Ingest and Standardize"
        self.description = (
            "Downloads a configured source, reprojects it to the analysis CRS, "
            "maps its fields onto the schema, loads it, and records provenance "
            "in DataSourceRegistry. Driven entirely by config/sources.yaml. A "
            "county whose field map has not been verified against the live "
            "source is refused rather than ingested on a guess - the original "
            "shared default map was wrong for Tarrant in every field."
        )
        self.category = "2 - Data"
        self.canRunInBackground = False

    def getParameterInfo(self):
        source_id = arcpy.Parameter(
            displayName="Source ID", name="source_id", datatype="GPString",
            parameterType="Required", direction="Input")
        source_id.filter.type = "ValueList"
        try:
            source_id.filter.list = [s["source_id"] for s in config.sources()["sources"]]
        except Exception:
            source_id.filter.list = ["S01"]
        source_id.value = "S01"

        county = arcpy.Parameter(
            displayName="County", name="county", datatype="GPString",
            parameterType="Required", direction="Input")
        try:
            s01 = next(s for s in config.sources()["sources"]
                       if s["source_id"] == "S01")
            county.filter.type = "ValueList"
            county.filter.list = sorted((s01.get("counties") or {}).keys())
        except Exception:
            pass

        out_gdb = arcpy.Parameter(
            displayName="Target geodatabase", name="gdb", datatype="DEWorkspace",
            parameterType="Required", direction="Input")
        try:
            out_gdb.value = config.paths()["gdb"]
        except Exception:
            pass

        max_pages = arcpy.Parameter(
            displayName="Max pages (0 = all; a small number pilots the ingest)",
            name="max_pages", datatype="GPLong",
            parameterType="Optional", direction="Input")
        max_pages.value = 0

        reuse = arcpy.Parameter(
            displayName="Reuse an existing raw download if present",
            name="reuse_download", datatype="GPBoolean",
            parameterType="Optional", direction="Input")
        reuse.value = True

        allow_unverified = arcpy.Parameter(
            displayName="Allow an unverified field map (not recommended)",
            name="allow_unverified", datatype="GPBoolean",
            parameterType="Optional", direction="Input")
        allow_unverified.value = False

        return [source_id, county, out_gdb, max_pages, reuse, allow_unverified]

    def isLicensed(self):
        return True

    def updateMessages(self, parameters):
        source_id, county, gdb_p, _mp, _reuse, allow = parameters
        if county.valueAsText and source_id.valueAsText:
            try:
                cfg = li_etl.county_config(source_id.valueAsText, county.valueAsText)
                if cfg.get("status") != "verified" and not allow.value:
                    county.setErrorMessage(
                        "Field map status is '%s', not 'verified'. Verify it "
                        "against the live source, or tick the override."
                        % cfg.get("status"))
                elif cfg.get("status") != "verified":
                    county.setWarningMessage("Ingesting on an UNVERIFIED field map.")
            except li_etl.IngestRefused as exc:
                county.setErrorMessage(str(exc))
        if gdb_p.valueAsText and not arcpy.Exists(gdb_p.valueAsText):
            gdb_p.setErrorMessage("Geodatabase not found. Run tool 1 first.")
        return

    def execute(self, parameters, messages):
        source_id = parameters[0].valueAsText
        county = parameters[1].valueAsText
        gdb_path = parameters[2].valueAsText
        max_pages = int(parameters[3].value or 0) or None
        reuse = bool(parameters[4].value)
        allow_unverified = bool(parameters[5].value)

        run_id = logging_utils.make_run_id("ingest")
        log_dir = Path(config.paths()["logs_dir"])
        logging_utils.get_logger("li", log_dir=log_dir, run_id=run_id)

        arcpy.AddMessage("run_id      %s" % run_id)
        arcpy.AddMessage("git commit  %s" % logging_utils.git_commit(_REPO)[:10])
        if max_pages:
            arcpy.AddWarning("PILOT MODE: stopping after %d pages." % max_pages)

        try:
            summary = li_etl.ingest_county_parcels(
                county=county, run_id=run_id, source_id=source_id,
                gdb=gdb_path, max_pages=max_pages,
                allow_unverified=allow_unverified, reuse_download=reuse)
        except li_etl.IngestRefused as exc:
            arcpy.AddError("Ingest refused: %s" % exc)
            raise arcpy.ExecuteError(str(exc))

        arcpy.AddMessage("-" * 58)
        for key, value in summary.items():
            arcpy.AddMessage("%-22s %s" % (key, value))
        arcpy.AddMessage("-" * 58)
        return

    def postExecute(self, parameters):
        return


class RunQAQC(object):
    """Tool 3 - run the scope Section 10 checks and log them to QAQC_Log."""

    def __init__(self):
        self.label = "3 - Run QA/QC"
        self.description = (
            "Runs the scope Section 10 quality checks against a loaded layer "
            "and writes every result to QAQC_Log. Hard checks - CRS, null and "
            "invalid geometry, duplicate and null keys - fail the run. Rates "
            "expected to be non-zero, such as exempt parcels carrying a zero "
            "land value, are reported as warnings so they stay visible without "
            "being treated as defects."
        )
        self.category = "2 - Data"
        self.canRunInBackground = False

    def getParameterInfo(self):
        gdb_p = arcpy.Parameter(
            displayName="Geodatabase", name="gdb", datatype="DEWorkspace",
            parameterType="Required", direction="Input")
        try:
            gdb_p.value = config.paths()["gdb"]
        except Exception:
            pass

        layer = arcpy.Parameter(
            displayName="Layer to check", name="layer", datatype="GPString",
            parameterType="Required", direction="Input")
        layer.filter.type = "ValueList"
        layer.filter.list = ["Parcels"]
        layer.value = "Parcels"

        min_features = arcpy.Parameter(
            displayName="Minimum expected feature count", name="min_features",
            datatype="GPLong", parameterType="Optional", direction="Input")
        min_features.value = 1

        fail_on_error = arcpy.Parameter(
            displayName="Fail the tool if any hard check fails",
            name="fail_on_error", datatype="GPBoolean",
            parameterType="Optional", direction="Input")
        fail_on_error.value = True

        return [gdb_p, layer, min_features, fail_on_error]

    def isLicensed(self):
        return True

    def execute(self, parameters, messages):
        gdb_path = parameters[0].valueAsText
        layer = parameters[1].valueAsText
        min_features = int(parameters[2].value or 1)
        fail_on_error = bool(parameters[3].value)

        run_id = logging_utils.make_run_id("qaqc")
        log_dir = Path(config.paths()["logs_dir"])
        logging_utils.get_logger("li", log_dir=log_dir, run_id=run_id)

        fc = os.path.join(gdb_path, "Cadastral", layer)
        if not arcpy.Exists(fc):
            raise arcpy.ExecuteError("%s not found." % fc)

        expected_crs = int(config.schema()["meta"]["crs"])
        results = li_qaqc.run_parcel_checks(fc, gdb_path, expected_crs, min_features)
        written = li_qaqc.write_log(gdb_path, run_id, results)
        counts = li_qaqc.summarize(results)

        arcpy.AddMessage("run_id %s  |  %d results written to QAQC_Log"
                         % (run_id, written))
        arcpy.AddMessage("-" * 76)
        for r in results:
            line = "%-8s %-18s %-46s %s" % (r.result, r.check_id, r.check_name, r.detail)
            if r.result == li_qaqc.FAIL:
                arcpy.AddError(line)
            elif r.result == li_qaqc.WARN:
                arcpy.AddWarning(line)
            else:
                arcpy.AddMessage(line)
        arcpy.AddMessage("-" * 76)
        arcpy.AddMessage("Pass %d  Warning %d  Fail %d  Skipped %d"
                         % (counts.get("Pass", 0), counts.get("Warning", 0),
                            counts.get("Fail", 0), counts.get("Skipped", 0)))

        if fail_on_error and counts.get("Fail", 0):
            raise arcpy.ExecuteError(
                "%d hard QA check(s) failed - see QAQC_Log." % counts["Fail"])
        return

    def postExecute(self, parameters):
        return
