# STATE — live project snapshot

> Snapshot, not history. Overwrite this file at each checkpoint.
> Narrative belongs in `docs/SESSION_LOG.md`; decisions in `docs/DECISIONS.md`.

**Last updated:** 2026-09-24 · main · <https://github.com/ndeogobernard/dsg-dfw-site-selection>

---

## ⏸ Stopped here, by request

**Vertical slice Part 1 is complete. Parts 2 and 3 are deliberately not started.**

Open `pro/DFW_DSG.aprx` and look at **138 candidate sites** over Tarrant before deciding
whether to calibrate thresholds or move to the network dataset.

---

## Current milestone

**Week 4 of 8** (scope §11). Full tracker with exit criteria: **`docs/PLAN.md`**.

| Milestone | Status |
|---|---|
| W2 — geodatabase schema built via tool | ✅ |
| W3 — ETL and QA/QC tools written | ✅ tools 2 and 3 |
| W3 — all layers loaded | 🔄 **Tarrant only**; 10 counties pending |
| W4 — screening tool + CandidateSites | ✅ **Tarrant, 138 candidates** |
| W2 — ERD + data dictionary v1 | ⏸ deferred — schema is stable and has now met real data |
| W5 — network dataset, service areas, OD | ⬜ Part 2, not started |

---

## Done this session

- **Seven physical-filter layers ingested** for the Tarrant slice, each with a
  `DataSourceRegistry` row and a QA check.
- **`ScreenCandidateSites` built and run** — physical-only (D-013), every threshold from
  `config/screening.yaml` at scope defaults, untightened.
- **758,633 parcels → 138 candidates.** 137 `Pass`, 1 `Review`. QA 8 Pass / 0 Warning / 0 Fail.
- **D-015, D-016, D-017** recorded. Five service-side defects fixed in config, not worked around.
- All nine layers added to `pro/DFW_DSG.aprx`. Tests still **121**, all arcpy-free.

## Layers loaded — Tarrant slice (county + 2 mi)

| Layer | Loaded | Note |
|---|---|---|
| `Parcels` | 758,633 | earlier session |
| `FloodZones_NFHL` | 26,850 | `page_size: 250` — NFHL 500s above that |
| `Wetlands_NWI` | 37,409 | tiled — service times out past offset 2000 |
| `IndustrialBuildings` | 532,471 | tiled |
| `Interchanges` | 805 | derived from TxDOT F_SYSTEM 1–2 crossings |
| `LandCover_NLCD` | 3,134 × 3,180 | MRLC WCS, subset 4326 → `outputCrs` 5070 |
| `Slope_pct` | 7,580 × 7,940 | 3DEP `exportImage`, 64 tiles, z-factor 3.28084 |
| `WaterCCN` | 127 | water only — no sewer attribute |

## Screening funnel — Tarrant, run `20260924_0020_screen`

| # | Filter | Threshold | Removed | Remaining |
|---|---|---|---|---|
| | parcels in county | | | 758,633 |
| 1 | acreage ≥ min_acres | 80 | 757,749 | 884 |
| 2 | floodway coverage | 0 | 151 | 733 |
| 3 | SFHA coverage | 20 | 131 | 602 |
| 4 | wetland coverage | 10 | 88 | 514 |
| 5 | mean slope | 5 | 113 | 401 |
| 6 | developed land cover | 30 | 184 | 217 |
| 7 | water CCN service | true | 62 | 155 |
| 8 | interchange proximity | 6.73 mi | 17 | **138** |
| — | sewer CCN service | **SKIPPED** | — | — |

Acreage does 99.9% of the work. After it, **developed land cover (184)** and **floodway (151)**
are the binding constraints — large parcels in a built-out county tend to be built on or in the
floodplain. Interchange proximity removes only 17, so D-015's approximation is not what decides
this list.

---

## Blocked / needs decision

1. **User review of the 138 candidates** — calibrate thresholds before Part 2, or accept.
2. **D-016 — sewer CCN.** No statewide source. User is searching TCEQ, TWDB, NCTCOG, PUC.
   Every candidate carries `sewer_status = "Unknown - pending D-016 search"`. Stays OPEN.
3. **D-014 — Dallas needs a DCAD roll join.** `CurrentDcadParcels` is geometry + account only.
   C10 cannot be computed for the second-largest county from the parcel layer.
4. **Eight counties have no located parcel source** — Collin, Ellis, Hunt, Johnson, Kaufman,
   Parker, Rockwall, Wise.
