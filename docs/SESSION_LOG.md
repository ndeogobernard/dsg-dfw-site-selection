# Session log

Append-only. One dated block per working session, newest at the bottom.
**Never edit or delete an earlier entry.** Corrections go in a later entry.

Each block records: **what changed**, **what was decided**, **what's next**.
Live status lives in `docs/STATE.md`; decisions in `docs/DECISIONS.md`.

---

## 2026-09-19 — Session 1 · Project kickoff, repo scaffold, geodatabase schema

**Commits:** `ad8a6b5` (scaffold + schema tool), plus this context bootstrap.

### What changed

- Confirmed the environment can deliver the scope: ArcGIS Pro 3.5, **ArcInfo** licence,
  **Network Analyst** and **Spatial Analyst** both `Available`, Python 3.11.11.
  `geopandas`/`shapely`/`fiona`/`pyogrio` absent — need a cloned conda env.
- Chose a **split layout**: repo on the desktop, bulk data and the geodatabase at
  `C:\GIS\dsg-dfw\data\`. `config/paths.yaml` holds the mapping, overridable via `DSG_*`
  environment variables.
- Built the §6.2 repo scaffold, `LICENSE` (MIT), `README.md`, `environment.yml`, `.gitignore`;
  `git init` on `main`.
- Wrote **seven config files** encoding the full analytical specification — `schema.yaml`
  (820 lines), `sources.yaml` (S01–S23, 11-county study area), `screening.yaml`, `network.yaml`,
  `criteria.yaml`, `weights.json`, `paths.yaml`.
- Wrote `src/li/`: `config.py`, `logging_utils.py`, `gdb.py`.
- Wrote `toolbox/LocationIntelligence.pyt` with **tool 1**, `BuildGeodatabaseSchema`.
  Verified it imports into ArcGIS Pro and runs end to end (~3 min 23 s).
- **Built and independently verified `DFW_DSG_SiteSelection.gdb`**: 10 feature datasets,
  29 feature classes, 11 tables, 11 domains, 10 relationship classes, 1 topology with 3 rules,
  5 attribute rules, GlobalIDs on all 40 classes, `CriteriaDefinitions` (11) and
  `WeightScenarios` (33) seeded from config with all scenario weights summing to 1.00.
- Wrote **26 arcpy-free tests**; all pass in 6.5 s.
- Set up this context system: `docs/PROJECT_GUIDE.md`, `docs/STATE.md`, `docs/DECISIONS.md`,
  `docs/SESSION_LOG.md`.

### What was decided

Three deviations from the scope, all implemented and documented in place:

1. **`Parcels` subtypes key on a new integer field `land_use_st`**, not the text
   `land_use_class` as §4.5 states — ArcGIS requires integer subtype fields. `land_use_class`
   keeps its domain and remains the human-readable value; the two are kept in sync on ingest.
2. **GlobalIDs added to every class.** Attribute rules fail with `ERROR 002710` without them —
   this is what broke the §4.5 rules on the first build. Also required for AGOL sync in §7.4.
3. **OD outputs stored as tables, not polyline** (§4.2 permitted either). All-pairs
   candidate-to-store lines have no cartographic value; flow map M06 draws from
   `LODES_OD_Flows`.

Two scope `[VERIFY]` flags investigated and effectively resolved, pending final confirmation
against downloaded data — see `D-001` and `D-002`:

- **EPSG:6584 is correct** — confirmed in Pro as NAD83(2011) StatePlane TX N Central FIPS 4202,
  US Feet.
- **The 11-county MSA list matches the 2023 OMB delineation** — Hood and Somervell correctly
  excluded.

Six scope-level decisions seeded as `OPEN` in `docs/DECISIONS.md` (`D-001`–`D-006`), plus one
proposed scope addition (`D-007`).

### Open question raised by the user, and the honest answer

The user challenged building a detailed schema before collecting or inspecting any data. The
response, recorded here because it shapes the next session:

- **Defensible part.** Roughly 40% of the schema is *our own output* (`CandidateSites`,
  `SiteScores`, `Shortlist`, `SensitivityResults`, `ScoreRuns`, OD tables, scenario/direction
  domains) and depends on no source. The rest is driven by what the analysis *requires* —
  §5.1 screening and §5.3 criteria dictate that `Parcels` must carry acreage, zoning class, and
  value per acre. ETL's job is to map sources into that target, which is what `field_map` exists
  for. ACS table IDs, LODES columns, and the NFHL schema are published standards. And §4.2
  specified this schema explicitly.
- **Valid part.** The **S01 `field_map._default` block is a guess** — written without ever
  seeing a TxGIO parcel file. It is the weakest artifact in the repo.
- **New risk surfaced by the challenge.** Statewide parcel layers are often geometry + ID only,
  with valuations published separately as CAD tabular rolls. If that holds here, criterion
  **C10 (land cost)** needs a join step absent from the pipeline design, and
  `Parcels.appraised_land_val` has nothing filling it.
- **Mitigation, by design.** The schema is a config file, not a hand-built database. Rebuilding
  costs one command and ~3.5 minutes with no data loss. The ERD and `DataDictionary.md` were
  deliberately **not** written yet, because §13.5 requires them to match the delivered schema
  exactly — writing them pre-reconnaissance would guarantee rework.

### What's next

1. **Data reconnaissance** — awaiting the user's go-ahead:
   - Pull Tarrant County parcels; inspect real field names, types, lengths, null rates.
   - Determine whether appraised values ship with parcel geometry or require a CAD roll join.
   - Inventory which of the 11 counties / municipalities publish open zoning (S02) — the single
     biggest schedule risk in the project.
   - Confirm ACS / LODES / NFHL field names against live pulls.
2. Reconcile `config/schema.yaml` against the findings, rebuild the GDB, then write the ERD and
   data dictionary against a schema that has met real data.
3. Resume the toolbox: tool 2 `IngestAndStandardize`, tool 3 `RunQAQC`.

Also awaiting a user decision on `D-007` (validating the model against the realized siting
decision) and on whether to push the repo to GitHub — no remote is configured yet.

---

## 2026-09-19 — Session 2 · Portfolio fix, GitHub remote, Pro project, reconnaissance

**Commits:** portfolio `2aac147`; project `8ccecc0`, `5c5d618`, plus this checkpoint.

### What changed

**1. Portfolio résumé 404 fixed** (`../ndeogo`, commit `2aac147`, pushed to main).
Commit `0311cf6` had deleted `Bernard_Issifu_Resume.pdf` but left the download control at
`index.html:630`, so the button 404'd and `check_site.py` failed. The anchor was the only child
of its own `.resume-section`, which carries `margin-bottom: 2.5rem`, so the wrapper was removed
with it to avoid a stray gap. The now-unused `.resume-download` CSS was left in place —
touching the stylesheet would require re-running `stamp_assets.py`. **check_site.py: 0 errors.**

**2. Project repo published.** <https://github.com/ndeogobernard/dsg-dfw-site-selection> —
public, created with `gh`. Added `.github/workflows/tests.yml`; CI passed in 14s with 26 tests.
The workflow also asserts arcpy is *absent* on the runner, so the arcpy-free guarantee cannot
lapse silently. Verified locally by blocking arcpy via a `sys.meta_path` hook: 26 passed.
All four portfolio GitHub links now return **HTTP 200**.

**3. ArcGIS Pro project** `pro/DFW_DSG.aprx` (commit `5c5d618`), generated by
`tools/setup_pro_project.py`. Three obstacles, all documented in **D-010**: `arcpy.mp` cannot
create an `.aprx`, so it is seeded from the blank project Pro ships for routing services; that
template references a `Blank.atbx`/`Blank.gdb` which are not actually shipped beside it, so both
entries are replaced; and a project must have a valid default toolbox while Pro 3.5's arcpy has
no `CreateToolbox`, so the script writes an empty `.atbx` directly as a zip. Verified: 0 broken
data sources, `"pathSaveRelative": true`, toolbox stored as `..\toolbox\LocationIntelligence.pyt`.
The **geodatabase path is absolute** and cannot be otherwise — it lives outside the repo tree by
design.

**4. Reconnaissance** → `docs/recon/RECON_findings.md`. No ETL written, as instructed.

### What was decided

**D-010 (DECIDED)** — `.aprx` versioning: commit binary snapshots, relative paths on, project
treated as regenerable from script, geodatabase must be built first.

**D-008 and D-009 raised with recommendations, awaiting sign-off.** Both change the schema, so
ETL is deliberately not started.

### What the recon found

- **The lookalike-layer trap.** Hub surfaces `Tax/TCProperty` as "Tarrant County Parcel
  Property" with an *identical 56-field schema* — but 110 features, all county-owned, in
  EPSG:2276. The real layer is `Dynamic/TADParcels`: **758,633 features**, EPSG:3785. Schema
  alone does not tell you which layer you have.
- **D-008 answered.** Appraised values ship with the geometry. `LAND_VALUE > 0` on 693,826 of
  758,633 (91.5%), null on **1** record. **No CAD roll join needed** — the design gap suspected
  in session 1 does not exist for Tarrant. But 8.5% are zero (exempt/ROW/government) and must be
  excluded from C10, or they normalize to the best possible land-cost score.
- **The session-1 field map was wrong.** `PROP_ID`/`LAND_STATE`/`LAND_VAL` do not exist. Correct
  Tarrant mapping recorded in findings §1.6.
- **Zoning is worse than assumed.** TAD parcels carry **no zoning and no land-use field at
  all** — so `zoning_class`, `land_use_class` *and* the `Parcels` subtypes have no source.
  Dallas publishes **20 zoning layers**, and PD parcels hold their real use in
  `PD_Subdistricts`, not base zoning. No authoritative **Fort Worth** layer found. And
  unincorporated Texas land has no zoning by law — not missing data, nothing to find.
- **The candidate band is backwards.** Tarrant alone yields **884 parcels ≥ 80 acres** before
  any other filter. The §5.1 relaxation ladder will not fire; tightening will.
- **LODES verified exactly** — every column in the schema exists. No changes needed.
- **Census API now requires a key**, returning an HTML "Missing Key" page. Blocks all ACS work.
- **C01 was about to be wrong.** C24010 splits production / transportation / material moving.
  `occ_transp_matmov` = `C24010_036E + 037E + 072E + 073E`. Using the parent lines (034/070)
  would fold **production** workers into the warehouse labour pool.
- **NFHL has no floodway field.** Floodway is a value inside `ZONE_SUBTY`, a 76-char free-text
  field, and `SFHA_TF` is `"T"`/`"F"` text rather than boolean. §5.1 makes floodway a hard
  filter, so a wrong derivation silently passes floodway land.

### Method note, recorded so it is not repeated

ArcGIS Hub search is **not** a reliable inventory. Querying Texas jurisdictions returned
Arlington **WA**, Grand Blanc **MI**, Lancaster **OH**, Decatur **GA**, Greenville **NC**,
Mesquite **NV**, and a Denton County "Local Option Zoning Map" that is about liquor, not land
use. Only Dallas was confirmed at the service level. The zoning table in the findings is
labelled INDICATIVE for exactly this reason.

### What's next

1. **Sign-off on D-008 and D-009** — blocking everything downstream.
2. Apply the schema changes in findings §6, rebuild the GDB, update tests.
3. Then tools 2 and 3, with Tarrant as the reference county.

User actions outstanding: Census API key (free, instant); decisions on D-007 (validating
against the realized siting decision) and D-001–D-006.

---

## 2026-09-19 — Session 3 · Week 6 plan, acquisition playbook, tutorial standard, four spokes

**Commits:** hub `481cfcc`, `131c528`, `e74c9c3`, `b6bfc05`, + this checkpoint ·
portfolio `9e4b328` · four new spoke repositories.

### What changed

**1 · Week 6 AGOL planned.** New `docs/PLAN.md` tracks the §11 timeline in-repo. Week 6 is
expanded into **6a** `PublishToAGOL`, **6b** web map via the `arcgis` Python API, **6c**
dashboard scaffold, **6d** StoryMap draft — with a *checkable* dependency gate: `SiteScores` and
`Shortlist` populated for all three scenarios, service areas and served stores resolved, maps
M01–M18 exported. If the gate is not met the right action is to finish Week 5, not publish
partial results. **6c and 6d are marked "scripted scaffold / Bernard finishes"** — widget and
narrative structure is scriptable; cross-widget interactivity, mobile layout, and publishing are
builder-side and human acts. **D-011** logged: default auth is Pro's active portal session, so
this project stores no credential at all.

**2 · `docs/DATA_ACQUISITION.md`** — the manual playbook, one section per S01–S23. Recon findings
folded in where they change what someone should *do*: the Tarrant lookalike-layer trap, Dallas's
20 zoning layers, the Census key requirement, the exact C24010 arithmetic, NFHL's missing
floodway field. Also created `docs/REPRODUCE.md`, which did not exist.

**3 · Dual-track tutorial standard.** `docs/tutorial/README.md` and `_LESSON_TEMPLATE.md`
created — **neither existed**, so they were written to spec rather than edited. Every lesson
carries Track A (automated), Track B (manual in ArcGIS Pro from raw sources), and a *Concepts —
why this works* section. `docs/PROJECT_GUIDE.md` Checkpoint now captures both tracks when a phase completes.

**4 · Four spoke repositories published**, all public, all HTTP 200:

| Repo | Files | CI |
|---|---:|---|
| `config-driven-geodatabase-schema-builder` | 14 | ✅ 26 tests, 12s |
| `arcgis-location-intelligence-toolbox` | 19 | ✅ 26 tests, 12s |
| `dfw-site-selection-explorer` | 5 | — |
| `dfw-site-selection-cartography` | 6 | — |

Sync is driven by `tools/spokes.yaml` + `tools/sync_spokes.py` rather than by memory: copies
only what the manifest names, skips identical files, never deletes, and **exits non-zero if an
entry has vanished from the hub**. Tests were run standalone in both tool spokes *before*
publishing — 26 passing in each.

**5 · Portfolio cards** now carry both links, hub and spoke (`9e4b328`). The Cartography gallery
card had no `card-links` block and gained one; `.card-links` already has `position:relative;
z-index:1`, which is what keeps pills clickable above the card's own map-viewer handler, so no
CSS was needed. `check_site.py`: 0 errors.

### What was decided

**D-011 (OPEN)** — AGOL authentication. **D-012 (DECIDED)** — hub/spoke strategy.

### Two things worth recording

- **Three files the instructions said to *edit* did not exist** — `docs/tutorial/README.md`,
  `_LESSON_TEMPLATE.md`, `docs/REPRODUCE.md`. Created to the same spec and flagged rather than
  silently invented.
- **A script bug caught by failing safely.** The first card-link script matched
  `DICK&#39;S` where the cartography card holds a literal apostrophe. It called `sys.exit(1)`
  *before* writing, so three already-computed edits were discarded and the file was untouched —
  confirmed by a clean `git status`. Worth keeping: validate-then-write, never write-as-you-go.

