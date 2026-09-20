# Decision log

Append-only ADR-lite record of project decisions. **Never edit or delete an existing entry.**
To change a decision, append a new one that names the entry it supersedes.

Each entry carries a status:

| Status | Meaning |
|---|---|
| `OPEN` | Not yet decided. Blocks the work that depends on it. |
| `DECIDED` | Settled. Rationale recorded. |
| `SUPERSEDED` | Replaced by a later entry, which is named in the entry. |

A `[VERIFY]` or `[DECISION]` marker in the scope is **not resolved** until it appears here with a
status other than `OPEN`. Every `DECIDED` entry must also be reflected in the methodology report
(scope §9).

---

## D-001 · OMB MSA definition for the study area

- **Date raised:** 2026-09-19
- **Status:** `OPEN`
- **Scope ref:** §2.1 `[VERIFY current OMB MSA definition]`

**Question.** Which OMB delineation defines the Dallas–Fort Worth–Arlington MSA for this study,
and does the 11-county list hold?

**Findings so far.** The scope's 11 counties — Collin, Dallas, Denton, Ellis, Hunt, Johnson,
Kaufman, Parker, Rockwall, Tarrant, Wise — match the **2023 OMB delineation**. Hood and Somervell
were removed from the MSA in that update and are correctly absent. Encoded in
`config/sources.yaml → study_area.counties` and asserted by `tests/test_schema.py`.

**Remaining to close.** Confirm against the TIGER/Line CBSA file at the vintage actually
downloaded, and confirm the CBSA code `19100`. Record the delineation year used.

**Alternatives.** Use the older 13-county definition for comparability with pre-2023 published
market research — rejected unless a specific comparison requires it, since it would misstate the
current market.

---

## D-002 · Analysis CRS — EPSG:6584 vs EPSG:2276

- **Date raised:** 2026-09-19
- **Status:** `OPEN` (strongly leaning 6584; verification already done)
- **Scope ref:** §2.3 `[VERIFY]`

**Question.** NAD83(2011) StatePlane Texas North Central FIPS 4202 US ft (**EPSG:6584**) or
NAD83 StatePlane Texas North Central FIPS 4202 ft (**EPSG:2276**)?

**Findings so far.** 6584 verified present and correct in ArcGIS Pro 3.5, reporting as
`NAD_1983_2011_StatePlane_Texas_North_Central_FIPS_4202_FtUS`, linear unit US Feet. It is the
current realization and the better default for data published in the last decade. Implemented
throughout: `config/schema.yaml → meta.crs`, and the geodatabase is already built in it.

**Remaining to close.** Confirm the datum transformation to apply for each source arriving in
NAD83 (1986) or WGS84, and record it per source in `DataSourceRegistry.transformation`. The
choice only becomes consequential at the transformation step; sub-metre differences do not affect
any screening threshold or criterion in this study.

**Alternatives.** EPSG:2276 — acceptable per scope, and marginally simpler if most sources arrive
on the 1986 datum. Rejected as the default because it discards the 2011 realization for no
analytical gain.

---

## D-003 · Store sourcing method, served-set rule, and store count

- **Date raised:** 2026-09-19
- **Status:** `OPEN`
- **Scope ref:** §2.2 `[DECISION: retain all stores within 10-hour truck time as served set; record the count]`

**Question.** Three sub-decisions: (a) compile stores from the dicks.com locator or from OSM;
(b) confirm the served set = stores within a 10-hour truck drive of the MSA centroid;
(c) record the resulting count.

**Findings so far.** `config/sources.yaml → S21` currently specifies
`method: locator_then_osm_validate` — compile from the locator, validate against OSM — with the
Census Geocoder as primary geocoder and a minimum geocode score of 90. `network.yaml` sets the
OD cutoff to 600 minutes. **None of this has been executed**, so the served-store count is unknown.

