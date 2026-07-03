# idmanifest

Create validated, ID-indexed manifests for research files.

`idmanifest` helps turn folders of study files into a table where each row is a participant, sample, session, or other study ID, and each column points to one kind of file. It is designed for workflows where files arrive over time, naming conventions vary a little, and researchers need a clear record of what is present, missing, duplicated, readable, or invalid.

The package never deletes files. Inventory cleanup methods only remove files from the in-memory inventory before creating a manifest. Copy helpers copy files to a new location when requested.

## Core Objects

- `PathInventory`: finds files, extracts IDs, runs checks, and lets you keep/remove paths before manifest creation.
- `CheckReport`: summarizes inventory problems and gives detailed rows for cleanup decisions.
- `IDManifest`: stores the ID-indexed path table, reads and validates files, creates tracker outputs, copies files, and saves results.

## Install

From this repository:

```bash
python -m pip install -e .
```

For development:

```bash
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
```

## Quick Start

```python
from idmanifest import PathInventory

paths = {
  "hypnogram": "data/hypnograms/*.xlsx",
  "artifact": "data/artifacts/*.xlsx"
}

inventory = PathInventory(
  paths,
  id_regex=r"BASE_([0-9]{3})",
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

## Inputs

Each manifest column starts as a tag mapped to either a glob pattern or an explicit file list.

```python
paths = {
  "alpha": "data/alpha/*.csv",
  "beta": "data/beta/*.csv"
}

inventory = PathInventory(paths, id_regex=r"BASE_([0-9]{3})")
```

Explicit file lists are also supported:

```python
inventory = PathInventory(
  {"alpha": ["data/alpha/BASE_001_alpha.csv"]},
  id_regex=r"BASE_([0-9]{3})"
)
```

Empty file groups raise by default. Use `allow_empty=True` when an empty tag is expected:

```python
inventory = PathInventory(
  {"alpha": [], "beta": "data/beta/*.csv"},
  id_regex=r"BASE_([0-9]{3})",
  allow_empty=True
)
```

## ID Extraction

IDs come from `id_regex`. By default, IDs are extracted from filenames.

If the regex has no capture groups, the whole match is used:

```python
PathInventory(paths, id_regex=r"BASE_[0-9]{3}")
```

If the regex has one capture group, that group is used:

```python
PathInventory(paths, id_regex=r"BASE_([0-9]{3})")
```

A named `id` group is supported:

```python
PathInventory(paths, id_regex=r"BASE_(?P<id>[0-9]{3})")
```

You can also select a specific group:

```python
PathInventory(paths, id_regex=r"(BASE)_([0-9]{3})", id_group=2)
```

## IDs In Folder Paths

Some studies store files under participant folders:

```text
data/
  BASE_001/
    session_1/
      exports/
        hypnogram.csv
  BASE_002/
    session_1/
      exports/
        hypnogram.csv
```

Use `id_source="path"` to search the full path instead of only the filename:

```python
inventory = PathInventory(
  {
    "hypnogram": "data/*/session_*/exports/*.csv",
    "artifact": "data/*/artifacts/**/*.csv"
  },
  id_regex=r"BASE_([0-9]{3})",
  id_source="path",
  sort=True
)
```

This is useful with nested glob patterns where the ID folder is not the immediate parent directory.

## Normalizing Equivalent IDs

Use `id_normalizer` when equivalent IDs appear in slightly different raw forms, such as `BASE_001` and `BASE001`.

```python
inventory = PathInventory(
  paths,
  id_regex=r"BASE_?[0-9]{3}",
  id_normalizer=lambda file_id: file_id.replace("_", "")
)
```

The regex must match every raw style you expect. The normalizer only changes the extracted ID used by checks and the manifest. It does not edit files or paths.

```text
data/alpha/BASE_001_alpha.csv  -> manifest id BASE001
data/beta/BASE001_beta.csv     -> manifest id BASE001
```

The original paths remain in the manifest path columns.

## Inventory Checks

Run all standard checks:

```python
report = inventory.check()
report.is_valid
report.counts()
report.summary()
report.details()
report.failed_files
```

Standard checks include:

- `invalid_ids`: files where no ID could be extracted
- `duplicate_ids`: repeated IDs within the same tag
- `duplicate_files`: the same file path appearing under more than one tag

Duplicate ID handling can flag every duplicate or only later extras:

```python
inventory.check_duplicate_ids(policy="all")
inventory.check_duplicate_ids(policy="extras")
```

You can also set the default policy:

```python
inventory = PathInventory(
  paths,
  id_regex=r"BASE_([0-9]{3})",
  duplicate_policy="extras"
)
```

### Path And Filename ID Agreement

When `id_source="path"`, filenames may also contain IDs. You can optionally require the path ID and filename ID to agree.

```python
inventory = PathInventory(
  paths,
  id_regex=r"BASE_?[0-9]{3}",
  id_source="path",
  id_normalizer=lambda file_id: file_id.replace("_", "")
)

