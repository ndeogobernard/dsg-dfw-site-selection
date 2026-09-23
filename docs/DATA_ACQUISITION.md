# Data acquisition playbook

How to obtain every source in scope §3, by hand, from scratch. One section per source
**S01–S23**.

This exists so the project is reproducible by a person, not only by a script. Someone with
ArcGIS Pro, a browser, and this document can rebuild the entire input dataset without running
any of our code. `config/sources.yaml` is the machine-readable twin of this file; when they
disagree, fix both.

## How to read this

| Tag | Meaning |
|---|---|
| **AUTO** | Scripted end to end by `IngestAndStandardize` (tool 2). A stable URL or API exists. |
| **MANUAL** | Hand-fetch. Interactive portal, per-county picking, licence click-through, or no stable endpoint. |
| **MIXED** | Scripted once the target is identified by hand. |
| *pending recon* | Not yet verified against the live source. Do not trust the details until it is. |

**Destination.** Everything lands in `data/raw/<source_id>/`, unmodified, exactly as downloaded.
Never edit a raw download — reprojection, renaming, and field mapping all happen on ingest into
the geodatabase, so the raw file stays a faithful record of what the provider published.

The raw directory is gitignored (scope §6.2). Record provider, vintage, download date, licence,
native CRS, and transformation in `DataSourceRegistry` as you go.

**Analysis CRS is EPSG:6584.** Every source is reprojected on ingest. Record the native CRS and
the datum transformation used — that is a §10 QA check, not bookkeeping.

**Study area:** DFW–Arlington MSA, 11 counties (2023 OMB delineation) — Collin `48085`,
Dallas `48113`, Denton `48121`, Ellis `48139`, Hunt `48231`, Johnson `48251`, Kaufman `48257`,
Parker `48367`, Rockwall `48397`, Tarrant `48439`, Wise `48497`. Clip to the MSA **plus a
15-mile buffer** (§2.1) so drive-time polygons and labour sheds are not truncated at the edge.

---

## S01 · Parcels — **MANUAL** (per county) · *partly verified*

| | |
|---|---|
| Provider | Texas Geographic Information Office (TxGIO, formerly TNRIS); county appraisal districts |
| Portal | <https://data.tnris.org/> · county CAD / county GIS portals |
| Destination | `data/raw/S01/<county>/` |
| Licence | Public domain / open data — confirm per county |
| Vintage | Latest published appraisal year |
| Native CRS | **Varies by county.** Verified: Tarrant `TADParcels` = EPSG:3785 |

**Verified — Tarrant County** (`docs/recon/RECON_findings.md` §1):

1. Open the REST endpoint
   `https://mapit.tarrantcounty.com/arcgis/rest/services/Dynamic/TADParcels/MapServer/0`
2. Confirm the feature count is ~**758,633**. If it returns ~110, you are on the wrong layer —
   `Tax/TCProperty` has an **identical 56-field schema** but holds only county-owned property.
   Schema does not identify the layer; the count does.
3. In ArcGIS Pro: **Add Data → From Path**, paste the URL, then **Data → Export Features** to
   `data/raw/S01/tarrant/`.
4. `maxRecordCount` is **1,000**, so any scripted pull must page. Pro handles this itself.

Fields that matter — `TAXPIN`, `ACCOUNT`, `OWNER_NAME`, `SITUS_ADDR`, `LAND_ACRES`,
`LAND_VALUE`, `TOTAL_VALU`, `YEAR_BUILT`. **There is no zoning or land-use field** (see S02).

### Per-county status — probed 2026-09-22

Only **Tarrant** is cleared for ingest. `IngestAndStandardize` refuses any county whose field
map is not `status: verified`, so the rest cannot be ingested by accident.

