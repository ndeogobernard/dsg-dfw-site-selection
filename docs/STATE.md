# STATE — live project snapshot

> Snapshot, not history. Overwrite this file at each checkpoint.
> Narrative belongs in `docs/SESSION_LOG.md`; decisions in `docs/DECISIONS.md`.

**Last updated:** 2026-09-24 · main · <https://github.com/ndeogobernard/dsg-dfw-site-selection>

---

## ⏸ Stopped here, by request

**Vertical slice Part 2 is complete. Part 3 (scoring) is deliberately not started.**

Open `pro/DFW_DSG.aprx`: the network dataset, the 138 candidates, their labour-shed
isochrones, the store network and the freight-reach bands are all on the map.

---

## Current milestone

**Week 5 of 8** (scope §11). Full tracker with exit criteria: **`docs/PLAN.md`**.

| Milestone | Status |
|---|---|
| W2 — geodatabase schema built via tool | ✅ |
| W3 — ETL and QA/QC tools written | ✅ |
| W3 — all layers loaded | 🔄 **Tarrant only**; 10 counties pending |
| W4 — screening tool + CandidateSites | ✅ 138 candidates |
| W5 — network dataset | ✅ **1,399,985 segments, 16 states, validated 7/7** |
| W5 — service areas + OD | ✅ 412 polygons, 19,152 OD pairs |
| W6 — scoring, scenarios, sensitivity | ⬜ Part 3, not started |
| W2 — ERD + data dictionary v1 | ⏸ deferred — schema is stable |

---

## Done this session

- **D-004 resolved** — OpenStreetMap via Geofabrik, not TxDOT RHiNo. RHiNo kept for validation.
- **`RoadNetwork_ND` built** from 1,399,985 OSM segments across 16 states and **validated on
  7 reference routes in both travel modes, 7/7 each**.
- **179 stores** compiled from OSM; **143 served** within 600 truck-minutes of the MSA centroid.
- **412 driving isochrones**, **4 freight-reach bands**, **19,152 OD pairs**.
- **D-018, D-019, D-020** recorded. Tests **207**, all arcpy-free.

## Network dataset — `RoadNetwork_ND`

| Property | Value |
|---|---|
| Source | OpenStreetMap via Geofabrik, 16 states, 3.8 GB (D-004) |
| Segments | **1,399,985** (1,157,005 long-haul + 242,980 MSA local) |
| Connectivity | **ANY_VERTEX** — OSM ways are not split at junctions |
| Elevation | NONE — vertex coincidence already encodes grade separation |
| Costs | `Miles`, `Minutes`, `TruckMinutes` (D-019) |
| Restrictions | `Oneway`, `TruckRestricted` |
| Build time | 14 s create + 124 s build |
| Licence | **ODbL 1.0 — attribution required on every map** (D-018) |

## Route validation — 7/7 in both modes

| Route | Driving | Truck | Ref |
|---|---|---|---|
| Fort Worth → Dallas | 32.6 mi / 29.9 min | 32.5 / 31.9 | 32 / 35 |
| Dallas → Austin | 194.8 / 163.2 | 194.8 / 180.8 | 195 / 180 |
| Dallas → Houston | 238.3 / 200.7 | 238.6 / 222.7 | 239 / 225 |
| Dallas → Oklahoma City | 204.1 / 172.9 | 205.0 / 192.3 | 206 / 185 |
| Dallas → Shreveport LA | 187.8 / 158.9 | 188.1 / 175.8 | 190 / 170 |
| Dallas → Little Rock AR | 319.8 / 263.6 | 319.8 / 296.1 | 319 / 285 |
| Dallas → Albuquerque NM | 649.7 / 545.3 | 646.8 / 602.6 | 647 / 570 |

**Distances land within 2% everywhere** — that is the strong signal, since distance depends only
on geometry and path choice. Times run 4–15% fast, correct for a free-flow network with no
traffic model. Truck is slower than Driving on every route. The four out-of-state routes solving
is the direct confirmation of D-004.

## Stage C outputs

| Output | Result |
|---|---|
| `Stores_DSG` | **179** within 600 mi (161 DSG, 10 Golf Galaxy, 5 House of Sport, 3 Public Lands) |
| Served set | **143 of 179** within 600 truck-min of the MSA centroid (min 14, median 248, max 594) |
| `ServiceAreas_Driving` | **412** polygons, 138 candidates × 15/30/45 min |
| `ServiceAreas_Truck` | **4** reach bands from the MSA centroid (D-020) |
| `OD_Cand_to_Stores` | **19,152** pairs; per candidate min 137, median 139, max 143 |

Stores by truck-time band from the MSA centroid: **≤60 min 20 · ≤120 min 1 · ≤240 min 22 ·
≤600 min 100 · beyond 36.** The gap between 60 and 120 minutes is real geography — the DFW metro,
then rural Texas, then the next metros.

---

## Blocked / needs decision

1. **User review of Part 2 before scoring.** Calibrate, or proceed to Part 3.
2. **`TAR-00758` is marooned.** Its label point snaps to *Perimeter Road*, an isolated 2.44-mile
   private, truck-restricted OSM stub that intersects **nothing**. Its driving service area caps
   at 2.44 minutes instead of 45, so C01–C03 would be meaningless for it. It still has 142 OD
   rows because the OD solver snapped it elsewhere. Decide: drop it, re-snap it, or carry it with
   a flag. `SA-REACH-FULL` now warns on this class of failure.
