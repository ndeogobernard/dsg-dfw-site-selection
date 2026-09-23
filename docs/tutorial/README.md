# Tutorial — building this study from scratch

A lesson per phase, teaching how the DICK'S DFW distribution-centre site-selection study was
built. Not API documentation and not a changelog: material someone can learn the work from.

---

## The dual-track principle

**Every lesson shows both the automated path and the manual one.**

| Track | What it is | Why it exists |
|---|---|---|
| **A — Automated** | The real tool run, with every parameter | Reproducibility. This is how the study is actually executed. |
| **B — Manual** | The same work by hand in ArcGIS Pro, from raw sources | Comprehension and audit. Works without this repository's code. |

Both tracks must reach the **same result**. Where they genuinely cannot — batching, memory
limits, a step only practical in script — the lesson says so and explains the difference rather
than quietly presenting one as the other.

**Why bother with Track B.** Three reasons, in order of how much they matter:

1. **A reader who has only ever run the tool does not understand the analysis.** They can
   reproduce it and cannot adapt it. The moment the data differs — another metro, another
   client, a county whose parcels lack a value field — they are stuck.
2. **A hidden pipeline cannot be audited.** A reviewer, or a sceptical client, is entitled to
   ask *"show me how you got that number"* and receive an answer they can check by hand. Scope
   §13.6 requires an independent reviewer to reproduce the Balanced run.
3. **It proves the tool is right.** Where the manual path and the automated path agree, the
   automation is verified. Where they disagree, a bug has been found — and that has already
   happened on this project more than once.

Every lesson also carries a **Concepts — why this works** section. A reader should finish
understanding the reasoning, not merely holding a list of keystrokes. Where a choice was
contested, the lesson names the alternative that was rejected and links the `docs/DECISIONS.md`
entry.

---

## Writing a lesson

Copy [`_LESSON_TEMPLATE.md`](_LESSON_TEMPLATE.md) to `NN-<slug>.md`.

**Fill lessons from work that has actually been done.** A lesson written ahead of the work is
fiction and will be wrong in the details that matter — the parameter that needed changing, the
error that appeared, the runtime. Per the Checkpoint protocol in `CLAUDE.md`, when a phase
completes, its lesson is filled in from that session's real commands *and* the manual
equivalent, while both are still fresh.

If the manual equivalent has never been performed, say so in the lesson rather than inventing
plausible-looking steps.

---

## Lessons

| # | Lesson | Phase | Status |
|---|---|---|---|
| 01 | Designing the geodatabase schema | §4 / W2 | ◻ |
| 02 | Building the schema from config | §4 / W2 | ◻ |
| 03 | Acquiring the data | §3 / W1 | ◻ |
| 04 | [Ingest, standardization, and QA/QC](04-ingest-and-qaqc.md) | §6.3 / W3 | 🔄 |
| 05 | Building the network dataset | §4.6 / W4 | ◻ |
| 06 | Screening candidate sites | §5.1 / W4 | ◻ |
| 07 | Service areas and OD matrices | §5.2 / W5 | ◻ |
| 08 | Workforce metrics from ACS and LODES | §5.3 / W5 | ◻ |
| 09 | Criteria, normalization, and scoring | §5.3–5.5 / W5 | ◻ |
| 10 | Sensitivity analysis | §5.6 / W5 | ◻ |
| 11 | Cartography and map series | §7 / W6 | ◻ |
| 12 | Publishing to AGOL; dashboard and StoryMap | §7.4, §8 / W6–7 | ◻ |

**◻** not started · **🔄** drafted · **✅** verified — both tracks performed and agreeing

---

## See also

- [`../DATA_ACQUISITION.md`](../DATA_ACQUISITION.md) — the manual acquisition playbook, already
  written to this standard
- [`../REPRODUCE.md`](../REPRODUCE.md) — end-to-end reproduction
- [`../DECISIONS.md`](../DECISIONS.md) — why things are the way they are
