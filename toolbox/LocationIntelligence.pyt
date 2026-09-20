# -*- coding: utf-8 -*-
"""LocationIntelligence - ArcGIS Python toolbox.

Site-selection analysis for a DICK'S Sporting Goods regional distribution
center in the Dallas-Fort Worth MSA. Implements scope Section 6.3.

Tools are thin wrappers: parameter definition, validation, and logging live
here, while all real work lives in the importable `li` package under src/ so
it can be unit-tested and called from run_pipeline.py without ArcGIS.

Implemented
    1  BuildGeodatabaseSchema

Planned (scope 6.3)
    2  IngestAndStandardize        8  ComputeWorkforceMetrics
    3  RunQAQC                     9  ComputeCriteriaScores
    4  BuildNetworkDataset        10  WeightedSuitability
    5  ScreenCandidateSites       11  SensitivityRunner
    6  BuildServiceAreas          12  ExportSiteProfiles
    7  BuildODMatrices            13  PublishToAGOL (optional)
"""

import importlib
import sys
from pathlib import Path

import arcpy

# Make src/ importable regardless of where the toolbox is opened from.
_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import li  # noqa: E402
from li import config, gdb as li_gdb, logging_utils  # noqa: E402

# ArcGIS caches toolbox modules between runs; reload so edits take effect
# without restarting Pro.
for _mod in (li, config, li_gdb, logging_utils):
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
        self.tools = [BuildGeodatabaseSchema]


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
