# Session log

Append-only. One dated block per working session, newest at the bottom.
**Never edit or delete an earlier entry.** Corrections go in a later entry.

Each block records: **what changed**, **what was decided**, **what's next**.
Live status lives in `.claude/STATE.md`; decisions in `docs/DECISIONS.md`.

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
- Set up this context system: `CLAUDE.md`, `.claude/STATE.md`, `docs/DECISIONS.md`,
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
partial results. **6c and 6d are marked "Claude Code scaffolds / Bernard finishes"** — widget and
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
why this works* section. `CLAUDE.md` Checkpoint now captures both tracks when a phase completes.

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
