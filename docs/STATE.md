# STATE — live project snapshot

> Snapshot, not history. Overwrite this file at each checkpoint.
> Narrative belongs in `docs/SESSION_LOG.md`; decisions in `docs/DECISIONS.md`.

**Last updated:** 2026-09-23 · main · <https://github.com/ndeogobernard/dsg-dfw-site-selection>

---

## ⏸ Stopped here, by request

**Tarrant is ingested. The other ten counties are deliberately not.** Open
`pro/DFW_DSG.aprx` to see 758,633 real parcels on the map before deciding what comes next.

---

## Current milestone

**Week 3 of 8** (scope §11). Full tracker with exit criteria: **`docs/PLAN.md`**.

| Milestone | Status |
|---|---|
| W2 — geodatabase schema built via tool | ✅ |
| W3 — ETL and QA/QC tools written | ✅ tools 2 and 3 |
| W3 — all layers loaded | 🔄 **Tarrant only**; 10 counties pending, other sources untouched |
| W2 — ERD + data dictionary v1 | ⏸ deferred — schema is now stable enough to write them |

---

## Done this session

- **Schema reconciled** against verified source data and rebuilt clean — D-008, D-009, D-013.
  12 domains, 6 attribute rules, 24 criterion columns, `Parcels` subtypes on `zoning_conf_st`.
- **Tools 2 and 3** — `IngestAndStandardize`, `RunQAQC`. Decisions live in pure arcpy-free
  functions; the arcpy half only executes them.
- **All 10 remaining CADs probed.** None ingested. Only Tarrant is `verified`.
- **Tarrant pilot: 758,633 / 758,633 loaded. 10 Pass, 1 Warning, 0 Fail.**
- `docs/tutorial/04-ingest-and-qaqc.md` filled from the real run (Track B still unperformed).
- Tests **26 → 85**, all arcpy-free. Both tool spokes re-synced and pushed, CI green.

## Pilot results — Tarrant

| Check | Result |
|---|---|
| Features loaded | **758,633** — exactly the source count |
| CRS | EPSG:6584 ✅ |
| Null / invalid geometry | 0 / 0 ✅ |
| Duplicate `parcel_id` | **0** ✅ (after the ACCOUNT fix) |
| Null published acreage / land value | 0.00% / 0.00% ✅ |
| Zero land value | **8.54%** — exempt/ROW, flagged `ZeroExempt`, excluded from C10 |
| Acreage disagreement > 5% | ⚠️ **25.20%** (191,192 parcels) |
| Attribute rules fired on insert | `acres` 100%, `land_val_per_acre` 100%, `acres_delta_pct` 84% |

Runtime **93 min** — 7 min downloading, the rest conversion and the row-by-row append.
`acres_published ≥ 80` → **884 parcels**, matching the server-side recon count exactly.

## CAD status — only Tarrant is cleared

| Mode | Counties |
|---|---|
| **AUTO, verified** | Tarrant (758,633) |
| **AUTO, skeleton** | Denton (384,308, 71 fields, has `cad_zoning`); Dallas (695,446, **5 fields**) |
| **MANUAL, not located** | Collin, Ellis, Hunt, Johnson, Kaufman, Parker, Rockwall, Wise |

---

## Blocked / needs decision

1. **D-014 — Dallas needs a DCAD roll join.** `CurrentDcadParcels` is geometry + account only;
   no land value at all. C10 cannot be computed for the second-largest county from the parcel
   layer. Four options recorded; recommendation is to obtain the roll and join on `GIS_Acct`.
2. **Eight counties have no located parcel source.** They may need hand-fetching. Their
   portals resolve but whether they publish a parcel layer is unconfirmed.
3. **The 25.20% acreage disagreement needs a view.** D-008 screens on the published figure;
   that is still the right call, but a quarter of parcels disagreeing by >5% belongs in the
   methodology report rather than in a log.
4. **Census API key** — free, instant, <https://api.census.gov/data/key_signup.html>.
   Blocks C01/C02 and the C24010 block-group question.
5. **Fort Worth zoning** — still no authoritative service found.
6. D-001 – D-007 and D-011 still OPEN.

---

## Next 1–3 actions

1. Look at Tarrant in `pro/DFW_DSG.aprx`, then decide: more counties, or move to the network
   dataset and screening with one county as a vertical slice.
2. Resolve **D-014** — it decides whether Dallas can be scored at all.
3. ERD and data dictionary are now unblocked; the schema has met real data.

---

## Gotchas

- Attribute rules need **GlobalIDs** first (`ERROR 002710`). Subtype fields must be **SHORT/LONG**.
- **A class with attribute rules cannot be written outside an edit session** — wrap inserts in
  `arcpy.da.Editor`. The session is also what makes the rules fire on insert.
- **Check key uniqueness before choosing a `parcel_id`.** `TAXPIN` is the survey abstract tract
  (98.44% unique, up to 8 parcels per tract); `ACCOUNT` is the key. A plausible field name is
  not evidence.
- **`JSONToFeatures` has ~1–2s fixed overhead per call** — concatenate pages first.
- ArcGIS REST `maxRecordCount` is 1,000 — paging is mandatory; use `returnCountOnly` for totals.
- **ArcGIS Hub search is not an inventory.** It returned Buncombe County NC and the American
  Red Cross for Texas parcel queries. Always confirm the publishing organisation.
- `arcpy.da.Describe()` does **not** expose topology rules — use `ExportXMLWorkspaceDocument`.
- `arcpy.mp` **cannot create** an `.aprx`; Pro 3.5 has no `CreateToolbox`.
- `Layer` has no `getExtent()` in Pro 3.5 — use `arcpy.Describe(fc).extent`.
- `arcgispro-py3` is **read-only** — clone before installing.
- PowerShell `Set-Content -Encoding utf8` **mangles UTF-8 punctuation** — edit text files in
  Python with explicit `encoding="utf-8"`.
- Long heredocs via Bash fail with `ENAMETOOLONG`; write files directly.
