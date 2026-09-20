# Site-Selection Analysis: DICK'S Sporting Goods Regional Distribution Center — Dallas–Fort Worth Market

**Project type:** Location-intelligence study (site selection)
**Client / use case:** DICK'S Sporting Goods — regional distribution center
**Market:** Dallas–Fort Worth–Arlington MSA, Texas
**Document version:** 1.1 — 19 September 2026
**Document owner:** Bernard Issifu
**Executed by:** Geospatial Analyst / Developer (hereafter "the Analyst")
**Status:** Scoped — ready for execution

---

## 0. Read this first

This document is a complete handoff specification. It defines the business question, study area, data sources, geodatabase design, analytical methodology, automation/toolbox requirements, visualization deliverables, communication deliverables, report structure, QA/QC, repository layout, timeline, and acceptance criteria. The Analyst should be able to execute the entire project from this document without further scoping.

Where a value is marked **[VERIFY]**, confirm it against the live source before use. Where a value is marked **[DECISION]**, the Analyst may choose, but must record the choice in the methodology report.

---

## 1. Background and business question

### 1.1 Client requirement

DICK'S Sporting Goods requires a regional distribution center in the Dallas–Fort Worth market to support its Texas business and serve its store network across the south-central U.S. Requirement profile (from the company's public announcement, Aug 2024):

| Parameter | Requirement |
|---|---|
| Facility | ~800,000 SF regional distribution center |
| Site | ~90 acres, single site or assemblage |
| Employment | ~300 full-time jobs, ramping over ten years |
| Network served | 100+ DICK'S Sporting Goods stores across several states |
| Stated priorities | Qualified and reliable workforce; proximity to the existing and expanding Texas store footprint; business-friendly environment |

The 90-acre / 800,000 SF / 300-job / 100+ store parameters drive the screening thresholds, criteria, and default weights throughout this document.

### 1.2 The analytical question

> **Which sites in the Dallas–Fort Worth MSA best satisfy DICK'S requirement for a ~90-acre, 800,000 SF regional distribution center, given its priorities of workforce availability and store-network proximity — and how do the leading candidates compare?**

### 1.3 Objectives

1. Build a reproducible, multi-criteria site-selection model for a large regional DC in the DFW MSA.
2. Screen the full parcel universe to a defensible candidate pool.
3. Score and rank all qualifying candidates under three weighting scenarios and test rank stability.
4. Deliver a top-five shortlist with site profiles and a recommended site.
5. Package the work as (a) a flagship portfolio project and (b) a standalone geodatabase-design portfolio project, plus supporting artifacts.

### 1.4 Success criteria (project level)

- Every analytical step is executable from the repository with a single command per scenario.
- A ranked shortlist, sensitivity results, and a written recommendation are produced for all three scenarios.
- All deliverables in Section 12 are produced and pass the acceptance checks in Section 13.

---

## 2. Study area and reference geography

### 2.1 Study area

Dallas–Fort Worth–Arlington MSA (11 counties): **Collin, Dallas, Denton, Ellis, Hunt, Johnson, Kaufman, Parker, Rockwall, Tarrant, Wise.** [VERIFY current OMB MSA definition.]

A 15-mile buffer around the MSA is used for network and demographic context so drive-time polygons and labor sheds are not truncated at the boundary.

### 2.2 Store-service network (demand points)

The DC will serve 100+ DICK'S stores across several states. Compile all DICK'S Sporting Goods, Golf Galaxy, Public Lands, and DICK'S House of Sport locations within a **600-mile radius of the MSA centroid**, then define the *served set* as stores within a **10-hour truck drive** (single-driver one-day delivery) of the MSA centroid. Expected coverage: Texas, Oklahoma, Louisiana, Arkansas, New Mexico, and possibly parts of Kansas, Missouri, Mississippi, Colorado. [DECISION: retain all stores within 10-hour truck time as served set; record the count.]

Sourcing method (choose one, document it):
1. Compile from the DICK'S store locator on dicks.com (manual or scripted), geocode with the ArcGIS World Geocoding Service or Census Geocoder.
2. Extract from OpenStreetMap (`shop=sports`, `brand=DICK'S Sporting Goods` / `brand:wikidata` tag) and validate against the locator.

Store `Stores_DSG` with fields: `store_id, banner, name, address, city, state, zip, lat, lon, source, geocode_score, served_flag`.

### 2.3 Coordinate reference system

- **Analysis CRS:** NAD 1983 (2011) State Plane Texas North Central FIPS 4202 (US Feet), EPSG:6584 [VERIFY]; acceptable alternative NAD83 / TX N Central EPSG:2276.
- **Web/visualization CRS:** WGS 84 Web Mercator (EPSG:3857) for AGOL.
- All source layers are reprojected to the analysis CRS on ingest; the source CRS and transformation used are recorded in `DataSourceRegistry`.

---

## 3. Data sources

All sources are free and public. Record provider, dataset name, vintage, download date, license, native CRS, and known limitations in `DataSourceRegistry` and in Appendix A of the report. URLs below are the canonical portals; confirm exact download endpoints at time of use.