### What's next

Unchanged and still blocking: **sign-off on D-008 and D-009**. Then apply the schema changes in
`docs/recon/RECON_findings.md` §6, rebuild the GDB, re-sync the schema-builder spoke, and build
tools 2 and 3.

---

## 2026-09-22/23 — Session 4 · Schema reconciled, tools 2–3 built, Tarrant pilot loaded

**Commits:** `384e228`, `1045e72`, `915b695`, `dbda2e7`, `abe1fa4`, + this checkpoint.
Both tool spokes re-synced and pushed.

### What changed

**1 · Schema reconciled and rebuilt** (D-008, D-009, D-013). `acres_published` beside
geometry-derived `acres` with a `calc_Parcel_AcresDelta` rule recording the disagreement;
`land_val_flag` so a zero value is never read as free land; `dm_ZoningConfidence` and
`zoning_confidence`; screening stripped of every industrial-zoning requirement; **C12** added
for the zoning/entitlement signal with its weight **carved out of C11** so each scenario still
sums to exactly 1.00; `Parcels` subtypes rekeyed onto `zoning_conf_st`. C01 pinned to the four
C24010 lines that exclude production workers. Rebuilt clean: 12 domains, 6 attribute rules,
24 criterion columns.

**2 · Tools 2 and 3.** `src/li/etl.py` and `src/li/qaqc.py`, both keeping decisions in pure
arcpy-free functions. Tool 2 refuses any county not marked `verified`, checks the feature count
so a lookalike layer cannot be ingested, and writes provenance every run.

