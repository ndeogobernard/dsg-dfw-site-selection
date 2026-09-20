# Reproducing this study

End-to-end, from a clean clone to a ranked shortlist. Acceptance criterion §13.1 requires that
`python run_pipeline.py --scenario Balanced --steps all` reproduces `SiteScores` and `Shortlist`
from raw data; §13.6 requires that an independent reviewer can do it from the README.

Two tracks, and both are supported deliberately:

| Track | For |
|---|---|
| **Automated** | Reproducing the result. Run the toolbox. |
| **Manual** | Understanding the result, or auditing it. Do the same work by hand in ArcGIS Pro. `docs/tutorial/` teaches this path. |

---

## 0 · Prerequisites

- **ArcGIS Pro 3.x** with **Network Analyst** and **Spatial Analyst** (both required)
- A cloned conda environment — `arcgispro-py3` is read-only:

```bash
conda create --clone arcgispro-py3 --name dsg-dfw
```

```bash
conda activate dsg-dfw && conda install -c conda-forge geopandas shapely pyogrio
```

- **A Census API key.** Free and instant at <https://api.census.gov/data/key_signup.html>.
  Set `CENSUS_API_KEY`. Without it, ACS requests return an HTML *"Missing Key"* page rather
  than an error, which fails confusingly.
- Roughly **150 GB** free disk. gSSURGO and 3DEP dominate.

## 1 · Configure paths

Bulk data and the geodatabase live outside the repository. Defaults are in
[`config/paths.yaml`](../config/paths.yaml); any value can be overridden with a `DSG_`-prefixed
environment variable:

```bash
set DSG_DATA_ROOT=D:\GIS\dsg-dfw\data
```

## 2 · Acquire the data

**→ [`docs/DATA_ACQUISITION.md`](DATA_ACQUISITION.md)** — the complete manual playbook, one
section per source S01–S23: portal, exact endpoint, step-by-step, destination, licence, vintage,
native CRS, and whether it is scripted or hand-fetched.

Roughly two-thirds of the sources are **MANUAL** — interactive portals, per-county picking, or
licence click-through. That is a property of public GIS data, not an omission. Read that
document before starting; several sources carry traps that cost hours if hit blind (the Tarrant
lookalike parcel layer, NFHL's missing floodway field, the ACS occupation split).

Everything lands in `data/raw/<source_id>/`, unmodified.

## 3 · Build the geodatabase

```bash
python -c "import sys; sys.path.insert(0,'src'); from li import gdb; gdb.build_schema(overwrite=True)"
```

Or run **1 – Build Geodatabase Schema** from `toolbox/LocationIntelligence.pyt` in ArcGIS Pro.
~3–4 minutes. Creates 10 feature datasets, 29 feature classes, 11 tables, 11 domains,
10 relationship classes, 1 topology, and 5 attribute rules from `config/schema.yaml`.

## 4 · Open the Pro project

`pro/DFW_DSG.aprx` — already wired to the geodatabase and the Python toolbox, relative paths on.
**Build the geodatabase first** (step 3) or its layers will not resolve. Regenerate with:

```bash
python tools/setup_pro_project.py --force
```

## 5 · Run the pipeline

```bash
python run_pipeline.py --scenario Balanced --steps all
```

Then repeat for `LaborFirst` and `AccessFirst`. Each run writes a `ScoreRuns` row carrying its
`run_id`, parameters, and the **git commit hash** — so any result traces back to the exact code
that produced it.

## 6 · Verify

```bash
python -m pytest tests/ -q
```

The suite is arcpy-free by design and also runs in CI. Check `QAQC_Log` against the §10
thresholds, and confirm weights sum to 1.00 per scenario.

## 7 · Publish (Week 6+, optional)

Requires ArcGIS Online. See [`docs/PLAN.md`](PLAN.md) Week 6 and **D-011** — authentication is
through ArcGIS Pro's active portal session, and **no credential is ever stored in this
repository**.

---

## Learning rather than running

[`docs/tutorial/`](tutorial/) walks the same work as teaching material. Every lesson is
**dual-track**: the automated command *and* the manual ArcGIS Pro equivalent, plus a
*Concepts* note explaining why the step works — so a reader can follow the reasoning, not just
the keystrokes.

## If something does not reproduce

1. Check the source **vintage** in `DataSourceRegistry` against what you downloaded. Sources
   change; the study is a snapshot.
2. Check `config/screening.yaml` — the auto-relaxation ladder may have settled on different
   parameters. The values actually used are in `ScoreRuns.parameters_json`.
3. Check the git commit in `ScoreRuns` against your checkout.
4. Sensitivity results are seeded; an unseeded re-run will not match exactly.
