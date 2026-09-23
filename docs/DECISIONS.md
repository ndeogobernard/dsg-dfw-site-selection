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

---

## D-008 · C10 land-cost data path

- **Date raised:** 2026-09-19
- **Status:** `DECIDED` 2026-09-22 — recommendation accepted in full. Implementation recorded in
  **D-008-R** below; the original analysis is preserved unchanged.
- **Scope ref:** §5.3 C10, §3 S01, §14 (parcel-data risk)
- **Evidence:** `docs/recon/RECON_findings.md` §1

**Question.** Do appraised values ship with parcel geometry, or do they live in a separate
appraisal-district tabular roll that must be joined — which would add a pipeline step that the
design does not currently have?

**Finding — they ship with the geometry, at least in Tarrant.** Verified against the live
`TADParcels` service over all 758,633 parcels:

| | |
|---|---:|
| `LAND_VALUE > 0` | 693,826 (91.5%) |
| `LAND_VALUE = 0` | 64,806 (8.5%) |
| `LAND_VALUE IS NULL` | 1 |
| `TOTAL_VALU > 0` | 742,055 (97.8%) |
| `LAND_ACRES IS NULL` | 23 |

**No CAD roll join is required.** The feared design gap does not exist for Tarrant. `LAND_VALUE`
and `LAND_ACRES` together give `land_val_per_acre` directly, which is all C10 needs.

**Recommendation.**

1. **Source C10 from the parcel layer's own value fields.** Add no join step.
2. **Exclude `LAND_VALUE = 0` parcels from C10 normalization** and record them as
   `screen_status = Review` rather than scoring them. Those 8.5% are tax-exempt, right-of-way,
   and government parcels. Treated as zero they would normalize to the *best possible* land-cost
   score and dominate the ranking with land that is not for sale.
3. **Prefer the CAD service per county over the TxGIO StratMap mosaic**, and write an explicit
   `field_map` per county in `config/sources.yaml`. The guessed `_default` map is wrong for
   Tarrant and there is no reason to expect a shared schema across 11 independent districts.
4. **Keep the CAD-published `LAND_ACRES` as `acres_published`**, separate from the
   geometry-derived `acres`, and add a QA/QC check on the discrepancy. Deed acreage and
   digitised geometry routinely disagree, and C07 and the 80-acre hard filter both depend on
   which one is used. Recommend screening on the **published** value, since that is what a
   broker or appraiser would quote, and reporting the geometry value alongside it.
5. **Treat this as confirmed for Tarrant only.** Items 1–4 are contingent on the other ten CADs
   behaving similarly; the recon plan already covers repeating §1 for each.

**Alternatives considered.** Join a separate appraisal roll anyway for richer attributes —
rejected as unnecessary work given the values are already present, and it would introduce 11
more schema-mapping surfaces. Use `TOTAL_VALU` instead of `LAND_VALUE` — rejected: total value
includes improvements, and this study is buying land, not buildings.

---

## D-009 · Zoning strategy

- **Date raised:** 2026-09-19
- **Status:** `DECIDED` 2026-09-22 — recommendation accepted in full. Implementation recorded in
  **D-009-R** below; the original analysis is preserved unchanged.
- **Scope ref:** §3 S02, §5.1 step 2, §14 (parcel-data risk)
- **Evidence:** `docs/recon/RECON_findings.md` §1.5, §2

**Question.** Zoning is a **hard filter** in §5.1. How is it sourced when no regional layer
exists, and what happens to parcels where zoning cannot be determined?

**Findings.**

1. **TAD parcels carry no zoning and no land-use field.** Verified: a field scan for `zon*`,
   `land_use*`, `luc*` over the 56-field schema returns nothing. `Parcels.zoning_class`,
   `zoning_code`, `land_use_code` and `land_use_class` have **no source in the parcel layer**,
   and since `land_use_class` drives the `Parcels` subtypes, the subtype assignment has no input
   either.