| ID | Category | Dataset | Provider / portal | Vintage target | Use |
|---|---|---|---|---|---|
| S01 | Parcels | Statewide parcels (11 counties) | Texas Geographic Information Office (TxGIO / formerly TNRIS) StratMap Land Parcels; county appraisal districts (TAD, DCAD, CCAD, Denton CAD, etc.) as fallback | Latest | Candidate universe, acreage, land use, appraised value |
| S02 | Zoning | Municipal zoning | City open-data portals: Fort Worth, Dallas, Arlington, Irving, Grand Prairie, Burleson, Lancaster, Mesquite, Denton, Frisco, McKinney, etc. | Latest | Industrial-zoned filter |
| S03 | Roads | TxDOT Roadway Inventory (RHiNo) | TxDOT Open Data Portal | Latest | Network dataset (primary) |
| S04 | Roads (alt) | OpenStreetMap Texas extract | Geofabrik (download.geofabrik.de) | Latest | Network dataset (alternate / gap fill) |
| S05 | Interchanges | Interstate/limited-access interchanges | Derived from S03 (functional class 1 & 2 intersections) or NTAD | Latest | Highway-access criterion |
| S06 | Intermodal | Intermodal freight facilities, rail lines, airports | USDOT BTS National Transportation Atlas Database (NTAD) | Latest | Intermodal criterion |
| S07 | Freight network | National Highway Freight Network (NHFN) | FHWA | Latest | Context / corridor maps |
| S08 | Demographics | ACS 5-year estimates (block group): population, households, labor force, unemployment (B23025), occupation (C24010), commuting (B08301), vehicles (B08201), median HH income (B19013) | US Census Bureau, data.census.gov / Census API | Latest 5-year | Labor shed metrics |
| S09 | Geography | TIGER/Line block groups, tracts, counties, places, MSA | US Census Bureau | Matching ACS vintage | Joins, boundaries |
| S10 | Workforce OD | LEHD LODES 8: Workplace Area Characteristics (WAC), Residence Area Characteristics (RAC), Origin–Destination (OD), Texas + neighboring states | US Census Bureau LEHD (lehd.ces.census.gov) | Latest | Transportation & warehousing employment (NAICS 48–49, CNS08), commute flows |
| S11 | Wages | OEWS (53-7062 Laborers & Freight, Stock, Material Movers; 53-7065 Stockers; 53-3032 Heavy Truck Drivers) for DFW MSA; QCEW county-level NAICS 493 | BLS | Latest | Wage context (report), county-level labor cost criterion |
| S12 | Employers | County Business Patterns (NAICS 493, 484) | US Census Bureau | Latest | Cluster context |
| S13 | Flood | National Flood Hazard Layer (NFHL) | FEMA Map Service Center | Latest | Hard filter (floodway, Zone AE/A) and risk criterion |
| S14 | Wetlands | National Wetlands Inventory | USFWS | Latest | Hard filter / risk |
| S15 | Soils | SSURGO (gSSURGO Texas) | USDA NRCS | Latest | Soils suitability (hydric, shrink-swell) |
| S16 | Elevation | 3DEP 1/3 arc-second DEM (or 1 m where available) | USGS National Map | Latest | Slope |
| S17 | Land cover | NLCD | MRLC | Latest | Developed vs. undeveloped screening |
| S18 | Buildings | Microsoft/Google Open Buildings or OSM building footprints | Microsoft (GitHub), OSM | Latest | Industrial cluster density |
| S19 | Water/sewer service | Certificates of Convenience and Necessity (CCN) — water & sewer | TCEQ | Latest | Utility-service hard filter |
| S20 | Electric | Substations, transmission lines | HIFLD Open Data | Latest | Context (optional criterion) |
| S21 | Stores | DICK'S / Golf Galaxy / Public Lands / House of Sport locations | dicks.com store locator; OSM | Sep 2026 | Demand points |
| S22 | Industrial market context | Industrial submarket boundaries (if publicly available), NCTCOG land use | NCTCOG Regional Data Center | Latest | Context maps |
| S23 | Lightcast (optional) | Occupation/industry staffing patterns, if trial access obtained | Lightcast | Latest | Enhancement; otherwise note as commercial equivalent |

---

## 4. Geodatabase design and management (standalone portfolio project)

### 4.1 Deliverable

- `DFW_DSG_SiteSelection.gdb` — file geodatabase (primary).
- `schema/schema.yaml` — machine-readable schema definition used by the `BuildGeodatabaseSchema` tool.
- `docs/ERD.png` and `docs/ERD.drawio` — entity-relationship diagram.
- `docs/DataDictionary.md` — every feature class, table, field, domain, subtype, relationship.
- `docs/GDB_DesignRationale.md` — the write-up for the portfolio page.
- Optional stretch: `docker/postgis/` — PostGIS replica with DDL and a loader script, to demonstrate enterprise/multi-user design.

### 4.2 Feature datasets and feature classes

All feature classes in the analysis CRS (Section 2.3). Naming: `PascalCase`, no spaces, prefix by role where useful. Fields: `snake_case`.