| County | Mode | Status | Features | Land value | Acreage | Source |
|---|---|---|---:|---|---|---|
| **Tarrant** | AUTO | **verified** | 758,633 | ✅ inline | ✅ | Tarrant County `TADParcels` |
| **Denton** | AUTO | skeleton | 384,308 | ⚠️ split HS/NHS | ✅ | Denton County GIS `Parcels_FC` |
| **Dallas** | AUTO | skeleton | 695,446 | ❌ **none** | ⚠️ `RecAcs` | City of Dallas `CurrentDcadParcels` |
| Collin | **MANUAL** | not located | — | ? | ? | try <https://www.collincad.org/> |
| Ellis | **MANUAL** | not located | — | ? | ? | try <https://www.elliscad.com/> |
| Hunt | **MANUAL** | not located | — | ? | ? | try <https://www.hunt-cad.org/> |
| Johnson | **MANUAL** | not located | — | ? | ? | try <https://www.johnsoncad.com/> |
| Kaufman | **MANUAL** | not located | — | ? | ? | try <https://www.kaufman-cad.org/> |
| Parker | **MANUAL** | not located | — | ? | ? | try <https://www.parkercad.org/> |
| Rockwall | **MANUAL** | not located | — | ? | ? | try <https://www.rockwallcad.com/> |
| Wise | **MANUAL** | not located | — | ? | ? | try <https://www.wisecad.org/> |

Every portal above returns HTTP 200, but **whether it actually offers a downloadable parcel
layer is unconfirmed** — a URL resolving is not the same as the data being there.

**Denton — AUTO, richest schema found.** 71 fields, and the only county located that publishes
a zoning field (`cad_zoning`) at all. Field-map skeleton is in `sources.yaml`. Two things must
be confirmed before promoting it to `verified`: whether land value is
`landHSValue + landNHSValue`, and whether `legalAcreage` or `effectiveSizeAcres` is the deeded
figure.

> **Dallas — geometry and account number only.** Five fields:
> `OBJECTID, RecAcs, GIS_Acct, Shape__Area, Shape__Length`. **No land value, no owner, no
> address, no year built, no land use, no zoning.** C10 cannot be computed for Dallas from the
> parcel layer alone; a DCAD tabular roll must be joined on `GIS_Acct`. See **D-014** — this is
> the join step D-008 concluded was unnecessary, and that conclusion held only because Tarrant
> happened to be probed first.

**What is needed by hand.** For the eight *not located* counties, someone has to visit the
appraisal district site and determine whether a parcel shapefile or geodatabase is published,
and whether valuations come with it or separately. Until then those counties cannot be ingested
at all. Nothing is needed by hand for Tarrant, Denton, or Dallas geometry — all three are
queryable REST services.

**Writing a new county field map.** Add an entry under `S01 → counties` with `status:
skeleton`, the endpoint, the expected feature count, and a `field_map`. Promote to `verified`
only after reading the live field list. Declare fields the county does not publish under
`unavailable:` so their nulls are a recorded fact. There is deliberately no shared default —
the original guessed default was wrong for Tarrant in every field.

---

## S02 · Zoning — **MANUAL** (per city) · *largely pending recon*

| | |
|---|---|
| Provider | Individual municipalities |
| Portal | Each city's open-data site |
| Destination | `data/raw/S02/<city>/` |
| Licence | Varies by city |

**This is the project's biggest acquisition risk.** There is no regional zoning layer. Parcels
carry no zoning (verified for Tarrant). Coverage is city-by-city, and **unincorporated county
land has no zoning at all** — Texas counties lack general zoning authority, so for those parcels
there is nothing to find, which is a finding rather than a gap.

**Verified — Dallas:**

1. `https://services2.arcgis.com/rwnOSbfKSwyTBcwN/arcgis/rest/services/Dallas_Zoning/FeatureServer`
2. It has **20 layers**, not one. Take at least:
   - layer **15 `Base_Zoning`** (3,827 features) — `ZONE_DIST`, `LONG_ZONE_DIST`, `DISTRICTUSE`
   - layer **9 `PD_Subdistricts`** (1,280) — Planned Development parcels carry only a `PD_NUM`
     in base zoning; their real permitted use lives here
   - layers 8 `CD_Subdistricts`, 11 `PDS_Subdistricts`