2. **Where zoning exists it is not one layer.** Dallas publishes **20 layers**. Base zoning is
   3,827 features, but Planned Development parcels carry only a `PD_NUM` there and their real
   permitted use sits in `PD_Subdistricts` (1,280 features). Large industrial tracts — precisely
   this study's targets — are commonly inside PDs, so reading base zoning alone misclassifies
   them.
3. **Coverage is patchy and the inventory is unreliable.** A Hub search across 30 jurisdictions
   produced more false positives than hits: Arlington **WA**, Grand Blanc **MI**, Lancaster
   **OH**, Decatur **GA**, Greenville **NC**, Mesquite **NV**. Only Dallas was confirmed at the
   service level.
4. **No authoritative Fort Worth zoning service was found** — the largest city in the study area
   and the one the client named.
5. **Unincorporated county land has no zoning at all, by law.** Texas counties lack general
   zoning authority. For those parcels this is not missing data; there is nothing to find. And
   unincorporated highway-adjacent land is exactly where cheap 80-acre tracts are.

**Recommendation — demote zoning from a hard filter to a scored, tiered attribute.**

Keeping zoning as a pass/fail gate means silently discarding every parcel in a
non-publishing city and every unincorporated parcel, which is both a large share of the
candidate universe and biased toward the cheap greenfield land the client would most plausibly
buy. That is a worse error than admitting uncertainty.

1. **Add a `zoning_confidence` domain** — `Confirmed` / `Inferred` / `Unzoned` / `Unknown`:
   - `Confirmed` — a spatial join to an authoritative municipal layer returned an industrial class.
   - `Inferred` — no zoning layer, but NLCD plus parcel context supports an industrial reading.
   - `Unzoned` — parcel is outside any incorporated place. Legally correct, not a gap.
   - `Unknown` — inside a city that publishes nothing usable.
2. **Hard-fail only on `Confirmed` *non*-industrial zoning.** A parcel confirmed residential is
   genuinely out. A parcel whose zoning is unknown is not.
3. **Carry the other three into scoring** with `screen_status = Review`, and add a small
   entitlement-risk weight so `Confirmed` industrial outranks `Unzoned` and `Unknown` rather
   than being indistinguishable from them.
4. **Union base zoning with PD/CD/PDS subdistricts** on ingest, preferring the subdistrict where
   one applies. Record per city which layers were combined.
5. **Report coverage honestly.** A table in the methodology report giving, per county, how many
   candidates fell into each confidence tier. This is a genuine finding about DFW data
   infrastructure, and stating it is more credible than implying complete coverage.
6. **Prioritise Fort Worth.** If an authoritative layer exists behind the city's open-data
   portal rather than Hub search, it is worth real effort — the client named Fort Worth, and a
   gap there is the most visible weakness in the study.

**Cost of this change.** One new domain, one new field, a change to the screening rule, and a
weight adjustment. `config/screening.yaml` already has `zoning.fallback_to_land_use` and
`fallback_screen_status: Review`, so the scaffolding is largely in place.

**Alternatives considered.**

- *Keep zoning as a hard filter, drop unknowns.* Simple, defensible on paper, and quietly
  discards most unincorporated greenfield land — the likeliest real-world DC sites. Rejected.
- *Keep it hard, but pass unknowns.* Inverts the bias: entitlement risk becomes invisible and
  a residential-in-practice tract can reach the shortlist. Rejected.
- *Hand-digitise zoning for non-publishing cities.* Most accurate, wholly impractical at
  ~180 incorporated places in eight weeks part-time. Rejected.
- *Use NCTCOG regional land use (S22) as the zoning proxy.* Worth testing as the `Inferred`
  tier's evidence base — it is regional and consistent, though land use is not zoning and
  cannot speak to entitlement. Recommend evaluating it when implementing tier 2.

---

## D-011 · AGOL authentication method

