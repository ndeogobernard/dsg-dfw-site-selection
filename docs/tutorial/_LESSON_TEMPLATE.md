# Lesson NN — <title>

> Template. Copy to `NN-<slug>.md` and fill from **real work already done**, not from
> imagination. A lesson describing a step nobody has run is fiction, and it will be wrong.
>
> Delete these quote blocks as you fill each section.

**Phase:** <scope §N / Week N> · **Status:** ◻ not started / 🔄 drafted / ✅ verified
**Prerequisites:** <earlier lessons, or "none">
**Time:** automated ~N min · manual ~N min

---

## What you will end up with

> One or two sentences, concrete and checkable. "A `CandidateSites` feature class with
> `screen_status` set on every evaluated polygon" — not "an understanding of screening".

## Why this step exists

> What question in the study does this answer, and what breaks downstream if it is skipped or
> done badly? Tie it to the scope section and to the criterion or filter it feeds.

---

## Concepts — why this works

> **This section is the point of the lesson.** A reader who follows the steps without it can
> repeat the work; a reader who has it can adapt the work when the data differs. Do not skip it
> because the steps "look obvious".
>
> Cover, in plain language:
>
> - **The idea.** The GIS or statistical concept in play — spatial join, zonal statistics,
>   network impedance, min–max normalization, whatever it is. Assume a competent reader who has
>   not used this particular tool.
> - **Why this approach and not another.** Name the alternative that was rejected and why. If
>   there is a `docs/DECISIONS.md` entry, link it.
> - **The assumption being made.** Every analytical step assumes something — that centroids
>   represent block groups adequately, that CAD acreage matches geometry, that a CCN implies
>   serviceability. Name it here rather than burying it.
> - **How it can go wrong quietly.** Failures that produce plausible-looking output rather than
>   an error. These are the expensive ones.

---

## Steps

> Both tracks must produce the **same result**. If they cannot, say so explicitly and explain
> the difference — that is useful information, not a defect to hide.

### Track A — Automated (the tool)

> The real command or tool run, copied from a session that actually worked. Include every
> parameter, not a sketch of them.

```bash
<exact command>
```

| Parameter | Value used | Why this value |
|---|---|---|
| | | |

**Config that drives this:** `config/<file>.yaml` → `<key>`

**Expected output:**

```
<real, trimmed console output>
```

**Runtime:** <measured, on what hardware>

### Track B — Manual (by hand in ArcGIS Pro)

> The same work, clicked or typed by a person, from the raw sources. Someone with no access to
> this repository's code must be able to follow it.
>
> Use numbered steps naming the actual tool, the ribbon path, and the parameter values. Where a
> geoprocessing tool is used, give its real name — *Pairwise Dissolve*, not "dissolve".

1. **<Ribbon path / tool name>** — …
   - Parameter: value
2. …

**Equivalent Python (Pro's Python window), if useful:**

```python
<arcpy snippet>
```

**Where this differs from Track A:** <e.g. the tool batches in groups of 50 for memory; by hand
you would do it in one pass and may hit a limit at N features>

---

## Verify it worked

> Checks the reader can run, with the number or condition to expect. "It looks right" is not a
> check. Prefer something countable.

| Check | How | Expect |
|---|---|---|
| | | |

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| | | |

---

## What this produced

| Output | Where | Feeds |
|---|---|---|
| | | |

## Try it yourself

> One or two variations that build understanding — change a threshold, swap a weighting, run it
> for a different county. Say what the reader should expect to see change, so they can tell
> whether they understood.

## Further reading

> Esri docs for the tools used, the scope section, relevant `docs/DECISIONS.md` entries.
