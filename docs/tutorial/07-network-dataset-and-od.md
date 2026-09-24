# Lesson 07 — The routing network, service areas and the OD matrix

**Phase:** scope §4.6 / §5.2 · Week 5 · **Status:** 🔄 Track A performed and verified · Track B not yet performed
**Prerequisites:** Lesson 06 (CandidateSites exists), Network Analyst licence

---

## What you will end up with

`RoadNetwork_ND` — a routable network dataset covering sixteen states — plus the store set it
serves, driving isochrones around every candidate, a freight-reach map, and a table of truck
drive times from each candidate to each served store.

## Why this step exists

This is the scope's **#1 risk** (§14), and it is the right thing to be nervous about. Everything
downstream is measured on this network: if it is disconnected, every drive time is wrong; if the
one-way logic is inverted, routes are wrong in a way that still looks plausible; if a state is
missing, the analysis silently answers a smaller question than the one asked.

---

## Concepts — why this works

**A network dataset is a graph with rules.** Edges come from a line feature class. What makes it
routable rather than merely drawn is the attributes: a **cost** the solver minimises, and
**restrictions** that forbid traversal. Everything else — service areas, OD matrices, closest
facility — is one of those two questions asked differently.

**Choosing the source is an analytical decision, not a preference.** D-004 compared TxDOT RHiNo
against OpenStreetMap by measuring both. RHiNo turned out to have posted speed on **30.7%** of
segments and one-way on **0.0%** — the `DIR_TRAV` column exists and is entirely empty. But the
decisive fact was geographic: the served set spans a 10-hour truck drive across **sixteen
states**, and RHiNo is Texas only. A Texas-only network cannot compute a drive time to a store in
Oklahoma City *at all*. Attribute quality was the question everyone expected to matter; extent
was the question that actually decided it.

**Connectivity policy has to match how the source is cut.** GDAL returns whole OSM ways, not ways
split at every junction. With `END_POINT` connectivity, two ways join only where one *ends* on
the other's endpoint — a cross-street meeting a highway mid-way would not connect, and the
network shreds into fragments. `ANY_VERTEX` connects wherever they share a vertex, which is
exactly how OSM encodes a real junction. And because ways that merely *cross* — an overpass —
share no vertex, **vertex coincidence already encodes grade separation**. No elevation field is
needed. Get this wrong and the network still builds, still solves short routes, and quietly fails
on long ones.

**One cost cannot serve two travel modes.** Scope §4.6 asks the Truck mode to use "impedance
`Minutes`" and simultaneously to cap truck speeds below general traffic. Those contradict: either
`minutes` holds free-flow time and the caps do nothing, or it holds capped time and the *Driving*
15/30/45-minute labour-shed isochrones are computed at truck speeds and come out far too small.
D-019 makes truck time a second cost attribute. The failure mode this avoids is the quiet one —
nothing errors, the workforce catchments are just wrong.

**Two tiers, because the alternative does not finish.** Full street detail across sixteen states
is tens of millions of edges to answer a question about 10-hour truck routes. The long-haul tier
carries motorway through secondary everywhere; the local tier adds residential detail only over
the MSA, where the 15-minute labour-shed areas need it. This is a modelling assumption and is
recorded as one: a route that would genuinely prefer a rural lane between two states is not
representable. For freight reach that is not a real case.

**How it can go wrong quietly:**

- **A disconnected network still solves short routes.** Validation must include routes that cross
  the seams — four of the seven reference routes cross a state line for exactly this reason.
- **Inverted one-way logic produces plausible routes.** `Oneway` must block *along*-digitized when
  the value is `TF` and *against*-digitized when it is `FT`. Swap them and every one-way street is
  reversed; the solver reports success and the times are only slightly off.
- **YAML turns `no` into `False`.** `hgv: [no, destination]` parses as `[False, "destination"]`,
  so `hgv=no` — the commonest truck prohibition in OSM — stops matching and trucks are routed onto
  roads explicitly closed to them. Caught here by a test, not by reading.
- **Duplicate edges do not error.** Extracting the long-haul classes again inside the study area
  put 121,147 OSM ways into the network twice, as parallel edges between the same junctions.
  Routing still works; the network is just silently wrong.
