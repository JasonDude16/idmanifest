# idmanifest

Create validated, ID-indexed manifests for research files.

`idmanifest` turns folders of study files into a table where each row is an ID and each column points to one kind of file. It is useful when files arrive over time, IDs appear in filenames or folder paths, and researchers need a clear record of what is present, missing, duplicated, readable, or invalid.

The package never deletes files. Cleanup methods only remove paths from an in-memory inventory before creating a manifest. Copy helpers copy files to a new location when requested.

## Install

```bash
python -m pip install -e .
```

For development:

```bash
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
```

## Core Objects

- `PathInventory`: finds files, extracts IDs, runs checks, and lets you keep or remove paths before manifest creation.
- `CheckReport`: summarizes inventory problems and provides detailed rows for cleanup decisions.
- `IDManifest`: stores the ID-indexed path table, reads and validates files, builds tracker outputs, copies files, and saves results.

## Basic Workflow

```python
from idmanifest import PathInventory

paths = {
  "scores": "data/scores/*.csv",
  "metadata": "data/metadata/*.csv"
}

inventory = PathInventory(
  paths,
  id_regex=r"SUBJ_([0-9]{3})",
  sort=True,
  duplicate_policy="extras"
)

report = inventory.check()

if not report.is_valid:
  print(report.summary())
  print(report.details())
  inventory.remove_failed_checks(report)

manifest = inventory.to_manifest()
manifest.save("manifest.csv", index=False)
```

## Inputs And ID Extraction

Each tag can point to a glob pattern or explicit file list:

```python
PathInventory({"scores": "data/scores/*.csv"}, id_regex=r"SUBJ_([0-9]{3})")

PathInventory(
  {"scores": ["data/scores/SUBJ_001_scores.csv"]},
  id_regex=r"SUBJ_([0-9]{3})"
)
```

`id_regex` controls ID extraction:

```python
PathInventory(paths, id_regex=r"SUBJ_[0-9]{3}")              # whole match
PathInventory(paths, id_regex=r"SUBJ_([0-9]{3})")            # first capture group
PathInventory(paths, id_regex=r"SUBJ_(?P<id>[0-9]{3})")      # named id group
PathInventory(paths, id_regex=r"(SUBJ)_([0-9]{3})", id_group=2)
```

Use `allow_empty=True` when an empty tag is valid for your workflow.

## IDs In Folder Paths

By default, IDs are extracted from filenames. Use `id_source="path"` when IDs are in folder paths:

```text
data/
  SUBJ_001/session-1/scores.csv
  SUBJ_002/session-1/scores.csv
```

```python
inventory = PathInventory(
  {"scores": "data/*/session-*/scores.csv"},
  id_regex=r"SUBJ_([0-9]{3})",
  id_source="path",
  sort=True
)
```

This also works with deeper glob patterns.

## Normalizing Equivalent IDs

Use `id_normalizer` when equivalent IDs appear in different raw styles, such as `SUBJ_001` and `SUBJ001`.

```python
inventory = PathInventory(
  paths,
  id_regex=r"SUBJ_?[0-9]{3}",
  id_normalizer=lambda file_id: file_id.replace("_", "")
)
```

The regex must match the raw styles you expect. The normalizer only changes the extracted ID used for checks and manifest rows; it does not edit files or paths.

## Checks And Reports

```python
report = inventory.check()
report.is_valid
report.counts()
report.summary()
report.details()
report.failed_files
```

Standard checks include invalid IDs, duplicate IDs within a tag, and duplicate file paths across tags.

When `id_source="path"`, you can also require filename IDs to match path IDs:

```python
report = inventory.check(check_path_filename_ids=True)
```

This catches paths like:

```text
data/SUBJ_002/session-1/SUBJ_999_scores.csv
data/SUBJ_003/session-1/scores.csv
```

where the filename ID conflicts with the folder ID or is missing. When enabled, this appears as `path_filename_id_mismatches` in the report.

## Cleaning The Inventory

These methods update the inventory only; they do not delete files.

```python
inventory.remove_matching({"scores": "practice"})
inventory.keep_matching({"scores": "visit1"})
inventory.remove_files({"scores": ["SUBJ_001_bad.csv"]})
inventory.remove_failed_checks(report, checks=["invalid_ids", "duplicate_ids"])
```

Inspect or reset the inventory:

```python
inventory.kept_files()
inventory.removed_files()
inventory.reset()
inventory.refresh()
```

## Working With A Manifest

```python
manifest = inventory.to_manifest()
manifest.dataframe()
manifest.summary()
```

Add expected IDs when you know the desired study roster:

```python
manifest.missing_ids(["001", "002", "003"])
manifest.ensure_ids(["001", "002", "003"], extras="keep")
manifest.ensure_id_range(1, 100, width=3)
```

Register readers and validation rules:

```python
import pandas as pd

manifest.add_reader("scores", pd.read_csv)
manifest.add_validation("scores", colnames=["score", "date"], ncols=2)

data = manifest.read("scores", "001")
manifest.read_all(columns="scores", stop_on_error=False)
manifest.log()
manifest.loaded_data("scores")
```

Custom validation functions are supported:

```python
def has_rows(df, minimum):
  return len(df) >= minimum

manifest.add_validation("scores", func=has_rows, minimum=10)
```

## Tracker Output

`tracker()` creates a status table with paths, missingness, reader/validation registration, read status, errors, and data shapes.

```python
tracker = manifest.tracker()
manifest.save_tracker("tracker.csv", index=False)
```

It includes per-tag columns such as `<tag>_present`, `<tag>_read_status`, `<tag>_read_error`, `<tag>_nrows`, and `<tag>_ncols`, plus overall status counts.

## Copying Files

Copy manifest files into a standardized output tree:

```python
manifest.copy_files("copied_files", mk_dirs=True)
```

For incremental updates, copy only files that are not already present:

```python
manifest.copy_files("copied_files", mk_dirs=True, copy_new_only=True)
```

To intentionally replace destination files:

```python
manifest.copy_files("copied_files", mk_dirs=True, overwrite=True)
```

After copying, rewrite manifest paths to point at the copy destination:

```python
manifest.replace_paths(use_copy_root_path=True)
```

## Saving And Loading

```python
manifest.save("manifest.csv", index=False)
manifest.save_log("read_log.csv", index=False)

manifest.load("manifest.csv")
manifest.load_log("read_log.csv")
```

Pickle helpers are available for local trusted workflows only:

```python
manifest.save_pickle("manifest.pkl")
manifest = IDManifest.load_pickle("manifest.pkl")
```

Never load pickle files from untrusted sources.

## Examples

```bash
python examples/basic_workflow.py
python examples/interactive_workflow.py
```

The interactive workflow demonstrates inventory inspection, reports, duplicate policies, keep/remove workflows, explicit file lists, ID extraction styles, ID normalization, path-based IDs, path/filename ID checks, expected IDs, manifest reading/validation, tracker output, copying files, path replacement, CSV output, pickle output, and refresh behavior.