- **Date raised:** 2026-09-19
- **Status:** `OPEN`
- **Scope ref:** §6.3 tool 13 `PublishToAGOL`, §6.5 (secrets), §7.4 (dashboard), §8 (StoryMap)
- **Plan ref:** `docs/PLAN.md` Week 6

**Question.** How does `PublishToAGOL` — and the Week 6 web map, dashboard, and StoryMap
scaffolding — authenticate to ArcGIS Online?

**Hard rule, not negotiable.** **No secrets in chat and no secrets in committed files.** No
username, password, token, API key, client secret, or `.env` file containing any of them goes
into this repository, a commit message, a config file, a notebook, a log, or a conversation.
Scope §6.5 states it and it is restated here because Week 6 is the first point where it becomes
tempting to shortcut.

If a credential is ever pasted somewhere it should not be, treat it as compromised: rotate it
first, then clean up.

**Default — publish through ArcGIS Pro's active portal session.**

`arcpy.sharing` uses the portal connection that ArcGIS Pro is already signed in to. The analyst
signs in once, in Pro's UI; the tool inherits that session. Nothing is stored by this project,
nothing is passed as a parameter, and there is nothing to leak. This is the method scope §6.3
assumes for tool 13, and it is the default for all Week 6 publishing.

Consequence, accepted: publishing requires an interactive, signed-in ArcGIS Pro. That is
appropriate — publishing is a deliberate act with a real-world effect, not something a
background job should do unattended.

**Fallback — for standalone or CI publishing, if it is ever needed.**

Only if publishing must run outside a signed-in Pro session:

1. **A named GIS profile** (preferred). `GIS(profile="dsg_dfw_agol")` — the `arcgis` Python API
   stores the credential in the OS keystore, outside the repository, created once on the local
   machine. Code references the profile *name* only, which is safe to commit.
2. **Environment variables** set on the local machine — `AGOL_URL`, `AGOL_USER`, `AGOL_PASSWORD`
   — read at runtime, never written to disk by this project and never echoed into logs.

Either way the repository contains a *reference*, never a value.

**Not planned, and would need their own decision:** OAuth app credentials (client id/secret),
and publishing from GitHub Actions via repository secrets. Neither is required — the CI here
runs arcpy-free tests and has no reason to touch a portal. Adding portal access to CI would
create a credential with publish rights sitting in a third-party system, for no gain.

**Remaining to close.** Confirm which ArcGIS Online organisation is the publishing target and
whether that account has publisher privileges and sufficient credits; confirm Pro is signed in
to that same portal; decide the sharing level at each stage — the plan assumes **unlisted**
through Week 6 review and public only in Week 7.

**Alternatives considered.** Hard-code credentials in a config file — rejected outright; it is
the single most common way a public portfolio repository leaks a live account. Prompt for a
password at tool runtime — rejected: it defeats unattended re-runs, and the value then exists in
process memory and shell history for no benefit over the Pro session.

---

## D-012 · Multi-repository strategy — hub and spokes

- **Date raised:** 2026-09-19
- **Status:** `DECIDED`
- **Scope ref:** §6.2 (repository layout), §12 (deliverables — flagship + standalone GDB project)
- **Manifest:** `tools/spokes.yaml` · **Rationale:** `docs/SYNC_MANIFEST.md`

**Decision.** This repository is the **hub** and remains authoritative. Four **spoke**
repositories republish curated extracts of it as focused standalone public projects:

| Spoke | Kind | Why it stands alone |
|---|---|---|
| `config-driven-geodatabase-schema-builder` | tool | Generic — reads any schema YAML, not just this study's |
| `arcgis-location-intelligence-toolbox` | tool | A reusable `.pyt` and its testable package |
| `dfw-site-selection-explorer` | showcase | The dashboard as its own artifact |
| `dfw-site-selection-cartography` | showcase | The map series as its own artifact |

**Rationale.** Scope §12 already asks for two deliverables — the flagship study *and* a
standalone geodatabase-design project — so the work is not one indivisible thing. Two further
components are independently useful: the toolbox is a reusable tool regardless of client, and
the dashboard and map series are self-contained artifacts a reader may want to look at without
reading a 653-line scope document.