| Feature dataset | Feature class | Geometry | Key fields (in addition to OBJECTID/Shape) |
|---|---|---|---|
| `Reference` | `StudyArea_MSA` | Polygon | `geoid, name, county_cnt, area_sqmi` |
| `Reference` | `Counties` | Polygon | `geoid, name, state_fips, county_fips` |
| `Reference` | `Places` | Polygon | `geoid, name, place_type` |
| `Cadastral` | `Parcels` | Polygon | `parcel_id, county, situs_addr, owner_type, land_use_code, land_use_class (domain), zoning_code, zoning_class (domain), acres, appraised_land_val, appraised_total_val, land_val_per_acre, year_built, improvement_flag, source_id` |
| `Cadastral` | `ParcelAssemblages` | Polygon | `assemblage_id, parcel_cnt, acres, dominant_zoning_class, method` |
| `Cadastral` | `Zoning` | Polygon | `city, zoning_code, zoning_class (domain), industrial_flag, source_id` |
| `Transportation` | `Roads` | Polyline | `road_id, name, func_class, speed_mph, oneway, truck_restrict, lanes, source_id` |
| `Transportation` | `RoadNetwork_ND` | Network dataset | Travel modes: `Driving`, `Truck` |
| `Transportation` | `Interchanges` | Point | `interchange_id, route_a, route_b, interchange_type` |
| `Transportation` | `IntermodalTerminals` | Point | `facility_id, name, operator, mode, source_id` |
| `Transportation` | `Railroads` | Polyline | `owner, class, source_id` |
| `Transportation` | `Airports` | Point | `name, faa_code, cargo_flag` |
| `Demographics` | `BlockGroups_ACS` | Polygon | `geoid, pop_total, hh_total, labor_force, unemployed, unemp_rate, occ_transp_matmov, occ_prod, med_hh_inc, workers_16plus, vehicles_0_hh, acs_vintage` |
| `Demographics` | `BlockGroups_Centroids` | Point | `geoid, pop_total, pop_weighted_flag` |
| `Demographics` | `Tracts` | Polygon | `geoid, name` |
| `Workforce` | `Tracts_LODES_WAC` | Polygon | `geoid, jobs_total, jobs_cns08_transp_wh, jobs_cns07_retail, lodes_year` |
| `Workforce` | `Tracts_LODES_RAC` | Polygon | `geoid, res_workers_total, res_cns08, lodes_year` |
| `Workforce` | `LODES_OD_Flows` | Polyline (or table) | `h_geoid, w_geoid, s000, sa01, sa02, sa03, se01, se02, se03, si01, si02, si03` |
| `Environmental` | `FloodZones_NFHL` | Polygon | `fld_zone (domain), sfha_flag, floodway_flag, source_id` |
| `Environmental` | `Wetlands_NWI` | Polygon | `wetland_type, attribute` |
| `Environmental` | `Soils_SSURGO` | Polygon | `mukey, hydric_pct, shrink_swell_class, drainage_class` |
| `Environmental` | `Slope_pct` | Raster (in GDB) | Percent slope from DEM |
| `Environmental` | `LandCover_NLCD` | Raster | NLCD class |
| `Utilities` | `WaterCCN` | Polygon | `ccn_no, utility_name, type` |
| `Utilities` | `SewerCCN` | Polygon | `ccn_no, utility_name, type` |
| `Utilities` | `Substations` | Point | `name, voltage_kv, owner` |
| `Market` | `Stores_DSG` | Point | see 2.2 |
| `Market` | `IndustrialBuildings` | Polygon | `bldg_id, area_sqft, industrial_flag, source_id` |
| `Analysis` | `CandidateSites` | Polygon | `cand_id, parcel_ids, acres, zoning_class, screen_status (domain), screen_reason, centroid_x, centroid_y, run_id` |
| `Analysis` | `ServiceAreas_Driving` | Polygon | `cand_id, break_min (15/30/45), run_id` |
| `Analysis` | `ServiceAreas_Truck` | Polygon | `cand_id, break_min (60/120/240), run_id` |
| `Analysis` | `OD_Cand_to_Stores` | Polyline/table | `cand_id, store_id, truck_minutes, truck_miles, run_id` |
| `Analysis` | `OD_Cand_to_Interchange` | table | `cand_id, interchange_id, truck_minutes` |
| `Analysis` | `OD_Cand_to_Intermodal` | table | `cand_id, facility_id, truck_minutes` |
| `Results` | `SiteScores` | Polygon | `cand_id, run_id, scenario, c01_raw … c11_raw, c01_s … c11_s, composite, rank, percentile, score_class (domain)` |
| `Results` | `Shortlist` | Polygon | `cand_id, scenario, rank, composite, profile_page_no, recommended_flag, notes` |
| `Results` | `SensitivityResults` | table | `run_id, scenario, cand_id, base_rank, min_rank, max_rank, mean_rank, top5_freq, top10_freq` |

### 4.3 Standalone tables

| Table | Purpose | Key fields |
|---|---|---|
| `DataSourceRegistry` | Provenance for every layer | `source_id, provider, dataset, url, vintage, download_date, license, native_crs, transformation, notes` |
| `CriteriaDefinitions` | Criteria metadata | `criterion_id, name, description, unit, direction (benefit/cost), normalization, source_id` |
| `WeightScenarios` | Weight sets | `scenario, criterion_id, weight` |
| `ScoreRuns` | Run log | `run_id, scenario, timestamp, user, toolbox_version, git_commit, parameters_json, cand_cnt, notes` |
| `QAQC_Log` | QA/QC results | `check_id, run_id, layer, check_name, result, count, threshold, passed, timestamp` |
| `StoreServiceSet` | Served stores per run | `run_id, store_id, served_flag, truck_minutes` |

### 4.4 Domains

| Domain | Type | Values |
|---|---|---|
| `dm_LandUseClass` | coded | Industrial, Commercial, Vacant, Agricultural, Residential, Institutional, Other |
| `dm_ZoningClass` | coded | HeavyIndustrial, LightIndustrial, PlannedIndustrial, Commercial, Agricultural, Residential, MixedUse, Unknown |
| `dm_FloodZone` | coded | A, AE, AH, AO, X, X500, D, Floodway, OpenWater |
| `dm_ScreenStatus` | coded | Pass, Fail, Review |
| `dm_ScoreClass` | coded | 1 (lowest) – 5 (highest) |
| `dm_Scenario` | coded | Balanced, LaborFirst, AccessFirst |
| `dm_Direction` | coded | Benefit, Cost |
| `dm_TravelMode` | coded | Driving, Truck |
| `rg_Acres` | range | 0 – 10,000 |
| `rg_Score` | range | 0 – 100 |

### 4.5 Subtypes, relationships, topology, rules

- **Subtypes:** `Parcels` by `land_use_class` (Industrial / Commercial / Vacant / Residential / Other) with per-subtype default zoning class and domain assignments.
- **Relationship classes (all simple):**
  - `CandidateSites` 1:M `SiteScores` on `cand_id`
  - `ScoreRuns` 1:M `SiteScores` on `run_id`
  - `ScoreRuns` 1:M `SensitivityResults` on `run_id`
  - `WeightScenarios` M:1 `CriteriaDefinitions` on `criterion_id`
  - `DataSourceRegistry` 1:M each source-derived feature class on `source_id`
  - `CandidateSites` 1:M `OD_Cand_to_Stores` on `cand_id`
- **Topology `Cadastral_Topology`:** Parcels — Must Not Overlap, Must Not Have Gaps (cluster tolerance 0.1 ft); ParcelAssemblages — Must Not Overlap.
- **Attribute rules:**
  - Calculation: `Parcels.acres = Shape_Area / 43560` on insert/update; `land_val_per_acre = appraised_land_val / acres`.
  - Constraint: `SiteScores.composite BETWEEN 0 AND 100`; `SiteScores.rank >= 1`.
- **Metadata:** ISO 19139 (ArcGIS metadata style) on every feature class and table; abstract, purpose, source citation, process steps, contact.
- **Versioning strategy:** Raw ingested layers are immutable after ingest (suffix `_raw` in a separate `Raw` feature dataset or a sibling `DFW_DSG_Raw.gdb`). All analytical outputs carry `run_id`. Historic runs are retained; `Shortlist` reflects the latest approved run.
- **Maintenance:** `Compact` after each pipeline run; nightly backup zip of the GDB to `outputs/backups/`; retain last 5.

### 4.6 Network dataset specification

