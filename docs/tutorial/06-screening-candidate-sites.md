# Lesson 06 — Screening candidate sites

**Phase:** scope §5.1 / Week 4 · **Status:** 🔄 Track A performed and verified · Track B not yet performed
**Prerequisites:** Lesson 04 (parcels ingested), physical-filter layers loaded

---

## What you will end up with

`CandidateSites` populated for one county: every parcel that survives the physical hard filters,
each carrying the rule it would have failed next, a `sewer_status`, and a `run_id` — plus a
drop-off funnel that reconciles from the full parcel count down to the candidates.

## Why this step exists

Screening decides what gets measured properly. Everything after it — service areas, OD matrices,
eleven scored criteria — runs only on what survives here, so a filter that is wrong in either
direction is expensive. Too strict and the real answer never reaches scoring. Too loose and the
network solves get slower for no gain.

---

## Concepts — why this works

**The idea.** A screen is a sequence of cheap, defensible rejections that leaves a set small
enough to measure expensively. The order matters for cost but not for the outcome: acreage runs
first because a SQL predicate takes 758,633 parcels to under a thousand, and every spatial
measurement afterwards then runs on that small set instead of the county.

**Physical only, on purpose.** There is no zoning gate here (D-013). Zoning is unobtainable for
much of the study area — parcels carry none, coverage is city-by-city, and unincorporated Texas
land has no zoning by law. Gating on it would silently delete exactly the cheap highway-adjacent
greenfield a distribution centre would realistically buy. Industrial context is *scored* in
Part 3 (C11, C12) where uncertainty can be priced rather than being fatal.

**Why the funnel is sequential, not independent.** It is tempting to report "how many parcels
violate each rule". Those counts overlap and do not sum to anything. Applying filters in
sequence to the survivors, and attributing each parcel to the **first** rule it fails, produces
numbers that reconcile: the removals add up exactly to the drop from start to finish. That is
what makes the funnel usable for calibration — you can see which filter is actually doing the
work.

**The assumption being made.** That a threshold measured on a *whole parcel* is the right
question. A 300-acre parcel that is 25% in a floodplain may still have 200 buildable acres in
one contiguous block, and this screen judges it on the aggregate. That is a known
simplification; the alternative — computing the largest developable sub-polygon per parcel — is
a real piece of work and belongs after the shortlist exists, not before.

**Two approximations, both recorded rather than hidden:**

- **D-015, interchange proximity.** The scope asks for truck drive-time ≤ 15 min. There is no
  network dataset at screening time, and building one to sift a county would invert the
  pipeline. Straight-line distance stands in, with the radius *derived* from the drive-time
  threshold rather than typed: `15/60 × 35 mph ÷ 1.3 = 6.73 miles`. Dividing by circuity makes
  the radius deliberately smaller than the distance a 15-minute drive covers, because roads do
  not run straight — erring toward excluding the marginal rather than admitting the unreachable.
- **D-016, sewer CCN.** No statewide source exists. Rather than drop every parcel for want of a
  dataset, sewer is not applied as a filter, every candidate records
  `sewer_status = "Unknown - pending D-016 search"`, and the funnel reports the stage as
  **SKIPPED**.

**How it can go wrong quietly:**

- **A missing raster reads as a passing score.** If the slope raster does not cover a parcel, a
  naive `None <= 5` comparison in Python raises, but `0 <= 5` passes. Absent slope data is not
  evidence of gentle terrain — so an unmeasurable metric returns `Review`, not `Pass`.
  *Absent overlap* is different: no intersecting flood polygon genuinely does mean zero flood
  coverage, and that is treated as 0.
- **Overlapping class polygons inflate coverage past 100%.** NFHL floodway polygons sit inside
  SFHA polygons; `TabulateIntersection` sums overlapping class area. Dissolving the class layer
  first is what stops a parcel failing on geometry bookkeeping rather than flood risk.
- **A filter whose data never loaded silently passes everything.** If `Interchanges` is empty,
  every parcel has "no interchange distance" and sails through. The runner logs a warning per
  unavailable layer, and QA records the layer as `Skipped` rather than `Pass`.
