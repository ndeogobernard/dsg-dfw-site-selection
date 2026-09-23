# Reconnaissance findings

**Date:** 2026-09-19 · **Commit:** see `docs/SESSION_LOG.md`
**Purpose:** establish what the source data actually contains *before* building
`IngestAndStandardize` or `RunQAQC`, so `config/schema.yaml` and the pipeline are designed
against reality rather than assumption.

No ETL was built in this pass. Every number below came from a live query against the named
service or API on the date above.

**Confidence labels used throughout:**

| Label | Meaning |
|---|---|
| **VERIFIED** | Queried the live endpoint directly and read the result. |
| **INDICATIVE** | Found via search; publisher and contents not individually confirmed. |
| **UNRESOLVED** | Could not be determined in this pass; blocked, and on the action list. |

---

## 1. Tarrant County parcels — VERIFIED

### 1.1 The authoritative layer

| | |
|---|---|
| Service | `https://mapit.tarrantcounty.com/arcgis/rest/services/Dynamic/TADParcels/MapServer/0` |
| Publisher | Tarrant County (Tarrant Appraisal District data) |
| Features | **758,633** |
| Geometry | Polygon |
| Spatial reference | **EPSG:3785** (Web Mercator) |
| Fields | 56 |
| `maxRecordCount` | 1,000 — paging is mandatory |

> **Trap worth recording.** ArcGIS Hub surfaces
> `Tax/TCProperty/MapServer/0` as "Tarrant County Parcel Property" with an *identical 56-field
> schema*. It holds **110 features**, every one owned by `TARRANT COUNTY OF` — it is
> county-owned property only, not the parcel universe. Schema alone does not tell you which
> layer you have; check the feature count. `TCProperty` also publishes in **EPSG:2276** while
> `TADParcels` is **EPSG:3785**, so the two are not interchangeable.

### 1.2 Field inventory (56 fields)

Grouped by usefulness to this project.

**Identity and location**
`TAXPIN` (30), `ACCOUNT` (8), `GISLINK` (25), `SITUS_ADDR` (30), `CITY` (50), `STATE` (2),
`ZIPCODE` (10), `STREET_NO`, `PREDIR`, `STREET_NAM` (25), `STREET_TYP` (5), `POSTDIR`,
`TAD_MAP` (9), `MAPSCO` (4), `SubdivisionName` (50), `LEGAL_1` (128), `LEGAL_2..4` (32 each)

**Ownership**
`OWNER_NAME` (30), `OWNER_ADDR` (30), `OWNER_CITY` (30), `OWNER_ZIP` (9), `OWNER_ZIP_` (4)

**Size — needed for screening and C07**
`LAND_ACRES` (Double), `LAND_SQFT` (Double)

**Value — needed for C10**
`LAND_VALUE`, `IMPR_VALUE`, `TOTAL_VALU`, `APPRAISEDV` (all Double), `APPRAISAL_` (Date)

**Residential structure detail — not useful here**
`BEDROOMS`, `BATHROOMS`, `GARAGE_CAP`, `LIVING_ARE`, `YEAR_BUILT`, `SW_POOL`, `CENTRAL_HE`,
`CENTRAL_AI`

**Transaction**
`DEED_DATE`, `DEED_BOOK` (7), `DEED_PAGE` (7), `INSTRUMENT_NO` (20)

**Other**
`SCHOOL` (50), `EXEMPTION_` (3), `SPEC1..SPEC5` (50 each), `PARCELTYPE` (Double),
`DESCR` (25), `ADDENDUM_T`, `ADDENDUM`, `SB247_Flag` (1)

### 1.3 Population rates — server-side counts over all 758,633 parcels

