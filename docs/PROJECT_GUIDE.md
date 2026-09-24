# docs/PROJECT_GUIDE.md — DICK'S DFW Distribution Center Site Selection

## Project identity

A reproducible, multi-criteria location-intelligence study identifying the best sites in the
Dallas–Fort Worth MSA for a **~90-acre, ~800,000 SF DICK'S Sporting Goods regional distribution
center** serving 100+ stores across the south-central U.S. The full parcel universe across 11
counties is screened against hard filters, survivors are scored on 11 criteria under three
weighting scenarios, rank stability is tested, and a top-five shortlist with one recommended site
and one alternate is delivered. Two deliverables come out of it: the **flagship project**
(repo, toolbox, maps, dashboard, StoryMap, methodology report) and a **standalone geodatabase-design
project** (schema, ERD, data dictionary, design rationale). It is portfolio work — polish and
public presentation matter as much as the analysis.

**`DICKS_Fort_Worth_DC_Site_Selection_Project_Scope.md` (repo root, v1.1, 653 lines) is the source
of truth** for goals, geodatabase design, toolbox specs, criteria, scenarios, timeline, and
acceptance criteria. When this file and the scope disagree, the scope wins — unless a
`docs/DECISIONS.md` entry explicitly supersedes it.

## Environment

- **ArcGIS Pro 3.x** with **Network Analyst** and **Spatial Analyst** (both required)
- Python 3.11 from a **cloned** conda env — `arcgispro-py3` is read-only:
  `conda create --clone arcgispro-py3 --name dsg-dfw`
- Libraries: `arcpy`, `pandas`, `numpy`, `pyyaml`, `requests`, `matplotlib`, `pytest`;
  `geopandas`, `shapely`, `pyogrio` for non-arcpy ETL (install into the clone)
- Interpreter on this machine:
  `C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe`
- Bulk data and the geodatabase live **outside the repo**; see `config/paths.yaml`.
  Any path may be overridden with a `DSG_`-prefixed environment variable.

## Repo layout (scope §6.2)

```
config/       schema.yaml, sources.yaml, screening.yaml, network.yaml,
              criteria.yaml, weights.json, paths.yaml
toolbox/      LocationIntelligence.pyt + models/ (ModelBuilder .tbx)
pro/          DFW_DSG.aprx + DFW_DSG.atbx — the ArcGIS Pro project.
              Regenerate with tools/setup_pro_project.py --force.
              Build the GDB first or its default geodatabase will not resolve.
tools/        repo utilities (Pro project setup, portfolio placeholders)
src/li/       importable package — all real logic lives here
              config, logging_utils, gdb, etl, qaqc, screening, network,
              workforce, criteria, scoring, sensitivity, export
src/run_pipeline.py    CLI entry point
tests/        arcpy-free unit tests, run in CI
docs/         ERD, DataDictionary.md, GDB_DesignRationale.md,
              Methodology_Report.pdf, DECISIONS.md, SESSION_LOG.md, figures/
notebooks/    exploration, results review, sensitivity plots
data/         raw/ and gdb/ — gitignored
outputs/      maps/, map_series/, tables/, backups/, logs/
```

## Hard conventions

Do not break these without recording a decision in `docs/DECISIONS.md`.

- **Config-driven.** No hard-coded paths, thresholds, or weights anywhere in code. Everything
  comes from `config/`. A magic number in a `.py` file is a bug.
- **Naming.** Feature classes and tables `PascalCase`; fields `snake_case`; domains `dm_*` (coded)
  and `rg_*` (range); relationship classes `rel_*`.
- **Analysis CRS (§2.3): EPSG:6584** — NAD83(2011) StatePlane Texas North Central FIPS 4202 (US ft).
  Verified correct. All layers reprojected on ingest; source CRS + transformation recorded in
  `DataSourceRegistry`. Web/AGOL publishing uses EPSG:3857.
- **Run identity.** `run_id = YYYYMMDD_HHMM_<scenario>`. Every run writes a `ScoreRuns` row
  carrying the run_id, scenario, timestamp, user, toolbox version, **git commit hash**, and
  `parameters_json`. Analytical outputs carry `run_id`; raw ingested layers are immutable.
- **Provenance.** Every source-derived layer carries `source_id` joining to `DataSourceRegistry`.
- **Secrets.** Never in the repo. AGOL and Census credentials via environment variables only.
- **Reproducibility.** A clean clone plus downloaded data must reproduce `SiteScores` and
  `Shortlist` for the Balanced scenario (acceptance criterion §13.1).

## Canonical commands

```bash
python run_pipeline.py --scenario Balanced --steps all
```

Scenarios: **Balanced**, **LaborFirst**, **AccessFirst**.

```bash
python -m pytest tests/ -q
```

Rebuild the geodatabase from `config/schema.yaml` (~3.5 min, destructive):