- Source: S03 (TxDOT) primary; S04 (OSM) to fill gaps or as alternate build. [DECISION: document which was used.]
- Attributes: `Minutes` (length / speed), `Miles`, `Oneway` restriction, `TruckRestricted` restriction (from truck-prohibited attributes where available; else functional-class rule: local residential streets restricted for Truck mode).
- Travel modes:
  - `Driving`: impedance Minutes; speed from posted/functional-class defaults; oneway respected.
  - `Truck`: impedance Minutes; speeds capped at 65 mph on freeways, 45 mph arterials, 25 mph locals; `TruckRestricted` avoided; U-turns not allowed.
- Alternative: ArcGIS Online routing services may be used for validation but the local network dataset is the reproducible source of record.

---

## 5. Analytical methodology

### 5.1 Phase A — Candidate screening (hard filters)

Input: `Parcels`, `Zoning`, `FloodZones_NFHL`, `Wetlands_NWI`, `Slope_pct`, `LandCover_NLCD`, `WaterCCN`, `SewerCCN`, `Interchanges`.

Steps:
1. **Assemblage:** Dissolve contiguous parcels sharing owner or zoning class where individual parcels are < 90 acres, to form `ParcelAssemblages` (max 6 parcels per assemblage). [DECISION: owner-based vs. zoning-based dissolve; document.]
2. Apply filters to parcels and assemblages:
   - `acres >= 80` (allows minor survey variance from the 90-acre target) **[parameter]**
   - `zoning_class IN (HeavyIndustrial, LightIndustrial, PlannedIndustrial)` OR (`zoning_class = Agricultural` AND within 1 mile of existing industrial-zoned land — captures rezonable greenfield) **[parameter]**
   - `floodway_flag = 0` AND SFHA coverage `< 20%` of area **[parameter]**
   - NWI wetland coverage `< 10%` of area **[parameter]**
   - Mean slope `< 5%` **[parameter]**
   - NLCD developed-high/medium intensity coverage `< 30%` (i.e., not already built out) **[parameter]**
   - Within a water CCN AND within a sewer CCN (or within 1 mile of sewer CCN boundary) **[parameter]**
   - Truck drive-time to nearest interstate interchange `<= 15 min` **[parameter]**
3. Write `CandidateSites` with `screen_status` and `screen_reason` (first failing rule) for all evaluated polygons, so failures are auditable. Expect 60–200 Pass candidates. If < 40, relax acreage to 70; if > 300, tighten interchange drive-time to 10 min. Record the final parameters.

### 5.2 Phase B — Network analysis

All on `RoadNetwork_ND`, run in batches via the toolbox.

| Analysis | Mode | Facilities | Breaks / targets | Output |
|---|---|---|---|---|
| Labor-shed service areas | Driving | Candidate centroids | 15, 30, 45 min | `ServiceAreas_Driving` |
| Freight-reach service areas | Truck | Candidate centroids | 60, 120, 240 min | `ServiceAreas_Truck` |
| OD to stores | Truck | Candidates → `Stores_DSG` (served set) | All pairs | `OD_Cand_to_Stores` |
| Closest interchange | Truck | Candidates → `Interchanges` | 1 nearest | `OD_Cand_to_Interchange` |
| Closest intermodal | Truck | Candidates → `IntermodalTerminals` (BNSF Alliance, UP Dallas Intermodal Terminal, DFW Airport cargo, Fort Worth Alliance Airport) [VERIFY list] | 1 nearest | `OD_Cand_to_Intermodal` |

Population-weighted block-group centroids (`BlockGroups_Centroids`) are intersected with service areas for demographic aggregation.

### 5.3 Phase C — Criteria

Each criterion is computed per candidate and stored as `cXX_raw`, then normalized to `cXX_s` in [0, 100].

| ID | Criterion | Measure (raw) | Direction | Source |
|---|---|---|---|---|
| C01 | Warehouse/transport labor pool | Sum of ACS `occ_transp_matmov` (workers in transportation & material-moving occupations) for block groups whose pop-weighted centroid falls in the 30-min Driving service area | Benefit | S08, B |
| C02 | Labor availability | Weighted unemployment rate across the same 30-min shed (unemployed / labor force) | Benefit | S08 |
| C03 | Proven commutability | LODES OD: sum of `s000` for workers with workplace in the candidate's tract(s) ∪ adjacent tracts; alternatively `jobs_cns08` in the 30-min shed | Benefit | S10 |
| C04 | Highway access | Truck minutes to nearest interstate interchange | Cost | B |
| C05 | Store-network access | Store-weighted mean truck minutes from candidate to all served stores (equal weights per store; optional: weight by store banner) | Cost | B, S21 |
| C06 | Intermodal access | Truck minutes to nearest intermodal terminal | Cost | B, S06 |
| C07 | Site size | Acres, capped at 150 (values above 150 treated as 150) | Benefit | S01 |
| C08 | Terrain | Mean percent slope | Cost | S16 |
| C09 | Flood risk | Percent of site within SFHA (A/AE/AH/AO) | Cost | S13 |
| C10 | Land cost | Appraised land value per acre (assemblage-weighted) | Cost | S01 |
| C11 | Industrial cluster | Sum of industrial building footprint area (sq ft) within 3 miles of centroid | Benefit | S18 |

Optional C12 (if Lightcast obtained): Lightcast staffing-pattern-based count of relevant occupations within 30 min. If used, rebalance weights and document.

### 5.4 Normalization

- Winsorize each raw criterion at the 5th and 95th percentiles across Pass candidates.
- Min–max scale to 0–100. For Cost criteria, invert: `s = 100 × (max − x) / (max − min)`.
- Store the min/max used per run in `ScoreRuns.parameters_json`.

### 5.5 Weighting scenarios

Weights sum to 1.00 per scenario. Rationale for the Balanced set: the client's stated priorities are workforce and store-network proximity.