| Condition | Count | Share |
|---|---:|---:|
| All parcels | 758,633 | 100% |
| `LAND_VALUE > 0` | **693,826** | **91.5%** |
| `LAND_VALUE = 0` | 64,806 | 8.5% |
| `LAND_VALUE IS NULL` | **1** | ~0% |
| `LAND_ACRES > 0` | 699,091 | 92.2% |
| `LAND_ACRES IS NULL` | 23 | ~0% |
| `TOTAL_VALU > 0` | 742,055 | 97.8% |

From a 2,000-record sample: `IMPR_VALUE` is zero on 42.2% and `YEAR_BUILT` is zero on 40.9% —
consistent with unimproved land, and exactly the population this study cares about.

The 8.5% with `LAND_VALUE = 0` are tax-exempt, right-of-way, and government parcels. They are
not a data defect; they should be excluded from C10 normalization rather than treated as
zero-cost land, which would otherwise make them score as the cheapest sites available.

### 1.4 Candidate-pool preview — Tarrant County only, acreage filter alone

| Threshold | Parcels |
|---|---:|
| `LAND_ACRES >= 70` | 1,001 |
| `LAND_ACRES >= 80` | **884** |
| `LAND_ACRES >= 90` | 804 |
| `LAND_ACRES >= 100` | 732 |
| `LAND_ACRES >= 150` | 532 |

**This reframes the screening design.** Scope §5.1 expects 60–200 Pass candidates across all
11 counties, and provides an auto-relaxation ladder in case fewer than 40 survive. Tarrant
*alone* yields 884 parcels at the 80-acre threshold before any other filter, and before
assemblages are even constructed. Across 11 counties the pre-filter pool will plausibly be
several thousand.

The consequence: the acreage threshold is **not** the binding constraint. Zoning, flood,
utility service, and interchange drive time do the real screening work. The
`candidate_band.if_below_min` branch in `config/screening.yaml` (relax to 70 acres) is very
unlikely to fire; `if_above_max` (tighten interchange time to 10 minutes) is the probable path.
Worth stating in the methodology report rather than presenting the band as if it cut both ways.

### 1.5 No zoning, no land use — VERIFIED

**TAD parcels carry no zoning field and no land-use code field.** A field-name scan for
`zon*`, `land_use*`, `luc*` returns **nothing**.

`DESCR` and `PARCELTYPE` are the only candidates for a use proxy, and a `returnDistinctValues`
query against both returned zero rows, so their value domains are still unknown — see
§5 Open items.

This directly contradicts an assumption baked into `config/schema.yaml` and `config/sources.yaml`:

- `Parcels.zoning_code` / `zoning_class` cannot be populated from the parcel source. They can
  only come from a spatial join to municipal zoning.
- `Parcels.land_use_code` / `land_use_class` likewise have no source in Tarrant. Since
  `land_use_class` drives the `Parcels` **subtypes** (§4.5), the subtype assignment has no
  input either, and every parcel would default to `Vacant` (code 3).
- The `field_map._default` block in `config/sources.yaml` (`PROP_ID`, `LAND_STATE`, `LAND_VAL`,
  `MKT_VAL`, `YR_BUILT`) was a guess and is **wrong for Tarrant**. Correct mapping below.

### 1.6 Corrected field map for Tarrant

```yaml
parcel_id:           TAXPIN        # or ACCOUNT; TAXPIN is the GIS key, ACCOUNT the tax key
owner_name:          OWNER_NAME
situs_addr:          SITUS_ADDR
acres:               LAND_ACRES    # supplied, not derived from geometry
appraised_land_val:  LAND_VALUE
appraised_total_val: TOTAL_VALU
year_built:          YEAR_BUILT
land_use_code:       null          # NOT PUBLISHED
zoning_code:         null          # NOT PUBLISHED - spatial join required
```

Note `LAND_ACRES` is published. The `calc_Parcel_Acres` attribute rule derives `acres` from
`Shape_Area` instead, so the two will disagree wherever the CAD acreage and the digitised
geometry differ. Keeping the published value as a separate field and reconciling the two is a
QA/QC check worth adding.