**3 · All 10 remaining CADs probed, none ingested.**

**4 · Tarrant pilot: 758,633 / 758,633 loaded, 10 Pass / 1 Warning / 0 Fail**, 93 minutes.

### What was decided

**D-008-R** and **D-009-R** record the accepted implementations; **D-013** covers physical-only
screening and the subtype rekey; **D-014** is new and OPEN.

### Three things the work caught that assumptions had not

**The QA check caught a wrong primary key — before it could do damage.** The 3-page smoke test
failed `ING-DUP-KEY` with 15 duplicates in 3,000 rows. Verified over 20,000 records: `ACCOUNT`
is 100% unique, `TAXPIN` only 98.44%. TAXPIN identifies the survey *abstract tract*; `A1614-1C`
carries eight separately-appraised accounts. The recon note said "TAXPIN is the GIS key,
ACCOUNT the tax key" and I chose the GIS-sounding one without ever checking uniqueness. Had
that check been a warning instead of a hard failure, assemblage logic would later have merged
unrelated parcels sharing a tract, and the map would have looked entirely plausible.

**D-008 did not generalise.** Dallas `CurrentDcadParcels` publishes 695,446 features with five
fields — geometry, an account number, an acreage. No land value, no owner, no zoning. C10
cannot be computed for the second-largest county in the study area from the parcel layer alone.
D-008's "no roll join needed" held only because Tarrant happened to be probed first. Recorded
as **D-014**, OPEN, rather than patched over.