- **Zone rasterization drops narrow parcels entirely.** `TabulateArea` and
  `ZonalStatisticsAsTable` rasterize each parcel and keep only cells whose *centre* falls inside
  it. At NLCD's native ~83.5 ft cell, a corridor-shaped parcel captures no centre and vanishes
  from the output table — absent, not zero. That reads as "unmeasurable" even though the raster
  covers the parcel perfectly well. This happened here, to 112 of 884 parcels (**D-017**).
  `_warn_if_patchy()` now flags any raster metric that covers under 98% of its zones.
- **The safe direction is still a wrong answer.** Every one of these failures pushes parcels to
  `Review`, never to a false `Pass` — so nothing bad gets admitted. It is still wrong: the list
  fills with parcels nobody screened, and they look exactly like candidates. Conservative and
  correct are not the same thing.

---

## Steps

### Track A — Automated (the tool)

```bash
python tools/ingest_physical_layers.py
```

```bash
python tools/screen_tarrant.py --reset
```

| Parameter | Value used | Why |
|---|---|---|
| `min_acres` | `80` | Scope Appendix B. Allows survey variance against the 90-acre target |
| `max_floodway_pct` | `0` | Regulatory floodway — no tolerance |
| `max_sfha_pct` | `20` | Some SFHA is tolerable on a large parcel |
| `max_wetland_pct` | `10` | Above this, mitigation cost and permitting dominate |
| `max_mean_slope_pct` | `5` | An 800,000 SF slab wants flat ground |
| `max_developed_pct` | `30` | Looking for greenfield, not redevelopment |
| `require_water_ccn` | `true` | Hard filter — the layer exists |
| `max_truck_min_to_interchange` | `15` | Converted to a 6.73-mile radius (D-015) |
| sewer | **SKIPPED** | D-016 — no source located |

**Config that drives this:** `config/screening.yaml` in full. There are no thresholds in code;
`tests/test_screening.py` asserts the scope defaults are the ones in force, so a silent
tightening fails CI.

**Real output — Tarrant, run `20260924_0020_screen`:**

```
   #  filter                            threshold   entering    removed   remaining
      parcels in county                              758,633          0     758,633
   1  acreage >= min_acres                     80    758,633    757,749         884
   2  floodway coverage                         0        884        151         733
   3  SFHA coverage                            20        733        131         602
   4  wetland coverage                         10        602         88         514
   5  mean slope                                5        514        113         401
   6  developed land cover                     30        401        184         217
   7  water CCN service                      True        217         62         155
   8  interchange proximity                6.7308        155         17         138
      sewer CCN service                   SKIPPED          -          -           -

  CANDIDATES WRITTEN: 138       by status: {'Pass': 137, 'Review': 1}
  QA: Pass 8  Warning 0  Fail 0
```

**Measured runtime.** Screening 5 min. The physical-layer ingest ahead of it took 54 min —
of which the 3DEP DEM alone was 15 min for 64 tiles.

**What the funnel says.** Acreage does 99.9% of the work; that is the whole reason it runs
first. After it, the two biggest cuts are **developed land cover (184)** and **floodway (151)** —
a distribution centre wants a large, flat, empty, unflooded parcel, and in a built-out urban
county the binding constraint is that large parcels tend to be either already built on or in
the floodplain. Interchange proximity removes only 17, which is worth knowing before trusting
it: at 6.73 miles in a county this dense, almost everything is already close enough, so D-015's
approximation is not what decides this list.

**One number to distrust.** Water CCN removes 62. That filter is `HAVE_THEIR_CENTER_IN`, so a
parcel straddling a service-area boundary is judged by its centroid. That is defensible for a
screen and wrong for a site decision; it gets revisited on the shortlist.

> **This run is the corrected one.** The first pass produced 180 candidates with 56 in `Review`,
> 55 of them because land cover came back unmeasurable on narrow parcels — a zone-rasterization
> artefact, not missing data. See **D-017**. If you re-run this yourself and get 180, check
> `raster_zonal.processing_cell_ft`.

### Track B — Manual (by hand in ArcGIS Pro)

> **Not yet performed.** Written from the tool's own steps, so treat it as a plan rather than a
> verified procedure.