| ID | Criterion | Balanced | LaborFirst | AccessFirst |
|---|---|---|---|---|
| C01 | Labor pool | 0.20 | 0.30 | 0.12 |
| C02 | Labor availability | 0.05 | 0.08 | 0.03 |
| C03 | Proven commutability | 0.10 | 0.15 | 0.05 |
| C04 | Highway access | 0.12 | 0.08 | 0.18 |
| C05 | Store-network access | 0.18 | 0.12 | 0.28 |
| C06 | Intermodal access | 0.08 | 0.05 | 0.12 |
| C07 | Site size | 0.05 | 0.04 | 0.04 |
| C08 | Terrain | 0.03 | 0.02 | 0.02 |
| C09 | Flood risk | 0.05 | 0.04 | 0.04 |
| C10 | Land cost | 0.07 | 0.06 | 0.05 |
| C11 | Industrial cluster | 0.07 | 0.06 | 0.07 |
| | **Total** | **1.00** | **1.00** | **1.00** |

Composite score: `composite = Σ (w_i × s_i)`. Rank descending. `score_class` = quintile (5 = top 20%).

### 5.6 Sensitivity analysis

1. **One-at-a-time (OAT):** For each criterion, perturb its weight by ±25%, renormalize remaining weights proportionally, recompute ranks. Report rank change of each top-10 candidate.
2. **Monte Carlo:** 1,000 draws from a Dirichlet distribution centered on the scenario weights (concentration parameter α = 50 × w). Record rank distribution per candidate. Report `min_rank, max_rank, mean_rank, top5_freq, top10_freq` to `SensitivityResults`.
3. **Threshold sensitivity:** Re-run Phase A with acreage 70/80/100 and interchange time 10/15/20 min; report candidate count and whether the top-five shortlist changes.

### 5.7 Shortlist, site profiles, and recommendation

Top 5 candidates under the Balanced scenario, cross-referenced with their ranks under LaborFirst and AccessFirst. For each: location map, acreage, zoning, composite and per-criterion scores, 30-min labor pool, unemployment rate, minutes to interchange/intermodal, store-network mean minutes, SFHA %, land value/acre, cluster sq ft, key risks, and a two-sentence assessment.

Recommendation: identify one recommended site and one alternate, with the rationale tied to the client's stated priorities, the sensitivity results (rank stability), and any non-modeled considerations to verify in due diligence (incentives, entitlement timing, build-to-suit availability, utility capacity, traffic impacts).

---

## 6. Automation, Python, ModelBuilder, and ArcGIS toolbox

### 6.1 Environment

- ArcGIS Pro 3.x with Network Analyst and Spatial Analyst extensions.
- Python 3.x (ArcGIS Pro conda env, cloned): `arcpy`, `pandas`, `numpy`, `pyyaml`, `requests`, `geopandas` (for non-arcpy ETL), `pyogrio`/`fiona`, `shapely`, `matplotlib`, `pytest`.
- Git; GitHub repository (public).

### 6.2 Repository layout

```
dsg-dfw-site-selection/
├── README.md                     # overview, quickstart, results summary
├── LICENSE
├── environment.yml
├── config/
│   ├── schema.yaml               # GDB schema (feature datasets, FCs, fields, domains, relationships)
│   ├── sources.yaml              # data source registry (id, url, vintage, crs, notes)
│   ├── screening.yaml            # Phase A thresholds
│   ├── network.yaml              # travel modes, speeds, restrictions
│   ├── criteria.yaml             # criteria definitions
│   └── weights.json              # scenarios and weights
├── toolbox/
│   ├── LocationIntelligence.pyt  # Python toolbox
│   ├── LocationIntelligence.pyt.xml
│   └── models/                   # ModelBuilder .tbx with visual models + exported diagrams
├── src/
│   ├── li/                       # importable package used by the toolbox
│   │   ├── __init__.py
│   │   ├── gdb.py                # schema build, domains, relationships
│   │   ├── etl.py                # download, reproject, standardize, load
│   │   ├── qaqc.py
│   │   ├── screening.py
│   │   ├── network.py            # service areas, OD matrices (batched)
│   │   ├── workforce.py
│   │   ├── criteria.py
│   │   ├── scoring.py            # normalization, weighting, ranking
│   │   ├── sensitivity.py
│   │   ├── export.py             # profiles, map-series index, CSV/XLSX
│   │   └── logging_utils.py
│   └── run_pipeline.py           # CLI: python run_pipeline.py --scenario Balanced --steps all
├── tests/
│   ├── test_scoring.py
│   ├── test_screening.py
│   └── fixtures/
├── notebooks/
│   ├── 01_data_exploration.ipynb
│   ├── 02_results_review.ipynb
│   └── 03_sensitivity_plots.ipynb
├── docs/
│   ├── ERD.png / ERD.drawio
│   ├── DataDictionary.md
│   ├── GDB_DesignRationale.md
│   ├── Methodology_Report.pdf
│   └── figures/
├── data/
│   ├── raw/                      # gitignored; downloaded sources
│   └── gdb/                      # gitignored; DFW_DSG_SiteSelection.gdb
└── outputs/
    ├── maps/                     # PNG/PDF static maps
    ├── map_series/               # multipage PDFs
    ├── tables/                   # CSV/XLSX
    └── backups/
```

### 6.3 Python toolbox `LocationIntelligence.pyt` — tool specifications

Each tool: validates parameters, logs to `outputs/logs/<run_id>.log`, writes/updates `ScoreRuns`, and is idempotent for a given `run_id`.

