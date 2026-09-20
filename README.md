# Site Selection: DICK'S Sporting Goods Regional Distribution Center — Dallas–Fort Worth

A reproducible, multi-criteria location-intelligence study identifying the best sites in the
Dallas–Fort Worth MSA for a **~800,000 SF regional distribution center on ~90 acres**, serving
**100+ stores** across the south-central U.S.

Built with ArcGIS Pro, `arcpy`, and a config-driven Python toolbox. Every threshold, weight, and
data source lives in `config/` — nothing analytical is hard-coded.

> **Status: in development.** Geodatabase design and the schema build tool are complete.
> Data acquisition, analysis, and deliverables are in progress. See [Progress](#progress).

---

## The question

> Which sites in the Dallas–Fort Worth MSA best satisfy DICK'S requirement for a ~90-acre,
> 800,000 SF regional distribution center, given its stated priorities of workforce availability
> and store-network proximity — and how do the leading candidates compare?

The client's published requirement drives every threshold in the model:

| Parameter | Requirement |
|---|---|
| Facility | ~800,000 SF regional distribution center |
| Site | ~90 acres, single site or assemblage |
| Employment | ~300 full-time jobs over ten years |
| Network served | 100+ stores across several states |
| Stated priorities | Qualified workforce; proximity to the Texas store footprint; business-friendly environment |

## Approach

1. **Screen** the full parcel universe across 11 counties against eight hard filters — acreage,
   zoning, floodway/SFHA, wetlands, slope, land cover, utility service, and highway access.
   Every evaluated polygon records *why* it failed, so the screen is auditable rather than a
   black box.
2. **Analyze** the survivors on a locally-built road network with separate `Driving` and `Truck`
   travel modes: labor-shed service areas, freight reach, and origin–destination matrices to the
   served store set.
3. **Score** each candidate on 11 criteria, winsorized and min–max normalized to 0–100.
4. **Weight** under three scenarios — `Balanced`, `LaborFirst`, `AccessFirst` — and test rank
   stability with one-at-a-time perturbation, a 1,000-draw Dirichlet Monte Carlo, and a
   threshold sweep.
5. **Recommend** one site and one alternate, with the non-modeled due-diligence items stated
   explicitly rather than hidden.

## Criteria and weights

| ID | Criterion | Direction | Balanced | LaborFirst | AccessFirst |
|---|---|---|---:|---:|---:|
| C01 | Warehouse/transport labor pool (30-min shed) | Benefit | 0.20 | 0.30 | 0.12 |
| C02 | Labor availability (unemployment rate) | Benefit | 0.05 | 0.08 | 0.03 |
| C03 | Proven commutability (LODES OD) | Benefit | 0.10 | 0.15 | 0.05 |
| C04 | Highway access (truck min to interchange) | Cost | 0.12 | 0.08 | 0.18 |
| C05 | Store-network access (mean truck min) | Cost | 0.18 | 0.12 | 0.28 |
| C06 | Intermodal access | Cost | 0.08 | 0.05 | 0.12 |
| C07 | Site size (capped at 150 ac) | Benefit | 0.05 | 0.04 | 0.04 |
| C08 | Terrain (mean % slope) | Cost | 0.03 | 0.02 | 0.02 |
| C09 | Flood risk (% SFHA) | Cost | 0.05 | 0.04 | 0.04 |
| C10 | Land cost (appraised $/acre) | Cost | 0.07 | 0.06 | 0.05 |
| C11 | Industrial cluster (sq ft within 3 mi) | Benefit | 0.07 | 0.06 | 0.07 |

## Results

_Pending analysis. This section will carry the shortlist, the recommended site, and the
sensitivity summary._

---

## Geodatabase design

`DFW_DSG_SiteSelection.gdb` is built entirely from [`config/schema.yaml`](config/schema.yaml) —
a machine-readable specification, not a hand-clicked database. One tool run produces:

| Component | Count |
|---|---:|
| Feature datasets | 10 |
| Feature classes | 29 |
| Standalone tables | 11 |
| Domains (9 coded, 2 range) | 11 |
| Relationship classes | 10 |
| Topology (3 rules) | 1 |
| Attribute rules (3 calculation, 2 constraint) | 5 |

Design notes, the ERD, and the full data dictionary live in [`docs/`](docs/).

**Analysis CRS:** EPSG:6584 — NAD83(2011) StatePlane Texas North Central FIPS 4202 (US Feet).
Published web layers are reprojected to EPSG:3857.

---

## Documentation

| Document | What it covers |
|---|---|
| **[docs/DATA_ACQUISITION.md](docs/DATA_ACQUISITION.md)** | How to obtain every source S01–S23 by hand — portal, endpoint, steps, licence, CRS |
| **[docs/REPRODUCE.md](docs/REPRODUCE.md)** | End-to-end reproduction from a clean clone |
| [docs/PLAN.md](docs/PLAN.md) | Milestone tracker with exit criteria and dependency gates |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Append-only decision log |
| [docs/recon/RECON_findings.md](docs/recon/RECON_findings.md) | What the sources actually contain, verified live |
| [docs/tutorial/](docs/tutorial/) | Dual-track lessons — automated *and* manual, with concepts |

## Quickstart

### Requirements

- ArcGIS Pro 3.x with **Network Analyst** and **Spatial Analyst**
- Git

### Setup

```bash
git clone <repo-url>
cd dicks-distribution-center-site-selection
```

The stock `arcgispro-py3` conda environment is read-only, so clone it before adding packages:

```bash
conda create --clone arcgispro-py3 --name dsg-dfw
```

```bash
conda activate dsg-dfw && conda install -c conda-forge geopandas shapely pyogrio
```

### Configure paths

Bulk data and the geodatabase live outside the repository. Defaults are in
[`config/paths.yaml`](config/paths.yaml) and any value can be overridden with a `DSG_`-prefixed
environment variable:

```bash
set DSG_DATA_ROOT=D:\GIS\dsg-dfw\data
```

### Build the geodatabase

From the ArcGIS Pro Python environment:

```bash
python -c "import sys; sys.path.insert(0,'src'); from li import gdb; gdb.build_schema(overwrite=True)"
```

Or open `toolbox/LocationIntelligence.pyt` in ArcGIS Pro and run **1 – Build Geodatabase Schema**.
A full build takes roughly 3–4 minutes; most of it is adding GlobalIDs and attribute rules.

### Open the ArcGIS Pro project

`pro/DFW_DSG.aprx` is the project used for the network dataset, symbology, layouts, and map
exports. It comes wired to the geodatabase and to `toolbox/LocationIntelligence.pyt`, with
**store relative paths to data sources** enabled.

> **Build the geodatabase first.** The project's default geodatabase points at
> `DFW_DSG_SiteSelection.gdb` as configured in `config/paths.yaml`. If that geodatabase has not
> been created by **BuildGeodatabaseSchema**, the project still opens, but its default
> geodatabase and any layers drawn from it will not resolve.

To recreate the project from scratch — it is regenerable, not hand-built:

```bash
python tools/setup_pro_project.py --force
```

### Run the tests

```bash
python -m pytest tests/ -q
```

The test suite is deliberately arcpy-free so it runs in CI. It validates that weights sum to
1.00, that every field's domain is declared, that relationship keys exist on both sides, that
subtype fields are integers, and that `criteria.yaml` stays in step with `weights.json` — the
errors that would otherwise surface minutes into a geodatabase build.

---

## Repository layout

```
config/       schema, sources, screening thresholds, network settings, criteria, weights
toolbox/      LocationIntelligence.pyt + ModelBuilder models
pro/          DFW_DSG.aprx — ArcGIS Pro project (network dataset, symbology, layouts)
src/li/       importable package (all real logic lives here)
tests/        arcpy-free unit tests, run in CI
tools/        repo utilities (Pro project setup, portfolio placeholders)
docs/         ERD, data dictionary, design rationale, methodology report
notebooks/    exploration and results review
outputs/      maps, map series, tables, logs
```

## Progress

| Phase | Status |
|---|---|
| Geodatabase design + schema build tool | ✅ Complete |
| Config-driven parameters (6 config files) | ✅ Complete |
| Schema integrity test suite | ✅ Complete — 26 tests |
| Data acquisition (S01–S22) | ⏳ Next |
| ETL, QA/QC tools | ◻ Not started |
| Network dataset + screening | ◻ Not started |
| Service areas, OD matrices, scoring | ◻ Not started |
| Sensitivity analysis | ◻ Not started |
| Maps, map series, dashboard, StoryMap | ◻ Not started |
| Methodology report | ◻ Not started |

## Data sources

All sources are free and public — TxGIO/county appraisal districts (parcels), TxDOT RHiNo and
OpenStreetMap (roads), US Census ACS/TIGER/LODES (demographics and workforce), FEMA NFHL (flood),
USFWS NWI (wetlands), USDA SSURGO (soils), USGS 3DEP (elevation), MRLC NLCD (land cover),
USDOT BTS NTAD (intermodal), TCEQ (utility CCN), and HIFLD (electric). Full provenance —
provider, vintage, download date, license, native CRS, and transformation — is recorded per
layer in the `DataSourceRegistry` table and in [`config/sources.yaml`](config/sources.yaml).

## Known limitations

- **Zoning coverage is incomplete by nature.** No authoritative regional zoning layer exists;
  coverage is city-by-city and unincorporated county land has none. Parcels without published
  zoning are classified from land use plus NLCD and flagged `Review` rather than silently
  passed or failed.
- **Utility CCN indicates the right to serve, not capacity at the parcel.** Treated as a
  due-diligence item, not a guarantee.
- **Incentives, entitlement timing, and build-to-suit availability are not modeled.** They are
  listed as due-diligence considerations in the recommendation.

## License

Code is released under the MIT License (see [LICENSE](LICENSE)). Data remains under the terms of
its respective providers; OpenStreetMap-derived layers require ODbL attribution on published maps.

## Author

**Bernard Issifu** — GIS Analyst