5. **Water CCN uses `HAVE_THEIR_CENTER_IN`** — a parcel straddling a boundary is judged by its
   centroid. Fine for a screen, wrong for a site decision; revisit on the shortlist.
6. **25.20% acreage disagreement** (Tarrant, >5% published vs computed) belongs in the
   methodology report, not a log.
7. **Census API key** — free, instant, <https://api.census.gov/data/key_signup.html>.
   Blocks C01/C02.
8. **Fort Worth zoning** — still no authoritative service found.
9. D-001 – D-007 and D-011 still OPEN.

## Next 1–3 actions

1. Review the 138 candidates in `pro/DFW_DSG.aprx`; decide calibration.
2. **Part 2** — network dataset, service areas, OD cost matrix.
3. ERD and data dictionary are unblocked.

---

## Gotchas

**Screening and rasters**

- **Zone rasterization keeps only cells whose CENTRE is inside the zone.** At a coarse cell a
  narrow parcel measures as *absent*, not zero — 112 of 884 here (D-017). Set
  `raster_zonal.processing_cell_ft`. An unmeasurable metric is `Review`, so this never admits a
  bad parcel — it quietly fills the list with unscreened ones.
- **A raster written by `save()` has no statistics** — `.minimum`/`.maximum` are `None` until
  `CalculateStatistics`.
- **`MakeImageServerLayer` + `CopyRaster` can silently return a 1 × 1 raster.** Use
  `exportImage` with an explicit bbox and size, and assert the result is bigger than a stub.
- **3DEP gateway-times-out (~90s) on tiles well inside its declared 8000 px cap.** The cap is a
  limit on the answer, not a promise it can compute it. 1024 px tiles; retry on 504.
- **3DEP elevation is in METRES, EPSG:6584 x/y in US FEET** — without the z-factor every slope
  is understated by 3.28×.
- **MRLC publishes the NLCD coverage in EPSG:3857 and GeoServer cannot WRITE Pseudo-Mercator.**
  Subset in 4326, demand 5070 back with `outputCrs`.
- **`Intersect` with POINT output emits MULTIPOINT.** Inserting that into a point class fails as
  a bare `AttributeError: __len__` from inside `insertRow`. `MultipartToSinglepart` first.
- **Dissolve a class layer before `TabulateIntersection`** — overlapping polygons (NFHL floodway
  inside SFHA) sum past 100%.

**Ingest and services**

- **FEMA NFHL** 500s above `page_size` 250. **FWS wetlands** times out past `resultOffset` 2000
  — tile instead. ArcGIS REST `maxRecordCount` is 1,000; use `returnCountOnly` for totals.
- **`JSONToFeatures` has ~1–2s fixed overhead per call** — concatenate pages first.
- **ArcGIS Hub search is not an inventory.** It returned Buncombe County NC and the American
  Red Cross for Texas parcel queries. Always confirm the publishing organisation.
- **Check key uniqueness before choosing a `parcel_id`.** `TAXPIN` is the survey abstract tract
  (98.44% unique); `ACCOUNT` is the key. A plausible field name is not evidence.

**Geodatabase and Pro**

- Attribute rules need **GlobalIDs** first (`ERROR 002710`). Subtype fields must be **SHORT/LONG**.
- **A class with attribute rules cannot be written outside an edit session** — wrap inserts in
  `arcpy.da.Editor`. The session is also what makes the rules fire on insert.
- `arcpy.da.Describe()` does **not** expose topology rules — use `ExportXMLWorkspaceDocument`.
- `arcpy.mp` **cannot create** an `.aprx`; Pro 3.5 has no `CreateToolbox`.
- `Layer` has no `getExtent()` in Pro 3.5 — use `arcpy.Describe(fc).extent`.
- **`addDataFromPath` fails with "Possible credentials issue"** when the path omits the feature
  dataset — it is a path error, not an authentication one.

**Environment**

- `arcgispro-py3` is **read-only** — clone before installing. `pytest` lives in the ArcGIS env,
  not the system Python.
- PowerShell `Set-Content -Encoding utf8` **mangles UTF-8 punctuation** — edit text files in
  Python with explicit `encoding="utf-8"`.
- Long heredocs via Bash fail with `ENAMETOOLONG`; write files directly.
- **Piping a background job to `tail` hides all progress** until it exits — log to a file and
  watch that instead.