---

## 2. Municipal zoning — PARTIALLY VERIFIED

### 2.1 Dallas — VERIFIED, and more complex than the schema assumes

`https://services2.arcgis.com/rwnOSbfKSwyTBcwN/arcgis/rest/services/Dallas_Zoning/FeatureServer`
— published by **City of Dallas GIS Services**. **20 layers**, not one:

| Layer | Name | Features | Relevant fields |
|---|---|---:|---|
| 15 | **Base_Zoning** | **3,827** | `ZONE_DIST`, `LONG_ZONE_DIST`, `DISTRICTUSE`, `PD_NUM`, `CD_NUM` |
| 9 | PD_Subdistricts | 1,280 | `ZONE_DIST`, `LONG_ZONE_DIST`, `DISTRICTUSE`, `SHAPE_ACREAGE` |
| 4 | SUP (specific use permits) | 1,338 | `SPECIFICUSE`, `EXPIRES`, `STATUS` |
| 11 | PDS_Subdistricts | 112 | `LONG_ZONE_DIST`, `DISTRICTUSE` |
| 8 | CD_Subdistricts | 25 | `LONG_ZONE_DIST`, `DISTRICTUSE` |
| 0–3, 5–7, 10, 12–14, 16–19 | overlays (deed restriction, historic, dry, height, shopfront, pedestrian, demolition delay, …) | 0–975 each | assorted |

**Base zoning alone is not the zoning.** A Planned Development parcel carries `PD_NUM` in
`Base_Zoning` and its actual permitted use in `PD_Subdistricts`. Industrial land inside a PD —
common for large tracts, which is exactly what this study is looking for — would be
misclassified by reading `Base_Zoning` on its own. The ingest must union base zoning with the
PD/PDS/CD subdistrict layers and prefer the subdistrict where one applies.

This is one city. There are ~180 incorporated places in the MSA.

### 2.2 Coverage across the 11 counties — INDICATIVE, with known false positives

A Hub search was run for 30 jurisdictions. **The results cannot be trusted as an inventory**
and are recorded here only as leads. The publisher-name heuristic matched same-named cities in
other states:

| Hit | Actually |
|---|---|
| "Arlington Zoning" | City of Arlington, **WA** |
| "Grand Blanc Zoning Districts" | Grand Blanc Township, **MI** |
| "Lancaster Zoning Map" | City of Lancaster, **OH** |
| "Decatur Zoning" | Maps of Decatur, **GA** |
| "Zoning for Greenville" | Greenville, **NC** |
| "Mesquite Zoning" | Clark County, **NV** |
| "Town of Frisco Zoning" | likely Frisco, **CO** |
| Denton County "Local Option Zoning Map" | liquor local-option, **not land use** |

Leads that look genuinely Texan and are worth checking first, by publisher name:

| County | Jurisdiction | Publisher as shown | Confidence |
|---|---|---|---|
| Dallas | **Dallas** | City of Dallas GIS Services | **VERIFIED** |
| Dallas | Irving | City of Irving | likely |
| Tarrant | Mansfield | MansfieldGIS / City of Mansfield Texas | likely |
| Denton | Lewisville | City of Lewisville, Texas | likely |
| Denton | Flower Mound | Town of Flower Mound GIS | likely |
| Collin | McKinney | City of McKinney | likely |
| Rockwall | Rockwall | City of Rockwall, TX Maps | likely |
| Ellis | Waxahachie | City of Waxahachie (StoryMap, not a service) | weak |
| Kaufman | Forney | jhiggins_forney (personal account) | weak |
| Tarrant | **Fort Worth** | `rsimpsonirr` — **not the city** | **none found** |

**Fort Worth is the single most important gap.** It is the largest city in the study area, the
one the client named, and no authoritative open zoning service was located for it in this pass.