3. **D-016 — sewer CCN.** Still OPEN; every candidate carries `sewer_status = "Unknown"`.
4. **D-014 — Dallas needs a DCAD roll join.**
5. **Eight counties have no located parcel source.**
6. **Census API key** — blocks C01/C02 even though the service areas now exist.
7. **Travel modes are not on the network dataset.** arcpy cannot add one and the template
   property is ignored, so opening Pro and starting a Network Analyst layer by hand offers no
   named mode. The toolbox sets impedance and restrictions from config.
8. **Turn restrictions are not modelled** (D-004) — documented limitation, not a defect.
9. D-001 – D-003, D-005 – D-007, D-011 still OPEN.

## Next 1–3 actions

1. Review Part 2 in `pro/DFW_DSG.aprx`; decide on `TAR-00758`.
2. **Part 3** — criteria, three weighting scenarios, sensitivity, shortlist.
3. Census API key unblocks C01–C03 from the service areas already built.

---

## Gotchas

**Network Analyst**

- **`arcpy.nax` refuses to open a network with no travel modes**, arcpy has no tool to add one,
  and the `TravelModes` key in the template XML is **ignored** on import. Use the classic
  `arcpy.na.Make*Layer` tools, which take impedance and restrictions explicitly.
- **Call those tools with keyword arguments.** `hierarchy_settings` sits between `hierarchy` and
  `output_path_shape`, so a positional call shifts the output shape into the hierarchy slot and
  fails naming neither.
- Passing `NO_HIERARCHY` to a network with **no hierarchy attribute** is rejected outright.
- **arcpy cannot define network attributes.** Create a throwaway ND, export Esri's template with
  `CreateTemplateFromNetworkDataset`, patch the XML, recreate. Evaluator CLSIDs:
  constant `{318C4B91-F5D2-467A-996C-0AB51B0D8FF2}`, expression
  `{68055FC4-37D5-4BD0-81A5-CD177A29759C}`. Read them from your own export, never guess.
- **`ClassConnectivity`** in that XML: `1` = end vertex, `2` = any vertex.
- **A feature class can belong to only one network dataset** — delete the old ND first.
- **Classic NA names its output rows**: OD lines `"<origin> - <destination>"`, SA polygons
  `"<facility> : 0 - 30"`. That is how results map back to ids.
- **A service area that stops short is not an error.** Check the largest polygon against the
  largest break, or a marooned candidate passes silently.

**OSM**

- **OSM ways are not split at junctions**, so `END_POINT` connectivity shreds the network. Use
  `ANY_VERTEX`; crossing-without-a-shared-node then encodes grade separation for free.
- **YAML 1.1 parses a bare `no` as `False`** — `hgv: [no, ...]` silently stops matching the
  commonest truck prohibition. Quote the values.
- **Tiers overlap by default.** Extracting long-haul classes again inside the study area
  duplicated 121,147 ways into parallel edges. Subtract.
- **GDAL cannot iterate a state-sized PBF layer directly** — the OSM driver overflows its other
  layers. Use `VectorTranslate`.
- **Committing mid-iteration invalidates the SQLite cursor**, restarting the pass forever. Read
  into a plan, then write.
- **Pro's stock `osmconf.ini` does not promote `oneway`/`maxspeed`/`hgv`** to columns, and
  `addr:*` tags may not survive at all — read optional tags defensively.
- **77% of Texas `secondary` is `oneway=yes`.** Not a bug: one-way frontage roads.

**Screening and rasters**

- **Zone rasterization keeps only cells whose CENTRE is inside the zone** — a narrow parcel
  measures as *absent*, not zero (D-017). Set `raster_zonal.processing_cell_ft`.
- **A raster written by `save()` has no statistics** until `CalculateStatistics`.
- **`MakeImageServerLayer` + `CopyRaster` can silently return a 1 × 1 raster.** Use `exportImage`
  with an explicit bbox and size, and assert the result is bigger than a stub.
- **3DEP gateway-times-out (~90 s) well inside its declared 8000 px cap.** Tile at 1024 px.
- **3DEP elevation is in METRES, EPSG:6584 x/y in US FEET** — without the z-factor every slope is
  understated 3.28×.
- **MRLC publishes NLCD in EPSG:3857 and GeoServer cannot WRITE Pseudo-Mercator.** Subset in
  4326, demand 5070 with `outputCrs`.
- **`Intersect` with POINT output emits MULTIPOINT**, which a point class refuses as a bare
  `AttributeError: __len__`. `MultipartToSinglepart` first.
- **Dissolve a class layer before `TabulateIntersection`** — overlaps sum past 100%.

**Ingest, geodatabase, environment**

- **FEMA NFHL** 500s above `page_size` 250. **FWS wetlands** times out past `resultOffset` 2000.
- **ArcGIS Hub search is not an inventory** — confirm the publishing organisation.
- **Check key uniqueness before choosing a `parcel_id`** — `ACCOUNT`, not `TAXPIN`.
- Attribute rules need **GlobalIDs** (`ERROR 002710`); subtype fields must be **SHORT/LONG**; a
  class with attribute rules cannot be written outside `arcpy.da.Editor`.
- **`GlobalID` makes bulk `Append` slow** — 1.4M road rows took 80 minutes at ~290 rows/s.
- **`addDataFromPath` fails with "Possible credentials issue"** when the path omits the feature
  dataset. It is a path error, not authentication.
- `arcgispro-py3` is **read-only**; `pytest` lives there, not in the system Python.
- **Piping a background job to `tail` hides all progress** until it exits — log to a file.