- **A missing store looks like an unserved market.** OSM's record of a retail chain is
  volunteer-contributed. The store count is a floor, not a census, and must be reported that way.

---

## Steps

### Track A — Automated (the tools)

```bash
python tools/ingest_roads.py --download-only
```

```bash
python tools/ingest_roads.py --extract-only
```

```bash
python tools/ingest_roads.py --load-only
```

```bash
python tools/run_network_analysis.py --validate --stores --stage-c
```

| Parameter | Value used | Why |
|---|---|---|
| source | OSM via Geofabrik, 16 states | D-004 — RHiNo cannot leave Texas |
| extent | 600 mi geodesic of MSA centroid | scope §2.2 store radius; computed via TIGERweb |
| connectivity | `ANY_VERTEX` | OSM ways are not split at junctions |
| elevation | `NONE` | vertex coincidence already encodes grade separation |
| `Minutes` | `miles / posted-or-default mph × 60` | Driving impedance |
| `TruckMinutes` | `miles / capped mph × 60` | Truck impedance (D-019) |
| truck speed caps | 65 freeway / 45 arterial / 25 local | scope §4.6 |
| `Oneway` | blocks `TF` along, `FT` against | opposite by direction |
| `TruckRestricted` | OSM `hgv`/`access`, else class 7 | D-004 — no free source has real restrictions |
| SA breaks, Driving | 15 / 30 / 45 min | scope §5.2 |
| truck reach bands | 60 / 120 / 240 / 600 min | D-020 — from the MSA centroid |
| OD cutoff | 600 min | 10-hour single-driver day |

**Measured results.**

| Step | Result | Runtime |
|---|---|---|
| Download | 16 extracts, 3.8 GB | 7 min |
| Extract | 1,399,985 segments (1,157,005 long-haul + 242,980 local) | 33 min |
| Load into `Roads` | 1,399,985 features | 80 min |
| Build `RoadNetwork_ND` | 5 attributes, ANY_VERTEX | 14 s create + 124 s build |
| Store set | 179 stores, 143 served | 18 min |

**Route validation — 7/7 solved in both modes, all within ±35%:**

```
  route                        miles   ref    minutes   ref   verdict
  Fort Worth -> Dallas          32.6    32      29.9     35   ok  (+2% mi, -15% min)
  Dallas -> Austin             194.8   195     163.2    180   ok  (-0% mi,  -9% min)
  Dallas -> Houston            238.3   239     200.7    225   ok  (-0% mi, -11% min)
  Dallas -> Oklahoma City      204.1   206     172.9    185   ok  (-1% mi,  -7% min)
  Dallas -> Shreveport LA      187.8   190     158.9    170   ok  (-1% mi,  -7% min)
  Dallas -> Little Rock AR     319.8   319     263.6    285   ok  (+0% mi,  -8% min)
  Dallas -> Albuquerque NM     649.7   647     545.3    570   ok  (+0% mi,  -4% min)
```

Read this carefully rather than just noting the passes. **Distances are within 2% everywhere** —
that is the strong signal, because distance depends only on geometry and path choice, with no
speed assumptions in it. **Times are uniformly 4–15% fast**, which is what a free-flow network
without traffic, signals or stops should do. A network that was *slow*, or whose errors had no
consistent sign, would be the worry.

### Track B — Manual (by hand in ArcGIS Pro)

> **Not yet performed.** Written from the tools' own steps.

1. Download the state `.osm.pbf` extracts from `download.geofabrik.de`.
2. **Data → Conversion → Quick Import** (Data Interoperability) or `ogr2ogr` to read the `lines`
   layer, filtering `highway IN (...)`. Pro has no native `.osm.pbf` reader; the extension or
   GDAL is required either way.
3. **Project** to EPSG:6584, then **Merge** the per-state layers into one `Roads`.
4. **Calculate Field** for `func_class`, `speed_mph`, `oneway`, `truck_restrict`, `minutes`,
   `truck_speed_mph`, `truck_minutes`.
5. **Catalog → right-click the feature dataset → New → Network Dataset.** In the wizard: choose
   `Roads` as the source, set connectivity to **Any Vertex**, add `Miles`, `Minutes` and
   `TruckMinutes` as Cost attributes and `Oneway` and `TruckRestricted` as Restriction
   attributes, giving each a field evaluator. Define **Driving** and **Truck** travel modes.