**A quarter of Tarrant parcels disagree with their own geometry on acreage.** 191,192 parcels
(25.20%) differ by more than 5% between CAD-published and geometry-derived acres. D-008 screens
on the published figure and that remains right — it is what a broker would quote — but this is
a methodology-report fact, not a log line.

### Cross-checks that held

`acres_published >= 80` returns **884** parcels, matching the server-side recon count exactly.
Zero land value came in at **8.54%**, against 8.5% measured in recon. Two independent routes to
the same numbers.

### Also worth recording

- Smoke-testing with `--max-pages 3` cost 36 seconds and found the key bug. The full run is 93
  minutes.
- A feature class with attribute rules cannot be written outside an edit session; the session
  is also what makes the rules fire, so `acres` and `land_val_per_acre` are populated by it.
- `JSONToFeatures` overhead meant 759 per-page calls would have dominated the ingest;
  concatenating to 16 files fixed it.
- I pushed the schema-builder spoke with a red CI because I ran its tests and the push in the
  same command, so the failure could not block. The manifest was missing `screening.yaml`.
  Fixed, and spoke tests now run *before* the push. The red run stays in that repo's history.

### What's next

Tarrant is viewable in `pro/DFW_DSG.aprx`. Stopped for review before touching the other ten.
**D-014** decides whether Dallas can be scored at all. The ERD and data dictionary are now
unblocked — the schema has met real data.