Not located at all: Haslet, Midlothian, Ennis, Cleburne, Alvarado, Terrell, Rhome — several of
which sit on exactly the kind of cheap highway-adjacent land this study is looking for.

**Unincorporated county land has no zoning by law in Texas.** Counties lack general zoning
authority. A material share of 80-acre-plus parcels near interchanges will be unincorporated,
so for those parcels the zoning filter is not merely missing data — there is nothing to find.

---

## 3. FEMA NFHL — VERIFIED

`https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer` — 32 layers.
**Layer 28 = Flood Hazard Zones** (polygon).

Field names confirmed live:

| Field | Type | Len | Note |
|---|---|---|---|
| `FLD_ZONE` | String | 17 | A, AE, AH, AO, X, VE, D, … |
| `ZONE_SUBTY` | String | **76** | **where FLOODWAY lives** |
| `SFHA_TF` | String | **1** | `"T"` / `"F"` — **text, not boolean** |
| `STATIC_BFE` | Double | | base flood elevation |
| `DEPTH`, `VELOCITY` | Double | | with `LEN_UNIT`, `VEL_UNIT` |
| `DFIRM_ID` | String | 6 | study id |
| `DUAL_ZONE` | String | 1 | |
| `SOURCE_CIT` | String | 21 | |

**Two schema corrections follow from this:**

1. **There is no floodway field.** `FloodZones_NFHL.floodway_flag` must be derived from
   `ZONE_SUBTY` containing `FLOODWAY` — a substring test on a 76-character free-text field, not
   a lookup. Scope §5.1 makes `floodway_flag = 0` a hard filter, so getting this derivation
   wrong silently passes floodway land.
2. **`SFHA_TF` is `"T"`/`"F"` text**, while `FloodZones_NFHL.sfha_flag` is SHORT. Needs explicit
   conversion on ingest; a naive cast yields nulls.

`config/schema.yaml` sizes `fld_zone` at TEXT(20) — adequate for the 17-char source. No
`zone_subty` field exists in the schema and one is needed.

---

## 4. Census ACS and LEHD LODES

### 4.1 LODES 8 — VERIFIED, schema matches exactly

Read live headers from `https://lehd.ces.census.gov/data/lodes/LODES8/tx/`.

| File | Columns | Confirmed present |
|---|---:|---|
| `tx_wac_S000_JT00_2022.csv.gz` | 53 | `w_geocode`, `C000`, `CA01–03`, `CE01–03`, `CNS01–20` incl. **`CNS08`** |
| `tx_rac_S000_JT00_2022.csv.gz` | 43 | `h_geocode`, `C000`, **`CNS08`** |
| `tx_od_main_JT00_2022.csv.gz` | 13 | `w_geocode`, `h_geocode`, **`S000`**, `SA01–03`, `SE01–03`, `SI01–03`, `createdate` |

Every column named in `config/schema.yaml` for `LODES_OD_Flows`, `Tracts_LODES_WAC`, and
`Tracts_LODES_RAC` exists. **No changes needed.** Latest year present is **2022**.

Note the geocode fields are **block**-level (15-digit), so aggregation to tract is on ingest, as
`config/sources.yaml` already states.

### 4.2 ACS — BLOCKED, and a correction to C01

**The Census API now requires a key.** Every data query returned HTTP 200 with an HTML page
titled *"Missing Key"*. This is a change from the historical behaviour where small volumes of
requests worked unauthenticated. `config/sources.yaml` already declares
`api_key_env: CENSUS_API_KEY`; it is now mandatory, not optional.

Free, instant, no cost: <https://api.census.gov/data/key_signup.html>

Metadata endpoints still work without a key, which confirmed the following.

**C24010 does not have a "transport and material moving" line.** It splits the category three
ways, for each sex:

