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