---

## 2026-09-23/24 — Session 5 · Vertical slice Part 1: physical layers ingested, Tarrant screened

**Goal.** Part 1 of 3 of the Tarrant vertical slice: ingest the physical-filter layers, build
`ScreenCandidateSites` as a physical-only screen, run the funnel, stop before the network
dataset.

### What changed

**Seven physical-filter layers ingested for the Tarrant slice** (county + 2 mi buffer), each
with a `DataSourceRegistry` row and a QA check:

| Layer | Features | Source |
|---|---|---|
| `FloodZones_NFHL` | 26,850 | FEMA NFHL |
| `Wetlands_NWI` | 37,409 | FWS |
| `IndustrialBuildings` | 532,471 | Tarrant County |
| `Interchanges` | 805 | TxDOT Roadway Inventory, derived |
| `LandCover_NLCD` | 3,134 × 3,180 | MRLC WCS |
| `Slope_pct` | 7,580 × 7,940 | USGS 3DEP, derived |
| `WaterCCN` | 127 | Tarrant County (earlier run) |

**`ScreenCandidateSites` built and run.** Physical-only per D-013. Thresholds entirely from
`config/screening.yaml` at scope Appendix B defaults, untightened. 758,633 parcels →
**138 candidates**, 137 `Pass` / 1 `Review`. QA on `CandidateSites` 8 Pass, 0 Warning, 0 Fail.
Funnel reconciles exactly. All nine layers added to `pro/DFW_DSG.aprx`.

**Five service-side and geoprocessing defects found and fixed**, each recorded in config rather
than patched around in code:

1. **FEMA NFHL** rejects pages above 250 rows → `page_size: 250` plus adaptive page halving.
2. **FWS wetlands** times out past `resultOffset` 2000 → tiled downloader (`download_rest_tiled`).
3. **`Intersect` emits MULTIPOINT**, which a point class will not accept — surfaced only as a
   bare `AttributeError: __len__` from deep inside `insertRow`. Explode to singlepart first.
4. **MRLC publishes the NLCD coverage in EPSG:3857** and GeoServer cannot *write* a
   Pseudo-Mercator GeoTIFF. Subset in 4326, demand 5070 back via `outputCrs`.
5. **`MakeImageServerLayer` + `CopyRaster` returned a 1 × 1 slope raster.** Replaced with
   `exportImage` at an explicit bbox and size, tiled at 1024 px (3DEP gateway-times-out at ~80s
   on tiles well inside its own declared 8000 px cap), with a size guard that refuses to derive
   slope from a stub. The z-factor (3.28084) matters as much: elevation is in metres, x/y in US
   feet, and an unscaled `PERCENT_RISE` understates every slope by 3.28×.

### What was decided

- **D-015** — interchange proximity is straight-line at screening, radius *derived* from the
  drive-time threshold (`15/60 × 35 ÷ 1.3 = 6.73 mi`), not typed. `DECIDED`.
- **D-016** — sewer CCN is **not** a hard filter this run and **not** permanently demoted.
  Every candidate carries `sewer_status = "Unknown - pending D-016 search"`; the funnel reports
  the stage as SKIPPED. Stays `OPEN` pending the manual search.
- **D-017** — zone rasterization cell size. `DECIDED`. See below.

### The one that mattered

The first screening run produced **180 candidates with 56 in `Review`**, 55 of them for
"developed land cover: not measurable". The NLCD raster covered those parcels — sampling it at
their centroids returned real classes. `TabulateArea` keeps only cells whose *centre* falls
inside a zone, and at NLCD's ~83.5 ft cell the corridor-shaped parcels common among 80+ acre
urban holdings (median effective width ~71 ft) captured none. 112 of 884 parcels were absent
from the table rather than zero.

Setting `raster_zonal.processing_cell_ft: 30` took coverage to 883/884 and 884/884, and the
candidate list from **180 → 138**, `Review` from **56 → 1**. Forty-two of the dropped parcels
genuinely exceed `max_developed_pct` and had been surviving on a metric that was never computed.

Nothing unsafe was admitted — unmeasurable scores `Review`, never `Pass` — but the list was
full of parcels nobody had screened, and they were indistinguishable from real candidates.
`_warn_if_patchy()` now logs a warning when any raster metric covers under 98% of its zones.

### What's next

1. **STOP** — the user reviews the 138 candidates in `pro/DFW_DSG.aprx` and calibrates
   thresholds before Part 2.
2. Part 2: network dataset, service areas, OD cost matrix.
3. D-016 remains open pending a sewer-CCN source; D-014 (Dallas roll join) still blocks Dallas.

---

## 2026-09-24 — Session 6 · Vertical slice Part 2: routing network, service areas, OD matrix

**Goal.** Resolve D-004, build and validate the network dataset, produce service areas and the
candidate-to-store OD matrix. Stop before scoring.

### Stage A — the road-source decision

RHiNo was measured against the live service rather than described: **908,702 statewide segments,
`SPD_MAX` populated on 30.7%, `DIR_TRAV` on 0.0%**, and no truck-restriction attribute at all
(`SEC_TRK` is the Texas Trunk System designation, `TRUCK_HY_*` are volumes). Local-street
coverage was fine at 62.2% `F_SYSTEM 7`, so the stub's worry about arterial bias was wrong.

The decision turned on extent, not attributes. Scope §2.2 defines the served set as stores within
a 10-hour truck drive of the MSA centroid; the 600-mile radius that bounds the store compilation
intersects **sixteen states** (computed via TIGERweb, not guessed — the scope had estimated nine).
RHiNo is Texas only, so it cannot compute a drive time to an Oklahoma City store at all.

Recommended OSM via Geofabrik; **the user chose it**. D-004 closed as DECIDED.

### Stage B — the network

3.8 GB of extracts, two-tier extraction (long-haul classes across all sixteen states, full street
detail only over the MSA), **1,399,985 segments** loaded, `RoadNetwork_ND` built in 124 s.