| # | Tool | Parameters (type) | Reads | Writes | Notes |
|---|---|---|---|---|---|
| 1 | `BuildGeodatabaseSchema` | `schema_yaml` (File), `out_gdb` (Workspace), `crs` (Spatial Reference), `overwrite` (Bool) | config | GDB, feature datasets, FCs, fields, domains, subtypes, relationship classes, topology, attribute rules | Creates empty schema exactly per Section 4 |
| 2 | `IngestAndStandardize` | `sources_yaml` (File), `gdb` (Workspace), `source_ids` (Multi-value String), `download` (Bool) | raw files/APIs | raw + standardized FCs, `DataSourceRegistry` rows | Handles shapefile, GeoJSON, GPKG, CSV+lat/lon, Census API JSON, LODES CSV.gz; reprojects; maps fields per `sources.yaml` field map |
| 3 | `RunQAQC` | `gdb`, `layers` (Multi-value), `run_id` | FCs | `QAQC_Log` | Checks: null geometry, invalid geometry (repair option), duplicates on key, schema conformance vs. `schema.yaml`, CRS match, extent within study buffer, domain violations, null-rate by required field, parcel topology errors |
| 4 | `BuildNetworkDataset` | `roads_fc`, `network_yaml`, `out_nd` | `Roads` | `RoadNetwork_ND` | Builds attributes, restrictions, travel modes; builds ND |
| 5 | `ScreenCandidateSites` | `gdb`, `screening_yaml`, `run_id` | Parcels, Zoning, env layers, CCNs, Interchanges, ND | `ParcelAssemblages`, `CandidateSites` | Records `screen_reason`; emits summary counts |
| 6 | `BuildServiceAreas` | `gdb`, `run_id`, `mode` (Driving/Truck), `breaks` (List), `batch_size` (Int) | CandidateSites, ND | `ServiceAreas_*` | Batches facilities (default 50) to control memory; supports resume |
| 7 | `BuildODMatrices` | `gdb`, `run_id`, `target` (Stores/Interchanges/Intermodal), `mode`, `cutoff_min` | CandidateSites, targets, ND | `OD_Cand_to_*` | Uses OD Cost Matrix solver; for Stores, computes served set by 600-min cutoff and writes `StoreServiceSet` |
| 8 | `ComputeWorkforceMetrics` | `gdb`, `run_id` | ServiceAreas_Driving, BlockGroups_Centroids, LODES | criterion table (C01–C03 raw) | Centroid-in-polygon aggregation; documents method |
| 9 | `ComputeCriteriaScores` | `gdb`, `run_id`, `criteria_yaml` | all inputs | `SiteScores` (raw and normalized) | Winsorize + min–max; stores parameters |
| 10 | `WeightedSuitability` | `gdb`, `run_id`, `weights_json`, `scenario` | SiteScores | composite, rank, percentile, score_class; `Shortlist` | One scenario per invocation; `--all` in CLI |
| 11 | `SensitivityRunner` | `gdb`, `run_id`, `scenario`, `oat_pct` (default 25), `mc_draws` (default 1000), `alpha_scale` (default 50), `seed` | SiteScores | `SensitivityResults`, plots | Deterministic with seed |
| 12 | `ExportSiteProfiles` | `gdb`, `run_id`, `scenario`, `top_n` (5), `out_dir` | Shortlist, SiteScores, OD tables | profile CSV/XLSX, map-series index layer with dynamic-text fields, JSON for dashboard | |
| 13 | `PublishToAGOL` (optional) | `gdb`, `layers`, `portal`, `folder` | Results | hosted feature layers | Uses `arcpy.sharing`; credentials via environment variables, never in code |

### 6.4 ModelBuilder deliverable

Build two visual models in `toolbox/models/LocationIntelligence_Models.tbx` that mirror the core chain, for stakeholders who prefer visual workflows and for the portfolio:
- `M1_ScreenAndServiceAreas`: Parcels → Select/Dissolve → Screen → Service Areas.
- `M2_ScoreAndRank`: Criteria join → Field calculations (normalization) → Weighted sum → Sort/Rank → Shortlist.
Export each model diagram to `docs/figures/model_M1.png`, `model_M2.png`.

### 6.5 Engineering standards

- Config-driven: no hard-coded paths, thresholds, or weights in code.
- Logging: Python `logging` to file and ArcGIS messages; every run has a `run_id` = `YYYYMMDD_HHMM_<scenario>` and the git commit hash stored in `ScoreRuns`.
- Tests: unit tests for normalization, weighting, ranking, winsorization, and screening rules using small fixtures; run `pytest` in CI (GitHub Actions on push, non-arcpy tests only).
- Performance: batch service-area and OD runs; use `arcpy.da` cursors; `multiprocessing` for non-arcpy ETL steps.
- Reproducibility: `run_pipeline.py --scenario Balanced --steps all` reproduces results from raw data; README documents expected runtime.
- Secrets: none in the repo; AGOL credentials via environment variables.

---

## 7. Visualization deliverables

### 7.1 Cartographic standards

- Page sizes: Letter (8.5 × 11 in) portrait for map series; Tabloid (11 × 17 in) landscape for overview maps; 1920 × 1080 px PNG exports for web.
- Consistent layout template (`layouts/LI_Template.pagx`): title, subtitle, legend, scale bar, north arrow, data-source and vintage credits, project label, page number.
- Basemap: Esri Light Gray Canvas or Human Geography (muted) for analytical maps; Esri Topographic for site profiles.
- Color: sequential palette for scores (e.g., viridis-style 5-class), diverging palette for rank change in sensitivity maps; consistent class breaks across scenarios.
- Fonts: one sans-serif family throughout. Minimum 7 pt label size in print.
- Symbology of the recommended site: distinct outline (e.g., black dashed) on every results map.

### 7.2 Static maps (PDF + PNG, `outputs/maps/`)

| # | Map | Content |
|---|---|---|
| M01 | Study area and market context | MSA counties, major highways, intermodal terminals, airports, DICK'S stores (served set) |
| M02 | Store-service network | Served stores with 4/6/8/10-hour truck isochrones from the MSA centroid |
| M03 | Candidate screening results | All screened polygons by `screen_status`; inset of fail reasons summary |
| M04 | Labor pool (C01) | Block-group transport/material-moving workers; 30-min labor shed of top candidates |
| M05 | Labor availability (C02) | Unemployment rate by block group |
| M06 | Commute flows (C03) | LODES OD flow lines into top-candidate tracts |
| M07 | Highway access (C04) | Interchanges; truck drive-time surface/contours |
| M08 | Store-network access (C05) | Candidates colored by mean truck minutes to served stores |
| M09 | Intermodal access (C06) | Terminals and truck drive-time bands |
| M10 | Flood and wetland constraints (C09) | NFHL SFHA, floodway, NWI |
| M11 | Land value per acre (C10) | Parcels/candidates choropleth |
| M12 | Industrial cluster (C11) | Industrial building footprint density (kernel or 3-mile sum) |
| M13 | Composite suitability — Balanced | Candidates by composite score class; top 5 labeled |
| M14 | Composite suitability — LaborFirst | as M13 |
| M15 | Composite suitability — AccessFirst | as M13 |
| M16 | Rank stability (Monte Carlo) | Candidates by `top10_freq` |
| M17 | Shortlist overview | Top 5 with 30-min labor sheds; recommended site highlighted |
| M18 | Recommended site | Site at 1:24,000 with labor shed, interchange, intermodal, and store-network reach insets |

