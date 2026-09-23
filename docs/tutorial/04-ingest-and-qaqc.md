# Lesson 04 — Ingest, standardization, and QA/QC

**Phase:** scope §6.3 tools 2–3 / Week 3 · **Status:** 🔄 Track A performed and verified · Track B not yet performed
**Prerequisites:** Lesson 02 (build the schema) · **Time:** automated ~93 min for Tarrant (758,633 parcels) — 7 min of it downloading

---

## What you will end up with

Tarrant County's parcels loaded into `Parcels` in the analysis CRS, with provenance in
`DataSourceRegistry`, every §10 quality check recorded in `QAQC_Log`, and the raw downloads
preserved unmodified in `data/raw/tarrant/`.

## Why this step exists

Everything downstream is a function of what gets loaded here. Screening filters these rows;
C07 and C10 read these fields. A field mapped to the wrong source column does not raise an
error — it produces a column full of plausible-looking nulls, or worse, plausible-looking
wrong numbers. This lesson is mostly about making that failure mode loud.

---

## Concepts — why this works

**The idea.** Ingest is three separable jobs: *acquire* (get bytes from a provider), *conform*
(reshape those bytes to your schema), and *load* (write them into the geodatabase). Keeping
them separate is what lets you re-run one without the others, and what lets the raw download
stay a faithful record of what the provider actually served.

**Why a per-county field map and no shared default.** The obvious design is one default
mapping with per-county overrides. It was tried, and it was wrong for Tarrant in *every single
field* — the default guessed `PROP_ID`, `LAND_STATE`, `LAND_VAL`; the real fields are
`ACCOUNT`, none, `LAND_VALUE`. Eleven appraisal districts publish independently and share no
schema. A default here is not a convenience, it is a mechanism for silently producing empty
columns. So `IngestAndStandardize` **refuses** any county whose map is not marked `verified`.

**The assumption being made.** That the endpoint you point at is the layer you think it is.
This is not safe. Tarrant publishes `Tax/TCProperty` with an *identical 56-field schema* to
`Dynamic/TADParcels` — and 110 features instead of 758,633, all county-owned. Schema does not
identify a layer. The feature count does, which is why `expected_feature_count` is a config
value and a hard check.

**How it can go wrong quietly:**

- A field maps to a column that exists but means something else. Nothing errors.
- The key you chose is not unique. Assemblages later merge unrelated parcels and the map looks
  fine. *(This happened — see below.)*
- A zero is read as a value rather than an absence. A zero land value is exempt or
  right-of-way land, not the cheapest land in the county; treated as a number it normalizes to
  the *best possible* C10 score and dominates the ranking.
- Paging is forgotten. `maxRecordCount` is 1,000, so an unpaged request returns the first
  1,000 rows and reports success.

---

## Steps

### Track A — Automated (the tool)

```bash
python tools/pilot_ingest_tarrant.py --fresh
```

Or in ArcGIS Pro: **LocationIntelligence → 2 - Ingest and Standardize**.

| Parameter | Value used | Why |
|---|---|---|
| `source_id` | `S01` | Parcels |
| `county` | `tarrant` | The only county marked `verified` |
| `gdb` | from `config/paths.yaml` | Never hard-coded |
| `max_pages` | `0` (all) | Set to `3` first to smoke-test — it is what caught the key bug |
| `reuse_download` | `False` (`--fresh`) | Force a clean pull |
| `allow_unverified` | `False` | Leave it false; it exists to be deliberate, not convenient |

**Config that drives this:** `config/sources.yaml → S01.counties.tarrant`

Then the checks:

```bash
python -c "import sys;sys.path.insert(0,'src');from li import config,qaqc;print(qaqc.summarize(qaqc.run_parcel_checks(config.paths()['gdb']+'\\Cadastral\\Parcels',config.paths()['gdb'],6584)))"
```

**Measured on the real run** (Tarrant, 758,633 parcels, this machine):

```
downloaded 758,633 features to 759 files in 427s
combined 759 pages into 16 files
staged 758,633 features in EPSG:6584
appended 758,633 rows into Parcels
ingest finished in 92.0 min
```