```bash
python -c "import sys; sys.path.insert(0,'src'); from li import gdb; gdb.build_schema(overwrite=True)"
```

## Session protocol

**At session start — before doing any work:**

1. Read `docs/STATE.md`.
2. Skim the most recent entries in `docs/DECISIONS.md` and `docs/SESSION_LOG.md`.
3. **Restate current status to the user** — current milestone, what's done, what's blocked, and
   the next actions — before touching anything.

**On the word "Checkpoint"** — and also before ending a session, or whenever context is getting
full:

1. Update `docs/STATE.md` so it matches reality. It is a *snapshot*, not a history.
2. Append a dated entry to `docs/SESSION_LOG.md`: what changed, what was decided, what's next.
3. Record any new decisions in `docs/DECISIONS.md`, and update the status of any OPEN decision
   that was resolved this session.
4. Stage and commit: `chore(context): checkpoint <YYYY-MM-DD>`.
5. **If a phase's work completed, fill its tutorial lesson** — see below.
6. **If this milestone produced a portfolio-worthy asset, also update the portfolio** — see
   below.

**Tutorial capture — part of every Checkpoint that completes a phase.**

`docs/tutorial/` is **dual-track**: every lesson carries both the automated path and the manual
one. When a phase's work is done, fill its lesson from `docs/tutorial/_LESSON_TEMPLATE.md`
while the details are still fresh, capturing **both**:

- **Track A — Automated.** The exact command or tool run, **every** parameter with the value
  actually used and why, the config keys that drove it, real trimmed output, measured runtime.
- **Track B — Manual.** The same work by hand in ArcGIS Pro from raw sources — named
  geoprocessing tools, ribbon paths, parameter values — followable by someone who does not have
  this repository's code. Note any genuine difference between the tracks rather than hiding it.
- **Concepts — why this works.** The idea in play, why this approach over the rejected
  alternative, the assumption being made, and how it can fail *quietly*.

Fill lessons from work that actually happened. A lesson written ahead of the work is fiction and
will be wrong in the details that matter. If the manual equivalent has not been performed, say
so in the lesson instead of inventing plausible steps.

**Portfolio sync — part of every Checkpoint that produces a public asset.**

Portfolio-worthy means: a published StoryMap or dashboard URL, results or a recommended site, a
report PDF, a real hero image, or exported map figures. When one lands, the same Checkpoint also
does this **in the separate portfolio repo at `../ndeogo`, on `main`**:

1. Swap the matching placeholder on the relevant card — replace an inert
   `<span class="card-link">…coming soon</span>` with a real `<a class="card-link" href="…">`,
   and replace the placeholder image at `assets/dsg-dfw-<component>.jpg` with the real export
   (16:10, ~1600×1000).
2. Drop new map figures into `assets/visualizations/dsg-dfw/` and add an `<a>` entry to the
   Cartography card's `<template class="card-maps">`.
3. **Remove the `" · In progress"` marker** from a card's `.card-desc` once that card is
   substantively complete.
4. Run `python tools/check_site.py` in `../ndeogo` — it must report **0 errors** before pushing.
   It fails on any internal `href`/`src` that does not resolve, which is why unbuilt links stay
   as `<span>` rather than dead hrefs.
5. Commit and push to `main` in `../ndeogo`. Keep the two repos' files and commits entirely
   separate — never commit portfolio files here or project files there.
6. Tick the matching boxes in `docs/PORTFOLIO_UPDATES.md` (this repo) and append a dated entry
   to its change log.

Match the site's existing markup exactly. It is hand-authored with no build step and no badge
component — **do not add CSS, frameworks, or redesign anything.**

**Rules:**

- **Never delete decision or session history.** `docs/DECISIONS.md` and `docs/SESSION_LOG.md` are
  append-only. Correct an earlier decision by appending a superseding entry that names the one it
  replaces — do not edit the original.
- **`docs/STATE.md` is the only context file that gets overwritten.**
- Keep `STATE.md` short. If it is growing into a narrative, the narrative belongs in
  `SESSION_LOG.md`.
- A decision marked `[VERIFY]` or `[DECISION]` in the scope is not resolved until it has an entry
  in `docs/DECISIONS.md` with a status other than OPEN.

## Working notes

- Read the scope section before implementing against it — it is specific, and the section numbers
  referenced in configs and docstrings point back to it.
- ArcGIS gotchas already hit: attribute rules require **GlobalIDs** (`ERROR 002710`); subtype
  fields must be **SHORT or LONG**, never text; `arcpy.da.Describe()` does **not** expose topology
  rules — verify via `ExportXMLWorkspaceDocument(..., "SCHEMA_ONLY")`.
- Flag scope gaps rather than silently working around them; the scope is a living document and
  `docs/DECISIONS.md` is where amendments get recorded.

@docs/STATE.md