**Remaining to close.** Execute the compilation, record the snapshot date and the count of stores
in the 600-mile search radius and in the served set, and confirm which banners are included
(DICK'S, Golf Galaxy, Public Lands, House of Sport).

**Alternatives.** OSM-only — faster and cleanly licensed, but brand coverage is incomplete and
would understate the network. Locator-only without OSM validation — no independent check on
completeness.

---

## D-004 · Network dataset source — TxDOT RHiNo vs OpenStreetMap

- **Date raised:** 2026-09-19
- **Status:** `OPEN`
- **Scope ref:** §4.6 `[DECISION: document which was used]`

**Question.** Build `RoadNetwork_ND` from TxDOT Roadway Inventory (RHiNo, S03), from the
Geofabrik OSM Texas extract (S04), or from a hybrid.

**Findings so far.** `config/network.yaml` sets `source_priority: [S03, S04]` — RHiNo primary,
OSM for gap fill. Neither has been downloaded, so neither has been inspected.

**Remaining to close.** Confirm RHiNo carries usable truck-restriction attributes. Scope §14
anticipates it may not, in which case the functional-class fallback in
`network.yaml → truck_restriction_rule` applies (currently restricting class 7 / local only).
Also confirm RHiNo's DFW coverage includes local streets adequate for 15-minute labor-shed
service areas; if it is arterial-biased, OSM may be the better primary despite the licensing
overhead. Validate 20 sample routes against AGOL routing per §14.

**Alternatives.** OSM primary — richer local-street coverage and explicit `hgv` tags, but ODbL
attribution obligations propagate to every published map. Hybrid — most accurate, most work,
hardest to document reproducibly.

---

## D-005 · Intermodal terminal list

- **Date raised:** 2026-09-19
- **Status:** `OPEN`
- **Scope ref:** §5.2 `[VERIFY list]`

**Question.** Which intermodal facilities constitute the C06 destination set?

**Findings so far.** The scope names BNSF Alliance, UP Dallas Intermodal Terminal, DFW Airport
cargo, and Fort Worth Alliance Airport — explicitly flagged `[VERIFY]`, i.e. not asserted as
complete. `config/sources.yaml → S06` points at USDOT BTS NTAD and carries a note not to assume
the list is exhaustive.

**Remaining to close.** Derive the list from NTAD rather than from the scope's prose, filter to
facilities genuinely relevant to a retail DC (rail intermodal and air cargo; exclude marine and
pipeline), and record the final set with the selection rule. C06 rankings are sensitive to
omissions — a missing terminal can move candidates.

**Alternatives.** Use the scope's four named facilities as-is — faster, but unverified and
likely incomplete. Include every NTAD freight facility without filtering — defensible but dilutes
the criterion with facilities no retail DC would use.

---

## D-006 · Optional scope — go / no-go

- **Date raised:** 2026-09-19
- **Status:** `OPEN`
- **Scope ref:** §5.3 (C12), §7.3 (MS03), §7.4 (Experience Builder), §4.1 (PostGIS), §14 (time risk)

**Question.** Which optional items are in scope? Scope §14 flags the 8-week part-time timeline as
tight and directs prioritising the pipeline and shortlist first.

**Items.**

| Item | Ref | Cost | Note |
|---|---|---|---|
| Lightcast criterion **C12** | §5.3 | Low build, gated on trial access | Requires rebalancing **all three** weight scenarios and documenting the change. Do not enable late. |
| **MS03** County Atlas map series | §7.3 | Low — reuses the MS01/MS02 machinery | Cheapest of the four to add. |
| **Experience Builder** wrapper | §7.4 | Medium | Presentation only; StoryMap + dashboard already cover §8. |
| **PostGIS** replica + DDL | §4.1 | High | Strongest signal for the *standalone geodatabase* deliverable — demonstrates enterprise/multi-user design beyond a file GDB. |

**Remaining to close.** Decide at the Week 5 checkpoint, once the pipeline's true runtime is
known. Deciding earlier risks committing to work the schedule cannot absorb; deciding later
wastes the option.

**Recommendation on current information.** MS03 yes (near-free). PostGIS yes *if* the
geodatabase project is meant to stand on its own as a portfolio piece. C12 only if trial access
arrives before scoring is finalised. Experience Builder no — lowest marginal value.

---

## D-007 · Model validation against the realized siting decision

- **Date raised:** 2026-09-19
- **Status:** `OPEN` — proposed addition, not in the scope as written
- **Scope ref:** would extend §13 (acceptance criteria) as a new §13.7

**Question.** Should the study report where the **actual** announced DICK'S DFW site ranks in the
model?

**Rationale.** Per the scope's own Appendix A, the DC was announced publicly in Aug 2024, so a
real outcome exists. A model that places the realized site in its top five is a far stronger
portfolio claim than one evaluated only against its internal logic. If the site ranks poorly,
that is equally publishable: it isolates exactly what the model does not capture — incentives,
existing entitlements, build-to-suit availability, assembled-land control — which §14 already
lists as non-modeled factors.

**Cost.** Low. One additional site lookup, one rank check, one short report subsection.

**Risk.** Hindsight bias — the analyst knows the answer before scoring. Mitigated by fixing all
weights and thresholds *before* the realized site is located in the candidate set, and by
recording the commit hash of the run that did so.

**Alternatives.** Omit it — keeps the study purely prospective and avoids any suggestion of
tuning toward a known answer. Defensible, but leaves clear evidential value unused.

---

> **Numbering note.** D-008 and D-009 are reserved for the two reconnaissance decisions (C10
> land-cost path; zoning strategy) and are appended after this entry, since the reconnaissance
> ran after the Pro project was stood up. The log is append-only, so entries sit in the order
> they were written rather than in numeric order.

---

## D-010 · Versioning the ArcGIS Pro project (`.aprx`) in git

- **Date raised:** 2026-09-19
- **Status:** `DECIDED`
- **Scope ref:** §6.2 (repository layout), §7 (visualization deliverables)

**Decision.** Commit `pro/DFW_DSG.aprx` and `pro/DFW_DSG.atbx` to the repository as periodic
snapshots, with **store relative paths to data sources enabled**, and treat the project as
**regenerable** from `tools/setup_pro_project.py` rather than as hand-built state.

**Rationale.**

An `.aprx` is a **binary** artifact — a zip containing CIM JSON — with three consequences that
shape how it must be handled:

1. **No meaningful diff.** `git diff` on an `.aprx` is noise. A reviewer cannot see what changed
   between two commits, so the commit message has to carry that information.
2. **No merge.** Two people editing the project on separate branches produce a conflict git
   cannot resolve. Whichever side is not chosen loses its work entirely. Only one person edits
   the project at a time, and the commit says what changed.
3. **It stores paths, not data.** The project references the geodatabase; it does not contain
   it. A fresh clone therefore has a project whose layers point at a geodatabase that does not
   exist yet, which is why the README states plainly that **BuildGeodatabaseSchema must run
   first**.

Relative paths are enabled so the repo survives being cloned to a different machine or folder.
Verified in the saved file: `"pathSaveRelative": true`, with the default toolbox stored as
`.\DFW_DSG.atbx` and the Python toolbox as `..\toolbox\LocationIntelligence.pyt`.

**Known limitation, accepted.** The geodatabase is stored as an **absolute** path
(`C:\GIS\dsg-dfw\data\gdb\DFW_DSG_SiteSelection.gdb`) because it lives outside the repository
tree by design — bulk data is kept off the user-profile folder. Relative-path storage cannot
help across unrelated roots. Anyone cloning this repo to a different layout must either
reproduce the `config/paths.yaml` locations, set `DSG_GDB`, or re-run
`tools/setup_pro_project.py --force`, which rewrites the project from local config. The
regeneration script is what makes this acceptable rather than a trap.

**Implementation notes worth keeping.** `arcpy.mp.ArcGISProject` opens an existing project; it
cannot create one. The project is therefore seeded from the blank `.aprx` that Pro ships at
`Resources\ArcToolBox\Services\routingservices\data\Blank.aprx`. That template references a
`Blank.atbx` and `Blank.gdb` that are **not** shipped beside it, so both entries are replaced
rather than inherited. A project must have a valid default toolbox — `updateToolboxes` raises
*"No valid default toolbox was set"* otherwise — and Pro 3.5's arcpy has no `CreateToolbox`
tool, so `tools/setup_pro_project.py` writes an empty `.atbx` directly (it is a zip holding a
`toolbox.content` manifest and a `toolbox.content.rc` string table).

**Alternatives considered.**

- *Gitignore the `.aprx` entirely and rebuild it every time.* Cleanest history, but the project
  will eventually hold layouts, symbology, and a network dataset that are genuinely authored by
  hand in Pro and cannot be scripted faithfully. Losing those is worse than carrying a binary.
- *Store only a `.aprx`-adjacent export (map files / `.lyrx` / `.pagx`).* Diffable and worth
  doing **in addition** once layouts exist — §7.1 already calls for `layouts/LI_Template.pagx`.
  It is not a substitute, because no export round-trips a whole project.
- *Git LFS.* Overkill at ~9 KB. Revisit only if the project grows large enough to bloat clones.