| Variable | Label |
|---|---|
| `C24010_034E` | Male: Production, transportation, and material moving occupations *(parent)* |
| `C24010_035E` | Male: **Production** occupations |
| `C24010_036E` | Male: **Transportation** occupations |
| `C24010_037E` | Male: **Material moving** occupations |
| `C24010_070E` | Female: Production, transportation, and material moving *(parent)* |
| `C24010_071E` | Female: **Production** occupations |
| `C24010_072E` | Female: **Transportation** occupations |
| `C24010_073E` | Female: **Material moving** occupations |

So criterion **C01** (`occ_transp_matmov`) is:

```
C24010_036E + C24010_037E + C24010_072E + C24010_073E
```

and `occ_prod` is `C24010_035E + C24010_071E`. Using the parent lines 034/070 would fold
**production** workers into the warehouse labour pool and inflate C01 substantially — factory
workers are not distribution-centre workers. The schema's separation of `occ_transp_matmov`
from `occ_prod` is correct; the variable mapping just has to respect it.

ACS 5-year vintages currently offered: 2019–**2024**.

**UNRESOLVED:** whether C24010 is published at **block group**. ACS 5-year restricts block-group
geography to a subset of tables, and this could not be tested without a key. C01, C02 and the
whole 30-minute labour-shed method in §5.3 depend on block-group estimates.
`config/sources.yaml` already anticipates a tract-level apportionment fallback; whether that
fallback is needed is the first thing to test once a key exists.

---

## 5. Open items

| # | Item | Blocks | Owner |
|---|---|---|---|
| 1 | Obtain a Census API key and set `CENSUS_API_KEY` | C01, C02, all ACS ingest | **user** |
| 2 | Confirm C24010 availability at block group | C01 method; tract fallback | after #1 |
| 3 | Locate authoritative Fort Worth zoning | D-009, screening | analyst |
| 4 | Verify the 9 "likely" Texas zoning leads are the right jurisdictions | D-009 | analyst |
| 5 | Determine `DESCR` / `PARCELTYPE` value domains on TAD parcels | land-use proxy | analyst |
| 6 | Repeat §1 for the other 10 county CADs | field maps, C10 | analyst |
| 7 | Reconcile published `LAND_ACRES` against geometry-derived acres | QA/QC | analyst |

---

## 6. Schema changes this recon implies

> **STATUS: APPLIED 2026-09-22.** D-008, D-009 and D-013 are all DECIDED and every item
> below is implemented in `config/` and present in the rebuilt geodatabase. See
> `docs/DECISIONS.md` entries **D-008-R**, **D-009-R** and **D-013**.
>
> Items 2 and 3 landed with a change of plan: the `Parcels` subtype moved off
> `land_use_class` entirely (D-013 Q2), and zoning became a scored signal rather than a
> filter (D-013 Q1), so C12 was added and its weight carved out of C11.

Originally recorded as: *not yet applied — they depend on D-008 and D-009 being settled.*

1. `Parcels`: add `acres_published` (DOUBLE) to hold CAD acreage separately from the
   geometry-derived `acres`, and a QA/QC check comparing them.
2. `Parcels`: `land_use_code`, `land_use_class`, `zoning_code`, `zoning_class` have **no source**
   in Tarrant. They must be nullable, populated by spatial join where possible, and the
   `land_use_st` subtype must tolerate being unset.
3. `FloodZones_NFHL`: add `zone_subty` (TEXT 76). Document `floodway_flag` as derived from it by
   substring match, and `sfha_flag` as converted from `"T"`/`"F"`.
4. `config/sources.yaml` S01: replace the guessed `field_map._default` with the verified Tarrant
   map in §1.6, and make each county's map explicit rather than defaulted.
5. `config/sources.yaml` S02: record that zoning is per-city, that base zoning must be unioned
   with PD/CD subdistricts, and that unincorporated land has none by law.
6. `config/criteria.yaml` C01: record the exact C24010 variable arithmetic from §4.2.
7. `config/screening.yaml`: revisit `candidate_band`. Per §1.4 the pool will run high, not low.