**Validated on 7 reference routes in both modes, 7/7 each.** Distances within 2% on every route
including Dallas–Albuquerque at 649.7 mi against 647. Times 4–15% fast, which is the right
direction for a free-flow network. Truck slower than Driving everywhere. The four out-of-state
routes solving is what D-004 was about.

### Stage C — store set, service areas, OD

**179 stores** matched from the OSM extracts already downloaded (161 DSG, 10 Golf Galaxy, 5 House
of Sport, 3 Public Lands), above the scope's "100+". **143 served** within 600 truck-minutes.
**412 driving isochrones**, **4 freight-reach bands**, **19,152 OD pairs**.

### What was decided

- **D-004 (resolved)** — OSM via Geofabrik, sixteen states. RHiNo kept as a validation source.
- **D-018** — ODbL. Attribution on every published map; `Roads`, `RoadNetwork_ND` and the
  geodatabase are **not** published, because share-alike attaches to a derived database and would
  reach parcel and CAD data this project has no standing to relicense.
- **D-019** — truck travel time is a **second** cost attribute. §4.6 asks the Truck mode to use
  "impedance `Minutes`" *and* capped speeds; one column cannot do both, and sharing it would have
  computed the labour-shed isochrones at truck speeds.
- **D-020** — `ServiceAreas_Truck` is built from the **MSA centroid**, not from 138 candidates.
  Nothing in `criteria.yaml` consumes it, and the Driving equivalent measured 31 minutes per
  batch of 50.

### Five bugs, all found by checking rather than by reading

1. **`hgv: [no, ...]` in YAML parses as `[False, ...]`** — the commonest truck prohibition in OSM
   silently stopped matching. Found by a smoke test asserting `hgv=no` restricts.
2. **Committing a transaction mid-iteration invalidates the SQLite read cursor**, restarting the
   attribute pass every 250k rows. Texas ran half an hour without finishing instead of six
   minutes. Invisible below 250k rows, which is why it reached a 326k-row file.
3. **The two extraction tiers overlapped**, putting **121,147** OSM ways into the network twice as
   parallel edges. Routing still worked. Found by comparing `road_id` sets between tiers.
4. **The OD matrix loaded all 179 stores as destinations instead of the 143 served.** Exposed by
   a QA line reading "max 145" against 143 served — a number that cannot exist.
5. **`Intersect` with POINT output emits MULTIPOINT**, failing as a bare `AttributeError:
   __len__` from inside `insertRow`.

### One finding that is not a bug

**`TAR-00758` is marooned.** Its label point snaps to *Perimeter Road*, an isolated 2.44-mile
private, truck-restricted OSM stub that intersects **nothing**. The facility sits 41.6% along it,
so its driving service area caps at exactly 2.44 minutes instead of 45 — the solver reported
success. It still has 142 OD rows because the OD solver snapped it to a different edge. Caught
because 412 polygons is not 138 × 3. `SA-REACH-FULL` now warns whenever a candidate's largest
polygon falls short of the largest break; any workforce figure computed from that polygon would
have been meaningless and would have looked fine.

### Also worth knowing

**Travel modes could not be put on the network dataset.** arcpy exposes no tool to add one, and
the `TravelModes` property key in the exported template XML is ignored on import — the created
network still reported none. Since `arcpy.nax` refuses to open a network without travel modes,
the solvers use the classic `arcpy.na.Make*Layer` tools, which take impedance, restrictions and
U-turn policy as explicit arguments read from `network.yaml`. Arguably more legible; the cost is
an empty travel-mode dropdown for anyone starting a Network Analyst layer by hand in Pro.

**Not a bug, recorded because it looks like one:** 77% of Texas `secondary` is tagged
`oneway=yes`. Confirmed against the raw extract — those are Texas's one-way frontage roads.

### Run identity

Service areas and the served set carry `20260924_0403_network`; the OD matrix was rebuilt after
the destinations fix and carries `20260924_0555_network`. Both are in `QAQC_Log`.

### What's next

1. **STOP** — the user reviews Part 2 and decides on `TAR-00758`.
2. Part 3: criteria, three weighting scenarios, sensitivity, shortlist.
3. The Census API key now blocks C01–C03 directly, since the service areas they need exist.