3. **Union base zoning with the subdistricts, preferring the subdistrict where one applies.**
   Large industrial tracts — exactly this study's targets — are commonly inside PDs, and reading
   base zoning alone misclassifies them.

**All other jurisdictions — *pending recon*.** No authoritative **Fort Worth** layer has been
located, which is the most important outstanding gap: it is the largest city in the study area
and the one the client named.

> **Do not use ArcGIS Hub search as an inventory.** Verified failure mode: Texas queries returned
> Arlington **WA**, Grand Blanc **MI**, Lancaster **OH**, Decatur **GA**, Greenville **NC**,
> Mesquite **NV**, and a Denton County "Local Option Zoning Map" that is about liquor, not land
> use. Always confirm the publishing organisation is the actual Texas jurisdiction.

Where no usable zoning exists, the parcel is tiered by `zoning_confidence` rather than dropped —
see **D-009**.

---

## S03 · TxDOT Roadway Inventory (RHiNo) — **MANUAL**

| | |
|---|---|
| Provider | Texas Department of Transportation |
| Portal | <https://gis-txdot.opendata.arcgis.com/> |
| Destination | `data/raw/S03/` · Licence: public domain · Native CRS: *pending recon* |

1. Search the portal for **"Roadway Inventory"** (RHiNo).
2. Download the statewide roadway file (shapefile or file geodatabase).
3. Clip to the MSA + 15-mile buffer on ingest, not before — keep the raw statewide file.
4. **Check for truck-restriction attributes.** Scope §14 anticipates they may be absent; if so,
   the functional-class fallback in `config/network.yaml → truck_restriction_rule` applies.
   Record which applied — that is **D-004**.

Also confirm coverage includes **local streets**. A network biased toward arterials cannot
support honest 15-minute labour-shed service areas, and would be a reason to prefer S04.

---

## S04 · OpenStreetMap Texas extract — **AUTO**

| | |
|---|---|
| Provider | Geofabrik · Portal: <https://download.geofabrik.de/north-america/us/texas.html> |
| Endpoint | `https://download.geofabrik.de/north-america/us/texas-latest-free.shp.zip` |
| Destination | `data/raw/S04/` · Native CRS: **EPSG:4326** |
| Licence | **ODbL 1.0 — attribution required on every published map** |

Stable URL, always the current extract. Download and unzip; `gis_osm_roads_free_1.shp` is the
road layer. OSM carries explicit `hgv` truck tags and richer local-street coverage than RHiNo,
which is the trade-off recorded in **D-004**.

If OSM is used in the delivered network, ODbL attribution must appear on **every** map and in
the StoryMap credits. That obligation propagates.

---

## S05 · Interchanges — **AUTO** (derived)

Derived from S03: intersections of **functional class 1 and 2** segments. No download.
Alternative source is NTAD (S06) if the derivation proves noisy. Destination `data/raw/S05/`
only if a downloaded alternative is used.

Validate visually against a basemap before trusting it — C04 (highway access) is a scored
criterion and a spurious interchange moves candidates.

---

## S06 · Intermodal, rail, airports (NTAD) — **MANUAL**

| | |
|---|---|
| Provider | USDOT Bureau of Transportation Statistics · Portal: <https://geodata.bts.gov/> |
| Destination | `data/raw/S06/` · Licence: public domain · Native CRS: typically EPSG:4326 |

1. Search for **Intermodal Freight Facilities**; download the rail and truck facility layers.
2. Also take **rail lines** and **airports** for `Railroads` and `Airports`.
3. Filter to facilities a retail DC would actually use — rail intermodal and air cargo; exclude
   marine and pipeline.

**Derive the list from NTAD, not from the scope's prose.** §5.2 names four facilities but flags
them `[VERIFY]`. C06 rankings are sensitive to omissions. This is **D-005**.