The practical argument is discoverability. Someone searching for "ArcGIS geodatabase schema
YAML" will not find it buried in a distribution-centre siting repository. Someone assessing
cartographic skill should not have to clone an analysis pipeline to see maps.

**Hub authoritative, one direction of travel.** Hub → spoke, never the reverse. A file listed in
`tools/spokes.yaml` is owned by the hub; editing it in a spoke means the next sync silently
overwrites it. Files a spoke owns outright — README, CI, `.gitignore` — are deliberately not in
the manifest and are never touched.

**Sync is deterministic, not remembered.** `tools/sync_spokes.py` copies only what the manifest
names, skips identical files, never deletes, and **exits non-zero if a manifest entry no longer
exists in the hub** — so a rename here surfaces immediately instead of quietly dropping a file
from a spoke. Re-sync is part of the Checkpoint protocol.

**Accepted trade-off — code duplication.** Both tool spokes carry `src/li/config.py`,
`logging_utils.py`, and `gdb.py`, plus overlapping config files. A change to `gdb.py` must reach
two places.

This is deliberate. The alternatives — a shared package on PyPI, or git submodules — would stop
each spoke standing alone. A reader landing on the schema builder from a portfolio link should
be able to clone it and run the tests immediately, not discover it is a shell around a
dependency they must also install. **For a portfolio, a repository that cannot be run on its own
has failed at its only job.** The manifest and script reduce the cost to one command; publishing
a broken standalone repo has no such remedy.

Duplication is also bounded: four modules and six config files, not a library.

**Honest cross-linking, no disguising.** Every spoke README ends with:

