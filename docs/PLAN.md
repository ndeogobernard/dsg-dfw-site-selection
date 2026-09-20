# Project plan — milestone tracker

In-repo tracking of the scope §11 timeline (8 weeks, part-time). `.claude/STATE.md` holds the
*current* position; this file holds the whole arc, including exit criteria and dependency gates.

**Legend:** ✅ done · 🔄 in progress · ⏸ deliberately deferred · ◻ not started · ⛔ blocked

| Week | Milestone | Status |
|---|---|---|
| 1 | Data acquisition; `sources.yaml` complete; stores compiled | 🔄 recon done, no ETL |
| 2 | Geodatabase schema built via tool; ERD + data dictionary v1 | ✅ / ⏸ ERD deferred |
| 3 | ETL and QA/QC tools; all layers loaded | ⛔ blocked on D-008, D-009 |
| 4 | Network dataset; screening | ◻ |
| 5 | Service areas, OD, workforce, scoring, 3 scenarios, sensitivity | ◻ |
| 6 | **AGOL publish + app scaffolding** | ◻ — see below |
| 7 | Dashboard + StoryMap finished and shared | ◻ |
| 8 | Methodology report; README; GDB write-up; peer reproduction | ◻ |

---

## Week 6 — AGOL publish + app scaffolding

**No AGOL access is required to reach this point.** Everything in Weeks 1–5 runs locally against
the file geodatabase and the local network dataset. AGOL is first needed here.

### Dependency gate

Week 6 does not start until **all** of the following exist. Each is checkable, so the gate is a
real precondition rather than a note:

| Prerequisite | Check |
|---|---|
| `SiteScores` populated for all three scenarios | rows exist per `scenario`, `composite` non-null, ranks unique |
| `Shortlist` populated with a recommended site | ≥ 5 rows per scenario; exactly one `recommended_flag = 1` |
| `SensitivityResults` populated | rows for the Balanced `run_id` |
| `ServiceAreas_Driving` / `ServiceAreas_Truck` | rows for shortlisted `cand_id`s |
| `Stores_DSG` with `served_flag` set | served set resolved, count recorded (D-003) |
| Static maps M01–M18 exported | files present in `outputs/maps/` |
| AGOL credentials available | D-011 — **not** in code or chat |

If the gate is not met, the correct action is to finish Week 5, not to publish partial results.

### 6a · `PublishToAGOL` — tool 13 · *Claude Code*

Publish the results layers as hosted feature layers (scope §6.3 tool 13, §7.4).

- **Layers:** `SiteScores`, `Shortlist`, `ServiceAreas_Driving`, `ServiceAreas_Truck`, `Stores_DSG`
- **Projection:** reproject to **EPSG:3857** for web use (scope §2.3); the analysis CRS stays 6584
- **Method:** `arcpy.sharing` against ArcGIS Pro's active portal session
- **Auth:** per **D-011** — no credentials in code, ever
- **Idempotent:** republishing the same `run_id` overwrites rather than duplicating
- **Records:** item IDs written back to `ScoreRuns.parameters_json` so a published app traces to
  the exact run and git commit that produced it

### 6b · Assemble the web map · *Claude Code*

Built with the **`arcgis` Python API** (not `arcpy`), so it is reproducible rather than clicked.

- Add the hosted layers from 6a
- Symbolize candidates by `score_class` — 5-class sequential, consistent breaks across scenarios
  (§7.1)
- Recommended site: distinct **black dashed outline**, as on every results map (§7.1)
- Service areas as toggleable layers; `Stores_DSG` filtered to `served_flag = 1`
- Popups configured for the fields the dashboard indicators read

### 6c · Scaffold the ArcGIS Dashboard · *Claude Code scaffolds / Bernard finishes*

Built with **`arcgis.apps.dashboard`** to the §7.4 specification:

- **Header** — title, scenario selector (category selector on `scenario`)
- **Map** — the 6b web map, with layer toggles
- **List** — candidates sorted by rank
- **Indicators** — composite, rank, 30-min labour pool, unemployment rate, minutes to
  interchange, mean minutes to stores, SFHA %, land value/acre
- **Charts** — serial chart of top 10 by composite; stacked bar of weighted criterion
  contributions for the selected candidate; gauge on `top10_freq`
- **Details panel** — site profile text

> **Hand-off:** Claude Code creates the widgets and wires the data. **Bernard finishes** the
> cross-widget interactivity (selection filtering and zoom-to) and the **mobile layout** in the
> Dashboard builder — both are builder-side configuration that the API does not express well.

### 6d · Draft the StoryMap · *Claude Code scaffolds / Bernard finishes*

Built with **`arcgis.apps.storymap`** — all **14 sections** of scope §8, with copy written and
maps/figures placed:

Cover · The requirement · The question · The DFW industrial market · Who the DC serves ·
Screening the market · What matters · The labour story · Reach and access · Results ·
How stable is the answer? · The shortlist · The recommendation · Method, data, and code

Audience is brokers, corporate real-estate executives, and economic-development staff, so every
technical term is explained in one line at first use (§8).

> **Hand-off:** Claude Code drafts the narrative and places media. **Bernard verifies** the copy
> and **publishes** in the StoryMap UI — sidecar/swipe blocks and final layout are builder work,
> and publishing is a deliberate human act.

### Week 6 exit criteria

- Hosted feature layers published and reachable
- Web map renders with correct symbology and the recommended site outlined
- Dashboard exists with every §7.4 widget present and bound to real data
- StoryMap exists with all 14 sections drafted and media placed
- Item IDs recorded in `ScoreRuns`
- Both apps shared **unlisted** for review — public sharing happens in Week 7

---

## Weeks 7–8

**Week 7** — Bernard finishes dashboard interactivity and mobile layout; verifies and publishes
the StoryMap; both shared for review. Portfolio cards updated per the Checkpoint protocol in
`CLAUDE.md` as each public URL lands.

**Week 8** — Methodology report (§9), README results summary, standalone GDB write-up, portfolio
pages, and peer reproduction of the Balanced run (§13.6).