---

## S07 · National Highway Freight Network — **MANUAL**

Provider FHWA · <https://ops.fhwa.dot.gov/freight/infrastructure/nfn/> · `data/raw/S07/` ·
public domain. Context and corridor maps only; **not scored**. Low priority.

---

## S08 · ACS 5-year estimates — **AUTO** ⚠️ *requires an API key*

| | |
|---|---|
| Provider | US Census Bureau · Portal: <https://www.census.gov/data/developers/data-sets/acs-5year.html> |
| Endpoint | `https://api.census.gov/data/{year}/acs/acs5` |
| Destination | `data/raw/S08/` · Licence: public domain · Native CRS: n/a (tabular) |

> **Verified: the API now requires a key.** Unauthenticated requests return HTTP 200 with an
> HTML page titled *"Missing Key"* — not a JSON error, so naive code will fail confusingly.
> Get one free and instantly at <https://api.census.gov/data/key_signup.html>, then set
> `CENSUS_API_KEY` as an environment variable. **Never commit it.**

Vintages available: 2019–2024. Tables: **B23025** (employment status), **C24010** (occupation),
**B08301** (commute mode), **B08201** (vehicles), **B19013** (median income).

**Verified correction for criterion C01.** C24010 has no combined "transport and material
moving" line. It splits three ways per sex:

```
occ_transp_matmov = C24010_036E + C24010_037E + C24010_072E + C24010_073E
occ_prod          = C24010_035E + C24010_071E
```

Using the parent lines `C24010_034E` / `C24010_070E` folds **production** workers into the
warehouse labour pool and inflates C01 — factory workers are not distribution-centre workers.

*Pending recon:* whether **C24010 is published at block group**. ACS 5-year limits block-group
geography to a subset of tables and this cannot be tested without a key. If it is not, fall back
to tract-level apportionment and document it.

Example once the key is set:

```bash
curl "https://api.census.gov/data/2023/acs/acs5?get=NAME,C24010_036E,C24010_037E&for=block%20group:*&in=state:48%20county:439&key=$CENSUS_API_KEY"
```

---

## S09 · TIGER/Line geography — **AUTO**

| | |
|---|---|
| Provider | US Census Bureau · Endpoint: `https://www2.census.gov/geo/tiger/TIGER{year}/` |
| Destination | `data/raw/S09/` · Licence: public domain · Native CRS: **EPSG:4269** (NAD83) |

No key required. Stable, predictable paths — take `BG/` (block groups), `TRACT/`, `COUNTY/`,
`PLACE/`, `CBSA/`, state FIPS **48**.

**The vintage must match the ACS vintage in S08**, or the joins silently drop rows. Confirm the
CBSA file gives the DFW–Arlington MSA 11 counties (code `19100`) — that closes **D-001**.

---

## S10 · LEHD LODES 8 — **AUTO** · *verified*

| | |
|---|---|
| Provider | US Census Bureau LEHD · Endpoint: `https://lehd.ces.census.gov/data/lodes/LODES8/` |
| Destination | `data/raw/S10/` · Licence: public domain · No key required |

Verified live — **every column named in `config/schema.yaml` exists**, no changes needed.
Latest year present: **2022**.

```
https://lehd.ces.census.gov/data/lodes/LODES8/tx/wac/tx_wac_S000_JT00_2022.csv.gz   (53 cols)
https://lehd.ces.census.gov/data/lodes/LODES8/tx/rac/tx_rac_S000_JT00_2022.csv.gz   (43 cols)
https://lehd.ces.census.gov/data/lodes/LODES8/tx/od/tx_od_main_JT00_2022.csv.gz     (13 cols)
```

Confirmed present: `w_geocode`, `h_geocode`, `C000`, **`CNS08`** (transportation and
warehousing, NAICS 48–49), `S000`, `SA01–03`, `SE01–03`, `SI01–03`.