1. **Select by attribute** on `Parcels`: `acres_published >= 80`. Export to a working layer —
   everything else runs on this small set.
2. **Pairwise Dissolve** `FloodZones_NFHL` filtered to `floodway_flag = 1`, then again to
   `sfha_flag = 1`. Dissolve *before* intersecting, or overlapping polygons double-count.
3. **Tabulate Intersection** (Analysis → Statistics) working layer × each dissolved layer,
   zone field `parcel_id`. Read `PERCENTAGE`.
4. Repeat step 2–3 for `Wetlands_NWI`.
5. **Zonal Statistics as Table** (Spatial Analyst) over `Slope_pct`, statistic `MEAN`. Set
   **Environments → Processing Cell Size to 30 ft** first, or narrow parcels return nothing
   (D-017).
6. **Tabulate Area** over `LandCover_NLCD`, Processing Cell Size again **30**, then compute
   developed % as `(VALUE_23 + VALUE_24) / total × 100`. Check the output row count against
   your input count — a parcel that produced no row is missing, not zero.
7. **Select Layer by Location** → `HAVE_THEIR_CENTER_IN` → `WaterCCN` to flag served parcels.
8. **Near** (Analysis → Proximity) working layer → `Interchanges`. `NEAR_DIST` is in US survey
   feet; divide by 5,280 for miles.
9. **Join** every result back on `parcel_id`, then **Select by Attribute** with the thresholds
   and export survivors to `CandidateSites`.
10. **Calculate Field** `sewer_status` = `"Unknown - pending D-016 search"`.

**Where this differs from Track A.** By hand you get one pass/fail per parcel with no record of
*which* rule rejected it, so there is no funnel — you would have to run each selection
separately and note the counts. The tool attributes every rejection to its first failing rule,
which is what makes the drop-offs reconcile.

---

## Verify it worked

| Check | How | Expect |
|---|---|---|
| Funnel reconciles | sum of `removed` | equals start minus final |
| CRS | `arcpy.da.Describe(fc)["spatialReference"]` | EPSG **6584** |
| `cand_id` unique | `SCR-DUPID` in `QAQC_Log` | 0 duplicates |
| Every candidate has `sewer_status` | `SCR-SEWER` | 100% populated |
| Candidate count | `SCR-BAND` | scope expects 60–200; a warning, not a failure |

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| Coverage percentages over 100 | Overlapping class polygons | Dissolve the class layer first |
| Everything passes a filter | That layer never loaded | Check the ingest summary; QA marks it `Skipped` |
| Candidate count is zero | A filter applied with no data behind it | Never apply a filter whose source is missing — record it as skipped (D-016) |
| Many candidates are `Review` for one metric | Zone rasterization dropped narrow parcels | Lower `raster_zonal.processing_cell_ft` (D-017) |
| A slope raster that is 1 × 1 | `MakeImageServerLayer` + `CopyRaster` returned a stub | Export via `exportImage` with an explicit bbox and size |
| Slopes all look impossibly gentle | z in metres, x/y in US feet | Pass the z-factor (3.28084) to `Slope` |
| `Objects in this class cannot be updated outside an edit session` | `CandidateSites` has attribute rules | Wrap the insert in `arcpy.da.Editor` |

---

## What this produced

| Output | Where | Feeds |
|---|---|---|
| `CandidateSites` | `Analysis/CandidateSites` | Parts 2 and 3 — service areas, OD, scoring |
| Funnel counts | console + `QAQC_Log` | calibration, methodology report §6 |
| `sewer_status` | on every candidate | D-016, shortlist review |

## Try it yourself

- Raise `min_acres` to 100 in `config/screening.yaml` and re-run. Watch which later filters
  stop mattering — that tells you which constraint is really binding.
- Set `max_sfha_pct` to 0 and see how much of the pool is flood-exposed at all.
- Change `circuity_factor` from 1.3 to 1.0 and watch the interchange radius grow from 6.73 to
  8.75 miles. That single assumption is worth understanding before trusting the count.

## Further reading

- `docs/DECISIONS.md` — **D-013** (physical-only), **D-015** (straight-line), **D-016** (sewer)
- Scope §5.1 and Appendix B — the thresholds and their origin
