# Spoke repository sync manifest

This repository is the **hub** and is authoritative. Four **spoke** repositories republish
curated extracts of it as focused standalone projects.

The machine-readable manifest is [`tools/spokes.yaml`](../tools/spokes.yaml); the sync is
performed by [`tools/sync_spokes.py`](../tools/sync_spokes.py). This document explains what they
do and why. The decision itself is **D-012**.

## The four spokes

| Repository | Kind | Content |
|---|---|---|
| [config-driven-geodatabase-schema-builder](https://github.com/ndeogobernard/config-driven-geodatabase-schema-builder) | tool | 14 files · schema config, builder code, validation tests, CI |
| [arcgis-location-intelligence-toolbox](https://github.com/ndeogobernard/arcgis-location-intelligence-toolbox) | tool | 19 files · the `.pyt`, its `li` modules, configs, tests, CI |
| [dfw-site-selection-explorer](https://github.com/ndeogobernard/dfw-site-selection-explorer) | showcase | spec + structure; auto-filled weeks 6–8 |
| [dfw-site-selection-cartography](https://github.com/ndeogobernard/dfw-site-selection-cartography) | showcase | spec + structure; auto-filled weeks 6–8 |

## Direction of travel

**Hub → spoke, always.** Never the reverse.

A file listed in the manifest is owned by the hub. Editing it in a spoke means the next sync
silently overwrites the change. If a spoke needs a file changed, change it in the hub and
re-sync.

Files a spoke owns outright — its `README.md`, its `.github/workflows/`, its `.gitignore` — are
**not** in the manifest and are never touched by the sync. That is the whole separation: the
manifest lists shared source, and everything else belongs to the spoke.

## Running a sync

```bash
python tools/sync_spokes.py --list
```

```bash
python tools/sync_spokes.py --dry-run
```

```bash
python tools/sync_spokes.py
```

The script copies only what the manifest names, skips files already identical, **never deletes
anything**, and exits non-zero if a manifest entry no longer exists in the hub — so a rename
here surfaces immediately rather than quietly dropping a file from a spoke.

Spokes are expected beside the hub. Override with `--parent`.

## Accepted duplication

Both tool spokes carry `src/li/config.py`, `logging_utils.py`, and `gdb.py`, plus overlapping
config files. That is deliberate.

The alternative — a shared package on PyPI, or git submodules — would make each spoke unable to
stand alone. A reader landing on the schema builder from a portfolio link should be able to
clone it and run the tests, not discover it is a shell around a dependency. For a portfolio, a
repository that cannot be run on its own has failed at its only job.

The cost is that a change to `gdb.py` must be synced to two places. The manifest and the script
make that one command, and the Checkpoint protocol makes it routine.

## Pending content

Some manifest entries name files that do not exist in the hub yet. They are listed under
`pending:` rather than `files:`, so the sync does not fail on them, and they move up as the work
lands:

- **Schema builder** — ERD, data dictionary, GDB design rationale, optional PostGIS DDL.
  Deliberately deferred: acceptance criterion §13.5 requires these to match the delivered schema
  *exactly*, and the schema changes once D-008 and D-009 are settled. **This spoke re-syncs
  after recon reconciles `config/schema.yaml`.**
- **Toolbox** — tools 2–13 and the ModelBuilder models, as each is built.
- **Showcases** — dashboard and map-series scripts, exports, and screenshots, weeks 6–8.

## Keeping it honest

Every spoke README carries a one-line cross-link naming the hub:

> A component of [dsg-dfw-site-selection](https://github.com/ndeogobernard/dsg-dfw-site-selection),
> a DFW regional-DC site-selection system.

The spokes are presented as what they are — components of one system, extracted because they are
independently useful. Nothing is disguised as unrelated work.

## When to sync

At **Checkpoint**, whenever a manifest-listed file changed. Verify with:

```bash
python tools/sync_spokes.py --dry-run
```

If it reports files to copy, sync and push the affected spokes.