Also take neighbouring states — `ok`, `la`, `ar`, `nm` — for commute context.
Geocodes are **block**-level (15 digits); aggregate to tract on ingest.

---

## S11 · BLS wages (OEWS, QCEW) — **MANUAL**

Provider BLS · <https://www.bls.gov/oes/> · `data/raw/S11/` · public domain.
SOC codes **53-7062**, **53-7065**, **53-3032** for the DFW MSA; QCEW county-level NAICS 493.
Report context and an optional county labour-cost criterion — **not** part of C01–C11.

---

## S12 · County Business Patterns — **AUTO** (same key as S08)

`https://api.census.gov/data/{year}/cbp` · `data/raw/S12/` · public domain.
NAICS **493** (warehousing) and **484** (trucking) for the 11 counties. Cluster context for the
report.

---

## S13 · FEMA NFHL — **MANUAL** · *verified schema*

| | |
|---|---|
| Provider | FEMA · Portal: <https://msc.fema.gov/portal/advanceSearch> |
| REST | `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer` — **layer 28** |
| Destination | `data/raw/S13/` · Licence: public domain |

Download the NFHL county file geodatabase per county from the Map Service Center, or pull
layer 28 via REST. Verified field names:

| Field | Type | Note |
|---|---|---|
| `FLD_ZONE` | String(17) | A, AE, AH, AO, X, VE, D … |
| `ZONE_SUBTY` | String(**76**) | **where FLOODWAY lives** |
| `SFHA_TF` | String(**1**) | `"T"` / `"F"` — **text, not boolean** |
| `STATIC_BFE`, `DEPTH`, `VELOCITY` | Double | |
| `DFIRM_ID` | String(6) | study id |

> **Two traps.** There is **no floodway field** — floodway must be derived by substring-matching
> `FLOODWAY` inside the 76-character `ZONE_SUBTY`. §5.1 makes floodway a **hard filter**, so
> getting this wrong silently passes floodway land into the candidate pool. And `SFHA_TF` is
> `"T"`/`"F"` text while the schema's `sfha_flag` is SHORT — a naive cast yields nulls.

---

## S14 · National Wetlands Inventory — **MANUAL**

Provider USFWS · <https://www.fws.gov/program/national-wetlands-inventory/data-download> ·
`data/raw/S14/` · public domain. Download the **Texas** seamless wetlands geodatabase; clip on
ingest. Large file. Hard filter at <10% coverage (§5.1) and input to C09 risk framing.

---

## S15 · gSSURGO soils — **MANUAL**

Provider USDA NRCS ·
<https://www.nrcs.usda.gov/resources/data-and-reports/gridded-soil-survey-geographic-gssurgo-database>
· `data/raw/S15/` · public domain. Download **gSSURGO Texas** (large — tens of GB).

Only three derived attributes are retained: **hydric percent**, **shrink-swell class**,
**drainage class**. Shrink-swell matters more than it looks for an 800,000 SF slab — expansive
clay is common in North Texas and drives foundation cost.

---

## S16 · USGS 3DEP elevation — **MANUAL**

Provider USGS · <https://apps.nationalmap.gov/downloader/> · `data/raw/S16/` · public domain.

1. Draw the MSA + buffer extent.
2. Select **Elevation Products (3DEP)** → **1/3 arc-second DEM** (or 1 m where available).
3. Download the tiles, mosaic on ingest, then **Slope** (Spatial Analyst) with
   `output_measurement = PERCENT_RISE` → `Slope_pct`.

Reproject the mosaic to EPSG:6584 **before** computing slope, not after — slope computed in
geographic coordinates is wrong.

---

## S17 · NLCD land cover — **MANUAL**

Provider MRLC · <https://www.mrlc.gov/data> · `data/raw/S17/` · public domain.
Take the latest CONUS land cover; clip on ingest. Classes **23** (Developed, Medium) and **24**
(Developed, High) are the "already built out" test in `config/screening.yaml`.