### 7.3 Map series (multipage PDFs, `outputs/map_series/`)

- **Criteria Map Series** (`MS01_Criteria.pdf`): one page per criterion C01–C11, identical layout, driven by a criteria index table; page title, criterion description, direction, weight per scenario in a dynamic-text block.
- **Site Profile Map Series** (`MS02_SiteProfiles.pdf`): one page per shortlisted site (top 5), index layer = `Shortlist`; page contains: locator inset, site map at 1:24,000, 30-min labor shed inset, dynamic text fields (acres, zoning, composite, rank, per-criterion scores, labor pool, unemployment rate, minutes to interchange/intermodal, mean minutes to stores, SFHA %, land value/acre), a bar chart image of per-criterion scores generated by `ExportSiteProfiles`.
- **County Atlas Series** (`MS03_CountyAtlas.pdf`, optional): one page per county showing Pass candidates and scores.

### 7.4 ArcGIS Dashboard

Publish results as hosted feature layers (Web Mercator) and build one dashboard, `DICK'S DFW Regional DC — Site Selection Explorer`:

- **Header:** title, scenario selector (category selector on `scenario`).
- **Map:** candidates symbolized by `score_class`; recommended site outlined; layer toggles for service areas and stores.
- **List:** candidates sorted by rank; selecting a candidate filters all widgets and zooms the map.
- **Indicators:** composite score, rank, labor pool (30 min), unemployment rate, minutes to interchange, mean minutes to stores, SFHA %, land value/acre.
- **Charts:** serial chart of top 10 by composite; stacked bar of weighted criterion contributions for the selected candidate; gauge for `top10_freq`.
- **Details panel:** site profile text.
- Mobile layout included.

Optional: an ArcGIS Experience Builder app wrapping the dashboard and StoryMap with a single navigation.

---

## 8. Communication — ArcGIS StoryMap

Title: **"Where Should DICK'S Build? Site Selection for a Regional Distribution Center in Dallas–Fort Worth"**

Audience: brokers, corporate real-estate executives, economic-development staff. Plain language; every technical term explained in one line the first time it appears.

| # | Section | Content / media |
|---|---|---|
| 1 | Cover | Hero map of DFW with the recommended site; one-sentence hook |
| 2 | The requirement | Facility size, acreage, jobs, store network, and stated priorities |
| 3 | The question | The analytical question, framed for a non-technical reader |
| 4 | The DFW industrial market | Context: MSA, corridors, intermodal, DFW as a top U.S. industrial market (M01) |
| 5 | Who the DC serves | Store-network map (M02); served-store count; one-day truck reach |
| 6 | Screening the market | Sidecar: what was filtered and why (M03), candidate count |
| 7 | What matters | Criteria explained; swipe maps for labor (M04) vs. store access (M08); weight scenarios explained |
| 8 | The labor story | Labor-shed map, commute flows (M06); why workforce matters for a 300-job DC |
| 9 | Reach and access | Drive-time visuals (M07, M09) |
| 10 | Results | Composite maps by scenario (M13–M15); embedded dashboard |
| 11 | How stable is the answer? | Sensitivity figures (rank ranges, top-5 frequency) |
| 12 | The shortlist | Site-profile cards for top 5 |
| 13 | The recommendation | Recommended site and alternate, with rationale and due-diligence items |
| 14 | Method, data, and code | Links to methodology PDF, GitHub repo, data sources; author bio and contact |

---

## 9. Methodology report (PDF)

File: `docs/Methodology_Report.pdf` (source in Markdown or Word; 20–35 pages plus appendices). Structure:

1. Executive summary (1 page; key numbers and the recommendation)
2. Client requirement and business question
3. Study area and reference geography
4. Data sources and preparation (table from Section 3; vintage discussion)
5. Geodatabase design summary (ERD; link to standalone write-up)
6. Candidate screening (rules, parameters, counts, fail-reason table)
7. Network analysis (network build, travel modes, service-area and OD parameters)
8. Workforce analytics method (ACS/LODES aggregation, definitions)
9. Criteria and scoring (definitions, normalization, formulas)
10. Weighting scenarios and rationale
11. Results by scenario (maps, top-10 tables)
12. Sensitivity analysis (OAT, Monte Carlo, thresholds)
13. Shortlist and site profiles
14. Recommendation and due-diligence considerations
15. Assumptions, limitations, and known gaps
16. Reproducibility (repo, environment, run instructions, runtimes)
17. References
Appendices: A — Data source registry; B — Data dictionary; C — Weight tables and sensitivity outputs; D — QA/QC log summary; E — Map gallery; F — Toolbox parameter reference.

---

## 10. QA/QC plan

| Stage | Check | Threshold / expectation |
|---|---|---|
| Ingest | CRS = analysis CRS | 100% |
| Ingest | Invalid/null geometry | 0 after repair |
| Ingest | Duplicate keys (`parcel_id`, `geoid`, `store_id`) | 0 |
| Ingest | Extent within study buffer | 100% |
| Parcels | Topology errors (overlap/gap) | Report count; resolve overlaps > 0.1 acre |
| Stores | Geocode score | ≥ 90; manual review below |
| Network | Connectivity: sample 100 random OD pairs solve | 100% solved |
| Screening | Fail reasons recorded for every evaluated polygon | 100% |
| Criteria | No nulls in `cXX_raw` for Pass candidates | 0 nulls |
| Scoring | Weights sum to 1.00 per scenario | exact |
| Scoring | Composite in [0,100]; ranks unique | 100% |
| Sensitivity | Seed recorded; results reproducible | Re-run matches |
| Maps | Every map has title, legend, scale, sources | Checklist |
| Dashboard | All widgets respond to selection; mobile layout works | Manual test |
| StoryMap | All links resolve; no draft layers | Manual test |

Peer review: one independent reviewer walks the pipeline from README and reproduces the Balanced run before the project is marked complete.

---

## 11. Timeline and milestones (8 weeks, part-time)