> A component of [dsg-dfw-site-selection](https://github.com/ndeogobernard/dsg-dfw-site-selection),
> a DFW regional-DC site-selection system.

The spokes are presented as components of one system, extracted because they are independently
useful. Padding a portfolio with repositories pretending to be unrelated projects is
transparent to any reviewer who looks at commit dates, and it would be dishonest. The portfolio
cards carry **both** links — hub and spoke — for the same reason.

The showcase spokes are marked **In progress** rather than implying finished work, and their
READMEs state plainly which items do not exist yet.

**Known consequence.** `config-driven-geodatabase-schema-builder` is currently short its ERD,
data dictionary, and design-rationale write-up. Those are deferred because acceptance criterion
§13.5 requires them to match the delivered schema *exactly*, and the schema changes once D-008
and D-009 are settled. **That spoke re-syncs after recon reconciles `config/schema.yaml`** —
publishing documentation that is about to be wrong would be worse than publishing none.

**Alternatives considered.**

- *One repository only.* Simplest and most honest by default, but buries four independently
  useful components and fails the discoverability argument above.
- *Spokes as git submodules of the hub.* No duplication, but submodules are a well-known
  usability tax and a spoke would no longer clone-and-run.
- *Shared internal package published to PyPI.* Correct for a product; disproportionate for a
  portfolio project, and it makes every spoke depend on a package index.
- *Copy files by hand at each milestone.* What the manifest exists to prevent. It drifts within
  weeks and nobody can tell which copy is current.

---

## D-008-R · C10 land-cost path — resolution

- **Date decided:** 2026-09-22 · **Status:** `DECIDED` · **Resolves:** D-008

Recommendation accepted in full. Implemented in `config/schema.yaml`,
`config/sources.yaml`, and `config/criteria.yaml`:

**C10 = appraised land value ÷ published acres.** Sourced from the parcel layer's own value
fields; no CAD roll join.

**Two acreages, kept apart deliberately.** `acres` is derived from geometry by the
`calc_Parcel_Acres` attribute rule; `acres_published` holds what the appraisal district states.
Screening and C10 use the **published** value, because that is the figure a broker or appraiser
would quote. `acres_delta_pct` is calculated by a new `calc_Parcel_AcresDelta` rule and is a
QA/QC output — the divergence between deed acreage and digitised geometry is information, not
an inconsistency to reconcile away.

**Zero land value is never treated as free land.** `land_val_flag` records the reason. Parcels
with `LAND_VALUE = 0` — 64,806 of 758,633 in Tarrant, 8.5%, all exempt / right-of-way /
government — are excluded from C10 normalization and flagged for review. Left in, they would
normalize to the *best possible* land-cost score and dominate the ranking with land that is not
for sale. Silent zeroes are prohibited.

**No shared default field map.** `config/sources.yaml` S01 now carries per-county maps only.
Tarrant's is `status: verified` and read from the live service. Fields verified *absent* are
declared under `unavailable:` so a null is a recorded fact rather than a silent mapping failure.

---

## D-009-R · Zoning strategy — resolution

- **Date decided:** 2026-09-22 · **Status:** `DECIDED` · **Resolves:** D-009

Recommendation accepted in full. Zoning is **not** a hard filter.

**New domain `dm_ZoningConfidence`** — `Confirmed` / `Inferred` / `Unzoned` / `Unknown`, on
`Parcels.zoning_confidence`.

**Only surviving zoning exclusion:** a parcel *confirmed* by an authoritative municipal layer to
be a non-industrial class (residential, mixed use). `Inferred`, `Unzoned`, and `Unknown` are
never excluded — `screening.yaml → zoning.never_excluded_confidences` enforces it.

**`Unzoned` is a finding, not a gap.** Texas counties have no general zoning authority, so
unincorporated land has no zoning to find. It scores *above* `Unknown` precisely because the
absence is legal certainty rather than missing data.

Non-`Confirmed` parcels carry `screen_status = Review`, so the shortlist always shows how much
entitlement uncertainty it is carrying.

---

## D-013 · Screening scope and the subtype key

- **Date decided:** 2026-09-22 · **Status:** `DECIDED`
- **Scope ref:** §5.1 (screening), §4.5 (subtypes), §5.3 (criteria), §5.5 (weights)

Two questions, both following from D-009.

### Q1 — Screening is physical and infrastructural only

Every industrial-zoning requirement is removed from `config/screening.yaml`. The hard filters
that remain are all physically verifiable: acreage, floodway, SFHA percentage, wetland coverage,
mean slope, developed percentage, water and sewer CCN, and truck drive-time to an interchange.

`allow_agricultural_near_industrial_miles` is retired — it existed only to rescue agricultural
land from the industrial-zoning gate, and there is no longer a gate to rescue it from.

**Industrial context moves into scoring**, where uncertainty can be priced instead of being
fatal: **C11** (industrial cluster, unchanged) plus a new **C12 · Zoning and entitlement
signal**, scoring `Confirmed` 100 / `Inferred` 65 / `Unzoned` 50 / `Unknown` 25.

**Weighting.** C12's weight is **carved out of C11** rather than diluting every criterion — both
measure industrial context, and the scope's original C11 allocation was already standing in for
entitlement. Balanced 0.07 → 0.04 + 0.03; LaborFirst 0.06 → 0.04 + 0.02; AccessFirst
0.07 → 0.04 + 0.03. Every other weight is untouched and each scenario still sums to exactly
1.00. The optional Lightcast criterion moves from C12 to **C13**.

*Why not leave zoning as a gate and accept the loss?* Because the loss is not random. It falls
hardest on unincorporated highway-adjacent greenfield — the cheap, large, rezonable land a
distribution centre would realistically buy. A filter that systematically removes the most
plausible answers is worse than one that admits uncertainty.

### Q2 — The `Parcels` subtype moves to `zoning_confidence`

Scope §4.5 keys subtypes on `land_use_class`. Recon showed **no county is guaranteed to publish
a land-use code — Tarrant publishes none at all**, so that subtype would have been unset on
every record in the pilot county and probably most others. A subtype nothing populates is
decoration.

The subtype is therefore keyed on `zoning_conf_st`, the integer partner of `zoning_confidence`,
which the pipeline always populates. ArcGIS requires integer subtype fields, hence the pair. The
default subtype is **`Unknown`**: a parcel is unknown until evidence says otherwise, which is
the honest default and fails safe.

`land_use_class` is retained as a **nullable** attribute with its domain, for counties that do
supply one. `land_use_st`, which existed only to be the subtype key, is removed.

### Also applied — recon corrections

- **C01** now names the exact ACS variables: `C24010_036E + 037E + 072E + 073E`. The parent
  lines `034E`/`070E` include **production** occupations; using them would have folded factory
  workers into the warehouse labour pool.
- **C09** records the real NFHL derivations: SFHA from `SFHA_TF` (`"T"`/`"F"` *text*), floodway
  by substring-matching `FLOODWAY` inside `ZONE_SUBTY`. NFHL has no floodway field, and floodway
  is a hard filter — a wrong derivation would silently pass floodway land.

**Verified after rebuild:** 12 domains, 6 attribute rules, 24 criterion columns on `SiteScores`,
`Parcels` subtypes on `zoning_conf_st` defaulting to `Unknown`, `land_use_st` gone.
41 tests passing (was 26).

---

## D-014 · Dallas County needs a DCAD roll join — D-008 does not generalise

- **Date raised:** 2026-09-22 · **Status:** `OPEN`
- **Scope ref:** §3 S01, §5.3 C10 · **Evidence:** CAD probe, 2026-09-22

**Finding.** D-008 concluded that appraised values ship with parcel geometry and no CAD roll
join is needed. That is true for Tarrant, and true for Denton. **It is false for Dallas.**

`CurrentDcadParcels` (City of Dallas GIS Services) publishes **695,446 features with five
fields**:

```
OBJECTID, RecAcs, GIS_Acct, Shape__Area, Shape__Length
```

Geometry, an account number, and a recorded acreage. **No land value, no total value, no owner,
no situs address, no year built, no land use, no zoning.**

This is precisely the scenario flagged in session 1 and then provisionally dismissed when
Tarrant turned out to carry values inline. It was dismissed one county too early: **D-008's
conclusion held for the county that happened to be probed first.** Dallas is the second-largest
county in the study area, so this is a material gap, not an edge case.

**Consequences.**

- **C10 cannot be computed for Dallas parcels from the parcel layer alone.** Either a DCAD
  tabular roll is obtained and joined on `GIS_Acct`, or Dallas candidates carry no land-cost
  score and must be handled explicitly rather than scoring as missing.
- The pipeline needs a **join step that the design does not currently have**, and it will be
  needed per county rather than once.
- The `unavailable:` list in `sources.yaml` is doing real work here: seven schema fields are
  declared absent for Dallas, so their nulls are a recorded fact rather than a mapping failure.

**Options.**

1. **Obtain the DCAD tabular roll and join on `GIS_Acct`.** Correct and complete. Adds a
   per-county join step to `IngestAndStandardize`, and DCAD's roll format must be confirmed.
2. **Score Dallas candidates without C10** and redistribute C10's weight across the remaining
   criteria *for those candidates only*. Avoids the join, but makes candidates in different
   counties non-comparable — which defeats the ranking.
3. **Use `TOTAL_VALU`-equivalent from another source** as a proxy. Not available either; Dallas
   publishes no value field at all.
4. **Exclude Dallas County.** Indefensible — it is the largest county by population in the MSA.

**Recommendation: option 1.** The join is unavoidable if the ranking is to compare counties
honestly. Better to discover this now, with two of eleven counties' schemas actually read, than
at scoring time.

**Also worth recording:** this is the second time an assumption survived because only one
county had been checked. The remaining eight counties have no located service at all, so their
value availability is unknown, and the possibility that more of them look like Dallas than like
Tarrant should be treated as live.