---

## S18 · Building footprints — **AUTO**

Provider Microsoft · <https://github.com/microsoft/USBuildingFootprints> · `data/raw/S18/` ·
**ODbL — attribution required**. Download the **Texas** GeoJSON.

> Footprints carry **no use attribute**. "Industrial" is derived by intersecting with
> industrial-zoned or industrial land-use parcels — which means **C11 inherits every weakness of
> S02 zoning**. State the derivation method in the report; it is not a neutral input.

---

## S19 · TCEQ water & sewer CCN — **MANUAL**

Provider TCEQ · <https://www.tceq.texas.gov/gis/download-tceq-gis-data> · `data/raw/S19/` ·
public domain. Download **Water CCN** and **Sewer CCN** service-area boundaries.

> A CCN is the *right to serve*, not evidence of capacity or infrastructure at the parcel. Scope
> §5.1 uses it as a hard filter; the report must state the limitation and the recommendation must
> list utility capacity as a due-diligence item.

Tarrant also publishes `Transportation/WaterUtilityProvider2025` on its own server — useful as a
cross-check.

---

## S20 · HIFLD electric infrastructure — **MANUAL**

Provider HIFLD · <https://hifld-geoplatform.hub.arcgis.com/> · `data/raw/S20/` · public domain.
Substations and transmission lines. **Context only**, optional criterion. Low priority.

---

## S21 · DICK'S store network — **MIXED** · *pending recon*

| | |
|---|---|
| Provider | dicks.com store locator; OpenStreetMap · Portal: <https://stores.dicks.com/> |
| Destination | `data/raw/S21/` · Licence: public web content, compiled for academic/portfolio analysis |

1. Compile all **DICK'S Sporting Goods**, **Golf Galaxy**, **Public Lands**, and **House of
   Sport** locations within **600 miles** of the MSA centroid.
2. Validate against OSM (`brand:wikidata`) for completeness.
3. Geocode with the **Census Geocoder** (free); minimum acceptable score **90**; review below.
4. **Snapshot with a capture date and record the count** — the store list changes, and every
   C05 number depends on this set.
5. The served set is stores within a **10-hour (600-minute) truck drive** of the MSA centroid,
   computed later by `BuildODMatrices`.

Be a considerate client of the locator: request politely, at a modest rate, and cache. This is
**D-003**.

---

## S22 · NCTCOG regional context — **MANUAL**

Provider NCTCOG · <https://data-nctcoggis.opendata.arcgis.com/> · `data/raw/S22/` · open data.
Regional land use and industrial submarkets. Context maps — and a candidate evidence base for
the `Inferred` zoning tier in **D-009**, since it is regional and internally consistent where
municipal zoning is not. Land use is not zoning and cannot speak to entitlement.

---

## S23 · Lightcast — **MANUAL** · *optional, disabled*

Provider Lightcast · <https://lightcast.io/> · commercial, trial access only.
`enabled: false` in `config/sources.yaml`. Feeds optional criterion **C12**; enabling it
requires rebalancing **all three** weight scenarios (**D-006**). If unavailable, the report
should note that C01–C03 are the open-data equivalent of a commercial labour-analytics product.

---

## Acquisition summary

| Tag | Sources |
|---|---|
| **AUTO** | S04, S05 (derived), S08*, S09, S10, S12*, S18 |
| **MANUAL** | S01, S02, S03, S06, S07, S11, S13, S14, S15, S16, S17, S19, S20, S22, S23 |
| **MIXED** | S21 |

\* requires `CENSUS_API_KEY`.

**Blocking user actions:** obtain a Census API key (S08, S12). **Largest open risks:** S02
zoning coverage, and confirming S01 valuation availability for the ten counties beyond Tarrant.

See also: `docs/REPRODUCE.md` (end-to-end run), `config/sources.yaml` (machine-readable twin),
`docs/recon/RECON_findings.md` (what was verified and how).
