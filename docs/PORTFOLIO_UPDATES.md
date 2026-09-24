# Portfolio updates

Tracks how this project is represented on the portfolio site
**[ndeogobernard.github.io/ndeogo](https://ndeogobernard.github.io/ndeogo/)**
(repo: [ndeogobernard/ndeogo](https://github.com/ndeogobernard/ndeogo)).

The portfolio is a **separate repository**, cloned as a sibling at `../ndeogo`. Its files and
commits stay fully separate from this one — nothing from this repo is ever committed there
except finished assets, and nothing from there is committed here.

**The change log below is append-only.** The checklist above it is living — tick boxes as
assets land. Both are updated at every Checkpoint that produces a portfolio-worthy asset; see
the Checkpoint protocol in `docs/PROJECT_GUIDE.md`.

---

## Card checklist

Slug prefix `dsg-dfw-`. Card images live at `../ndeogo/assets/<slug>.jpg` (16:10). Documentation
PDFs follow the site convention `../ndeogo/documentation/<slug>-documentation.md.pdf`.

### 1. Spatial Analysis — *DICK'S DFW Distribution Center Site Selection* (flagship)

Tab `#tab-analysis` · slug `dsg-dfw-analysis` · **Status: In progress**

| Item | State |
|---|---|
| Card live on site | ✅ done |
| GitHub link | ✅ done — links to the project repo |
| Card image | ⬜ placeholder — **real hero image is top priority** |
| StoryMap link | ⬜ pending — inert "coming soon" pill |
| Dashboard link | ⬜ pending — inert "coming soon" pill |
| Report PDF | ⬜ pending — inert "coming soon" pill |
| Remove "In progress" marker | ⬜ pending — once StoryMap + report + hero image are live |

### 2. Automation — *Location Intelligence Python Toolbox*

Tab `#tab-automation` · slug `dsg-dfw-toolbox` · **Status: In progress**

| Item | State |
|---|---|
| Card live on site | ✅ done |
| GitHub link | ✅ done |
| Card image | ⬜ placeholder |
| Demo GIF | ⬜ pending — inert "coming soon" pill |
| Remove "In progress" marker | ⬜ pending — once all 13 tools ship and the GIF is up |

### 3. Geodatabase Design & SQL — *DFW Site-Selection Geodatabase Design*

Tab `#tab-geodatabase` · slug `dsg-dfw-geodatabase` · **Status: In progress**

| Item | State |
|---|---|
| Card live on site | ✅ done |
| GitHub link | ✅ done |
| Card image | ⬜ placeholder — ERD export is the natural replacement |
| Report / design-rationale PDF | ⬜ pending — inert "coming soon" pill |
| Remove "In progress" marker | ⬜ pending — once ERD + data dictionary are published |

### 4. Web Applications — *DICK'S DFW Site Selection Explorer*

Tab `#tab-webapps` · slug `dsg-dfw-dashboard` · **Status: In progress**

| Item | State |
|---|---|
| Card live on site | ✅ done |
| GitHub link | ✅ done |
| Card image | ⬜ placeholder — dashboard screenshot is the natural replacement |
| Live Map link | ⬜ pending — inert "coming soon" pill |
| StoryMap link | ⬜ pending — inert "coming soon" pill |
| Remove "In progress" marker | ⬜ pending — once the dashboard is published publicly |

### 5. Cartography — *DFW Site-Selection Map Series*

Tab `#tab-cartography` · slug `dsg-dfw-mapseries` · **Status: In progress**

Gallery card — opens the site's map viewer. Real maps are added as `<a>` entries inside the
card's `<template class="card-maps">`, with figures under
`../ndeogo/assets/visualizations/dsg-dfw/`.

| Item | State |
|---|---|
| Card live on site | ✅ done |
| Card image | ⬜ placeholder |
| Map figures in viewer | ⬜ placeholder — one stand-in entry; real maps M01–M18 pending |
| `assets/visualizations/dsg-dfw/` folder | ⬜ not created yet |
| Remove "In progress" marker | ⬜ pending — once the series is exported |

---

## Real assets still needed

Priority order. Every one of these replaces a placeholder currently on the live site.

| # | Asset | Replaces | Priority |
|---|---|---|---|
| 1 | **Flagship hero image** — composite suitability map (M13, Balanced) or the recommended-site map (M18), exported 1600×1000 | `assets/dsg-dfw-analysis.jpg` | **Top** |
| 2 | ArcGIS StoryMap public URL | Flagship + Web Apps "StoryMap" pills | High |
| 3 | ArcGIS Dashboard public URL | Flagship "Dashboard" + Web Apps "Live Map" pills | High |
| 4 | `Methodology_Report.pdf` | Flagship "Report" pill | High |
| 5 | Dashboard screenshot, 1600×1000 | `assets/dsg-dfw-dashboard.jpg` | Medium |
| 6 | ERD export (`docs/ERD.png`), cropped 16:10 | `assets/dsg-dfw-geodatabase.jpg` | Medium |
| 7 | GDB design-rationale PDF | Geodatabase "Report" pill | Medium |
| 8 | Toolbox demo GIF — tool running in Pro | Automation "Demo GIF" pill | Medium |
| 9 | Map series M01–M18 PNGs | Cartography gallery + `dsg-dfw-mapseries.jpg` | Medium |
| 10 | Toolbox screenshot in the Pro Catalog pane | `assets/dsg-dfw-toolbox.jpg` | Low |

Placeholders are regenerated with `python tools/make_portfolio_placeholders.py`.

---

## Change log

### 2026-09-19 — Initial publication

Portfolio commit [`e7205fd`](https://github.com/ndeogobernard/ndeogo/commit/e7205fd) on `main`,
live at <https://ndeogobernard.github.io/ndeogo/>.

**Added** five cards, one per tab, each reusing that tab's existing markup verbatim. No new CSS,
no framework, no redesign.

**Inspection findings that shaped the work:**

- The site is **hand-authored** — a single 52 KB `index.html`, `.nojekyll`, no Jekyll or
  `package.json`. No build step to run.
- Card images follow `assets/<slug>.jpg` at **16:10** (`.card-img-wrap` sets
  `aspect-ratio: 16/10`). Documentation follows `documentation/<slug>-documentation.md.pdf`.
- **No badge or status component exists** anywhere in the CSS. Rather than invent one, status is
  a `" · In progress"` suffix inside the existing `.card-desc`, matching its type style exactly.
- The built-in `.card-placeholder` / `.ph-N` fallback is a **flat grey tile**, so real
  placeholder images were generated instead — dark, monochrome, drawn in the site's own greys.
- **Cartography cards are all `is-gallery`**, driven by a `<template class="card-maps">` and a
  lightbox, not by link pills. The map-series card follows that pattern.
- `tools/check_site.py` runs in CI on every push and **errors on any internal `href`/`src` that
  does not resolve**. Placeholder links are therefore inert
  `<span class="card-link">…coming soon</span>` elements, not dead hrefs.

**Verification:** `tools/check_site.py` → 0 errors. All five cards render under the correct
panels (6 analysis, 6 automation, 3 geodatabase, 5 webapps, 11 cartography). All 33 images load;
the five new ones at 1600×1000. The Cartography lightbox opens with its caption.

**Pre-existing issue found, not introduced here and not fixed here:** portfolio commit
`0311cf6` ("Delete Bernard_Issifu_Resume.pdf") removed the résumé PDF, but `index.html:630`
still links to it — `<a class="resume-download" download href="Bernard_Issifu_Resume.pdf">`.
`check_site.py` fails on that reference, so CI is red on `main` independently of this change,
and the résumé download button 404s for visitors. Flagged to the owner; the fix is theirs to
choose (restore the PDF, or remove the button).