| Week | Milestone | Exit criteria |
|---|---|---|
| 1 | Data acquisition; `sources.yaml` complete; stores compiled | All S01–S22 downloaded; registry rows written |
| 2 | Geodatabase schema built via tool; ERD and data dictionary v1 | `BuildGeodatabaseSchema` runs clean; ERD reviewed |
| 3 | ETL and QA/QC tools; all layers loaded | `RunQAQC` passes thresholds |
| 4 | Network dataset; screening | Candidate pool 60–200 |
| 5 | Service areas, OD matrices, workforce metrics, scoring, three scenarios, sensitivity | `SiteScores`, `SensitivityResults` populated; draft shortlist |
| 6 | Static maps M01–M18; map series MS01–MS02 | Exports in `outputs/`; cartographic checklist passed |
| 7 | AGOL publish; dashboard; StoryMap | Dashboard and StoryMap shared (unlisted) for review |
| 8 | Methodology report; README; standalone GDB write-up; portfolio pages; peer reproduction | Acceptance checklist (Section 13) complete |

---

## 12. Deliverables checklist

**A. Flagship project**
- [ ] GitHub repository (public) per Section 6.2, with README results summary
- [ ] `LocationIntelligence.pyt` with tools 1–12 (13 optional)
- [ ] ModelBuilder toolbox with M1, M2 and exported diagrams
- [ ] `DFW_DSG_SiteSelection.gdb` (delivered as zipped download link, not in git)
- [ ] Static maps M01–M18 (PDF + PNG)
- [ ] Map series MS01, MS02 (MS03 optional)
- [ ] ArcGIS Dashboard (public link)
- [ ] ArcGIS StoryMap (public link)
- [ ] Methodology report PDF
- [ ] Results tables (CSV/XLSX): candidates, scores by scenario, sensitivity, shortlist
- [ ] Portfolio page: summary, hero image, links, 3–5 key findings, recommended site

**B. Standalone geodatabase project**
- [ ] `docs/GDB_DesignRationale.md` (portfolio write-up)
- [ ] ERD (PNG + editable)
- [ ] Data dictionary
- [ ] `schema.yaml` and `BuildGeodatabaseSchema` tool (linked from the flagship repo)
- [ ] Short screen recording/GIF showing domains, subtypes, relationship class navigation, topology validation
- [ ] Portfolio page: design goals, decisions, trade-offs, maintenance strategy
- [ ] Optional: PostGIS DDL and loader

---

## 13. Acceptance criteria

The project is complete when all of the following are true:

1. `python run_pipeline.py --scenario Balanced --steps all` executes end-to-end from raw data on a clean clone (with data downloaded) and reproduces `SiteScores` and `Shortlist` for the Balanced scenario.
2. All three scenarios and the sensitivity analysis are populated in the GDB with a recorded `run_id` and git commit.
3. A top-five shortlist, a recommended site, and an alternate are documented with rationale for the Balanced scenario, with cross-scenario ranks shown.
4. All maps, map series, dashboard, StoryMap, and report pass the QA/QC checklist in Section 10.
5. The standalone geodatabase write-up, ERD, and data dictionary exist and match the delivered GDB schema exactly (verified by a schema diff script).
6. One independent reviewer has reproduced the Balanced run from the README.

---

## 14. Assumptions, risks, and mitigations

| Item | Risk | Mitigation |
|---|---|---|
| Parcel data | County parcel schemas differ; zoning not statewide | Field-map per county in `sources.yaml`; treat zoning as city-by-city; where zoning is unavailable, use parcel land-use code plus NLCD as proxy and flag |
| Store data | Store list changes over time | Snapshot with date; record count; re-run `BuildODMatrices` if updated |
| Network build | TxDOT RHiNo lacks truck restrictions in some areas | Apply functional-class rules; validate 20 sample routes against AGOL routing |
| Assemblage logic | Owner-based dissolves can create unrealistic assemblages | Cap at 6 parcels; require contiguity; manual review of assemblages > 300 acres |
| LODES aggregation | Tract-level, may be coarse for a site | Use adjacent-tract union; document |
| ArcGIS credits | AGOL routing consumes credits | Use local network dataset for all production runs |
| Non-modeled factors | Incentives, entitlement timing, utility capacity, build-to-suit availability | Listed as due-diligence items in the recommendation, not scored |
| Time | 8 weeks part-time is tight | Prioritize: pipeline + shortlist first; MS03 and Experience Builder optional |

---

## Appendix A — Client requirement source facts

- Announced 13 Aug 2024 (DICK'S Sporting Goods press release; Hillwood newsroom; Dallas Innovates): 800,000 SF regional distribution center in the Fort Worth area; ~300 full-time jobs over ten years; serves 100+ stores across several states; sixth DC in the network (others: Atlanta GA; Conklin NY; Goodyear AZ; Plainfield IN; Smithton PA).
- Stated selection drivers: business-friendly environment, qualified and reliable workforce, proximity to existing and expanding Texas store footprint.
- Market context: DFW ranked the top U.S. market for industrial space under construction at the start of 2026 (Fort Worth Report, Apr 2026).

## Appendix B — Parameter defaults (`config/screening.yaml`)

```yaml
min_acres: 80
max_parcels_per_assemblage: 6
allow_agricultural_near_industrial_miles: 1.0
max_sfha_pct: 20
max_floodway_pct: 0
max_wetland_pct: 10
max_mean_slope_pct: 5
max_developed_pct: 30
require_water_ccn: true
require_sewer_ccn_or_within_miles: 1.0
max_truck_min_to_interchange: 15
```

## Appendix C — Weights (`config/weights.json`)

```json
{
  "Balanced":   {"C01":0.20,"C02":0.05,"C03":0.10,"C04":0.12,"C05":0.18,"C06":0.08,"C07":0.05,"C08":0.03,"C09":0.05,"C10":0.07,"C11":0.07},
  "LaborFirst": {"C01":0.30,"C02":0.08,"C03":0.15,"C04":0.08,"C05":0.12,"C06":0.05,"C07":0.04,"C08":0.02,"C09":0.04,"C10":0.06,"C11":0.06},
  "AccessFirst":{"C01":0.12,"C02":0.03,"C03":0.05,"C04":0.18,"C05":0.28,"C06":0.12,"C07":0.04,"C08":0.02,"C09":0.04,"C10":0.05,"C11":0.07}
}
```

*End of document.*