The download is 7 minutes of the 93. The rest is conversion, projection, and the row-by-row
append through the edit session — which is the price of having the attribute rules fire on
insert rather than running a separate calculate pass afterwards.

**What the tool does, in order:** read the live field list → check the feature count against
`expected_feature_count` → resolve the field map → page the REST layer to GeoJSON in
`data/raw/tarrant/` → concatenate pages → `JSONToFeatures` → `Project` to EPSG:6584 → insert
into `Parcels` inside an edit session → write `DataSourceRegistry` → run §10 checks → write
`QAQC_Log`.

### Track B — Manual (by hand in ArcGIS Pro)

> **Not yet performed.** Written from the tool's own steps rather than from doing it by hand,
> so treat it as a plan rather than a verified procedure. It will be confirmed and corrected
> when a county is ingested manually.

1. **Confirm the layer.** Open
   `https://mapit.tarrantcounty.com/arcgis/rest/services/Dynamic/TADParcels/MapServer/0` in a
   browser. Check the feature count is ~758,633, **not** ~110.
2. **Add Data → From Path**, paste the URL. Pro pages the service itself.
3. **Data → Export Features** to `data/raw/tarrant/`.
4. **Project** (Data Management → Projections and Transforms) to EPSG:6584. Record the datum
   transformation used — that is a §10 check, not bookkeeping.
5. **Append** (Data Management) into `Parcels`, using **Field Map** to wire `ACCOUNT →
   parcel_id`, `LAND_ACRES → acres_published`, `LAND_VALUE → appraised_land_val`,
   `TOTAL_VALU → appraised_total_val`, `TAXPIN → alt_parcel_id`.
6. **Calculate Field** for `land_val_flag` — `ZeroExempt` where `appraised_land_val = 0`.
7. Add a `DataSourceRegistry` row by hand: provider, dataset, URL, vintage, download date,
   licence, native CRS, transformation.

**Where this differs from Track A.** Pro's Append does not set `land_val_flag` or
`zoning_confidence`, so step 6 is a separate manual pass the tool folds into the load. The
tool also refuses an unverified county and checks the feature count; by hand, both are on you
to remember.

---

## Verify it worked

| Check | How | Expect |
|---|---|---|
| Feature count | `GetCount` on `Parcels` | 758,633 — exactly the source count |
| CRS | `arcpy.da.Describe(fc)["spatialReference"]` | EPSG **6584** |
| Key uniqueness | `ING-DUP-KEY` in `QAQC_Log` | **Pass** — 0 duplicates |
| Attribute rules fired | `acres`, `land_val_per_acre` populated | non-null where inputs exist |
| Provenance | `DataSourceRegistry` | one row per ingest run |

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `Objects in this class cannot be updated outside an edit session` | `Parcels` carries attribute rules | Wrap inserts in `arcpy.da.Editor` |
| `ING-DUP-KEY` fails | The chosen key is not unique | Check uniqueness on a sample *before* choosing |
| Ingest refused, "not 'verified'" | County field map unconfirmed | Read the live field list, then promote it |
| Only 1,000 rows loaded | Paging forgotten | `resultOffset` must advance per page |
| Conversion takes longer than the download | One `JSONToFeatures` call per page | Concatenate pages first |

---

## What this produced

| Output | Where | Feeds |
|---|---|---|
| `Parcels` rows | `Cadastral/Parcels` | screening, C07, C10 |
| Raw GeoJSON pages | `data/raw/tarrant/` | reproducibility |
| Provenance row | `DataSourceRegistry` | §10, methodology appendix A |
| Check results | `QAQC_Log` | §10, methodology appendix D |

## Try it yourself

- Run with `--max-pages 3` and watch how fast the QA summary comes back. Smoke-testing on
  3,000 rows rather than 758,633 is what made the key bug cheap to find.
- Point `endpoint` at `Tax/TCProperty` instead and watch the feature-count check refuse it.
- Set a county's `status` back to `skeleton` and confirm the tool refuses to run.

## Further reading

- `docs/DATA_ACQUISITION.md` §S01 — per-county acquisition and status
- `docs/DECISIONS.md` — **D-008** (land cost), **D-009** (zoning), **D-014** (Dallas roll join)
- `docs/recon/RECON_findings.md` §1 — the Tarrant field inventory this map came from