6. **Network Dataset → Build.**
7. **Analysis → Network Analysis → Service Area**, add candidate centroids as facilities, set
   cutoffs 15 30 45, solve.
8. **Analysis → Network Analysis → Origin-Destination Cost Matrix**, candidates as origins,
   served stores as destinations, cutoff 600, solve, export the Lines table.

**Where this differs from Track A — and it is the biggest gap in this tutorial.** The wizard in
step 5 can define **named travel modes**; `arcpy` cannot. There is no geoprocessing tool to add a
travel mode to an existing network dataset, and the `TravelModes` property in the exported
template XML is ignored on import. So the automated path builds the network by patching Esri's
own exported template — which works for attributes and connectivity — and then drives the solvers
through the classic `arcpy.na.Make*Layer` tools, which take impedance, restrictions and U-turn
policy as explicit arguments instead. The modelling is identical and arguably more legible in
config than hidden behind a mode name. The practical consequence: **open this network in Pro and
the travel-mode dropdown will be empty.** Set impedance and restrictions by hand, or use the
toolbox.

---

## Verify it worked

| Check | How | Expect |
|---|---|---|
| Attributes exist | `arcpy.Describe(nd).attributes` | Miles, Minutes, TruckMinutes, Oneway, TruckRestricted |
| Network connects across states | reference routes | 7/7 solve |
| Times are sane | vs reference figures | within ±35%, and *fast* not slow |
| Truck ≥ Driving | compare the two runs | truck slower on every route |
| No duplicate edges | `road_id` overlap between tiers | 0 |
| Every candidate has areas | `SA-BREAKS` | polygons = candidates × breaks |
| Every candidate reaches a store | `OD-COVER` | 0 unreachable |
| No impossible speeds | `OD-SPEED` | 0 pairs above 80 mph average |

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `Network has no travel modes` | `arcpy.nax` needs named modes | use the classic `arcpy.na.Make*Layer` tools |
| `Cannot set input into parameter hierarchy_settings` | positional args shifted | call with keyword arguments |
| Long routes fail, short ones work | network disconnected at a seam | check connectivity is `ANY_VERTEX` |
| Routes go the wrong way down one-ways | `Oneway` directions not opposite | `TF` blocks along, `FT` blocks against |
| Trucks routed onto prohibited roads | YAML parsed `no` as `False` | quote the values |
| Network twice the expected size | tiers overlap | subtract long-haul classes from the local tier |
| `The network source participates in multiple network datasets` | an old ND still exists | delete it before creating another |
| Service area solve takes forever | detailed polygons × many facilities | batch, or use simple polygons where detail does not matter |

---

## What this produced

| Output | Where | Feeds |
|---|---|---|
| `Roads` | `Transportation/Roads` | the network dataset |
| `RoadNetwork_ND` | `Transportation/` | every network analysis |
| `Stores_DSG` | `Market/Stores_DSG` | demand points |
| `StoreServiceSet` | table | served-set provenance |
| `ServiceAreas_Driving` | `Analysis/` | C01–C03 workforce criteria |
| `ServiceAreas_Truck` | `Analysis/` | freight-reach map (D-020) |
| `OD_Cand_to_Stores` | table | store-accessibility criterion |

## Try it yourself

- Set `connectivity` to `END_POINT` and rebuild. Watch the long routes stop solving while the
  short ones still work — that is what a shredded network looks like from the inside.
- Change `default_speeds_mph` for class 1 from 70 to 55 and re-run validation. The distances will
  not move at all and the times will move a lot: that separation is why distance is the better
  check of geometry.
- Remove `Oneway` from the Truck mode's restrictions and re-run. Most times barely change, which
  is the point — a restriction error is not visible in aggregate statistics.

## Further reading

- `docs/DECISIONS.md` — **D-004** (source), **D-018** (ODbL), **D-019** (truck cost), **D-020** (freight reach)
- Scope §4.6, §5.2, §14 risk register
- `© OpenStreetMap contributors, ODbL 1.0` — attribution is required on every map made from this network