report = inventory.check(check_path_filename_ids=True)
```

This catches cases like:

```text
data/BASE_102/session/BASE_999_summary.csv
data/WATCH01/session/measurement.csv
```

The first has a conflicting filename ID. The second has no filename ID at all. When enabled, the check appears in `summary()`, `counts()`, `details()`, and `failed_files` as `path_filename_id_mismatches`.

You can enforce this during manifest creation:

```python
manifest = inventory.to_manifest(check_path_filename_ids=True)
```

## Keeping And Removing Paths

Cleanup methods alter the inventory, not the filesystem.

```python
inventory.remove_matching({"artifact": "practice"})
inventory.keep_matching({"hypnogram": "night1"})
inventory.remove_files({"artifact": ["BASE_101_bad.xlsx"]})
inventory.remove_failed_checks(report, checks=["invalid_ids", "duplicate_ids"])
```

These methods return per-tag counts so scripts can log cleanup decisions.

You can inspect what remains and what was removed:

```python
inventory.kept_files()
inventory.removed_files()
```

Reset back to all currently discovered files:

```python
inventory.reset()
```

Refresh after new files arrive:

```python
inventory.refresh()
```

## Creating A Manifest

After cleanup, create an `IDManifest`:

```python
manifest = inventory.to_manifest()
manifest.dataframe()
manifest.summary()
```

The manifest is a path table:

```text
id    hypnogram                         artifact
001   data/hypnograms/BASE_001.xlsx     data/artifacts/BASE_001.xlsx
002   data/hypnograms/BASE_002.xlsx     NaN
```

`summary()` reports present and missing values by column.

## Expected IDs

Use expected IDs when a study should contain a known set of participants or sessions.

```python
manifest.missing_ids(["001", "002", "003"])
manifest.extra_ids(["001", "002", "003"])
```

`ensure_ids()` makes missing expected IDs explicit by adding rows with missing paths:

```python
manifest.ensure_ids(["001", "002", "003"], extras="keep")
```

Numeric range helpers are inclusive:

```python
manifest.missing_id_range(1, 260, width=3)
manifest.ensure_id_range(1, 260, width=3)
```

Prefixes and suffixes are supported:

```python
manifest.ensure_id_range(1, 260, prefix="BASE_", width=3)
```

Extras can be kept, dropped, or treated as an error:

```python
manifest.ensure_ids(expected_ids, extras="keep")
manifest.ensure_ids(expected_ids, extras="drop")
manifest.ensure_ids(expected_ids, extras="raise")
```

## Reading And Validating Data

Register readers by manifest column:

```python
import pandas as pd

manifest.add_reader("hypnogram", pd.read_excel, engine="openpyxl")
manifest.add_reader("artifact", pd.read_csv)
```

Register validation rules:

```python
manifest.add_validation(
  "hypnogram",
  colnames=["epoch", "stage"],
  ncols=2,
  allow_missing_values=False
)
```

Custom validation functions are supported:

```python
def has_required_rows(df, minimum):
  return len(df) >= minimum

manifest.add_validation("hypnogram", func=has_required_rows, minimum=100)
```

Read one file:

```python
data = manifest.read("hypnogram", "001")
```

Read all files, or a subset of columns and IDs:

```python
manifest.read_all(stop_on_error=False)
manifest.read_all(columns="hypnogram", stop_on_error=False)
manifest.read_all(columns=["hypnogram", "artifact"], ids=["001", "002"], stop_on_error=False)
```

Inspect read outcomes:

```python
manifest.log()
manifest.loaded_data("hypnogram")
manifest.loaded_data("hypnogram", "001")
```

Use `keep_data=False` when you only want the read/validation log and do not want to keep loaded data in memory:

```python
manifest.read_all(columns="hypnogram", keep_data=False, stop_on_error=False)
```

## Tracker Output

`tracker()` creates a researcher-friendly table that combines paths, missingness, reader/validation registration, read status, validation errors, and loaded data shapes.

```python
tracker = manifest.tracker()
manifest.save_tracker("master_tracker.csv", index=False)
```

Per-tag columns include:

```text
<tag>_path
<tag>_present
<tag>_reader_registered
<tag>_validation_registered
<tag>_read_status
<tag>_read_error
<tag>_nrows
<tag>_ncols
```

Overall columns include:

```text
overall_present_count
overall_missing_count
overall_error_count
overall_pending_count
overall_status
```

`overall_status` is one of:

- `complete`
- `pending`
- `incomplete`
- `error`

## Copying Files

Copy manifest files into a standardized output tree:

```python
manifest.copy_files("copied_files", mk_dirs=True)
```

By default, copying to a non-empty destination tag folder raises an error. This protects existing files.

For incremental study updates, copy only files that are not already present:

```python
manifest.copy_files("copied_files", mk_dirs=True, copy_new_only=True)
```

To intentionally replace destination files:

```python
manifest.copy_files("copied_files", mk_dirs=True, overwrite=True)
```

`overwrite=True` and `copy_new_only=True` cannot both be used.

After copying, rewrite manifest paths to point at the copy destination:

```python
manifest.replace_paths(use_copy_root_path=True)
```

You can also provide replacement roots manually:

```python
manifest.replace_paths({"hypnogram": "/new/root"})
```

## Saving And Loading

Save the manifest and read log as CSV:

```python
manifest.save("manifest.csv", index=False)
manifest.save_log("read_log.csv", index=False)
```

Load CSVs back into the object:

```python
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

Run a complete terminal example:

```bash
python examples/basic_workflow.py
```

For a fuller line-by-line IDE walkthrough:

```bash
python examples/interactive_workflow.py
```

The interactive workflow demonstrates inventory inspection, reports, duplicate policies, keep/remove workflows, explicit file lists, ID extraction styles, ID normalization, path-based IDs, path/filename ID agreement checks, expected IDs, manifest reading/validation, tracker output, copying files, path replacement, CSV output, pickle output, and refresh behavior.
