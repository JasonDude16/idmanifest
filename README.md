# idmanifest

Create validated, ID-indexed file manifests from folders where filenames encode subject, participant, sample, or session IDs.

`idmanifest` is built around three concepts:

- `PathInventory`: finds files, extracts IDs, validates file collections, and removes or keeps files.
- `CheckReport`: summarizes invalid IDs, duplicate IDs, duplicate file paths, and detailed cleanup rows.
- `IDManifest`: stores an ID-indexed table of paths and can read, validate, copy, and save the files those paths point to.

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

## Basic Workflow

```python
from idmanifest import PathInventory

paths = {
  "hypnogram": "data/hypnograms/*.xlsx",
  "artifact": "data/artifacts/*.xlsx"
}

inventory = PathInventory(paths, id_regex=r"BASE_([0-9]{3})", sort=True)
report = inventory.check()

if not report.is_valid:
  print(report.summary())
  print(report.details())
  inventory.remove_failed_checks(report)

manifest = inventory.to_manifest()
manifest.save("manifest.csv", index=False)
```

## ID Extraction

The ID comes from `id_regex`.

If the regex has no capture groups, the whole match is used:

```python
PathInventory(paths, id_regex=r"BASE_[0-9]{3}")
```

If the regex has one capture group, that group is used:

```python
PathInventory(paths, id_regex=r"BASE_([0-9]{3})")
```

If the regex has a named `id` group, that group is used:

```python
PathInventory(paths, id_regex=r"BASE_(?P<id>[0-9]{3})")
```

You can also select a specific group:

```python
PathInventory(paths, id_regex=r"(BASE)_([0-9]{3})", id_group=2)
```

## Inputs

Each tag can point to a glob pattern:

```python
PathInventory({"alpha": "data/alpha/*.csv"}, id_regex=r"BASE_([0-9]{3})")
```

Or to an explicit list of files:

```python
PathInventory({"alpha": ["data/alpha/BASE_001.csv"]}, id_regex=r"BASE_([0-9]{3})")
```

Empty tags raise by default. Use `allow_empty=True` when empty file groups are valid for your workflow.

## Checks And Reports

```python
report = inventory.check()
report.is_valid
report.counts()
report.summary()
report.details()
report.failed_files
```

Duplicate ID handling is explicit:

```python
inventory.check_duplicate_ids(policy="all")     # flag every file with a duplicated ID
inventory.check_duplicate_ids(policy="extras")  # keep the first file, flag later files
```

You can also set the default policy:

```python
inventory = PathInventory(paths, id_regex=r"BASE_([0-9]{3})", duplicate_policy="extras")
```

## Remove Or Keep Files

```python
inventory.remove_matching({"artifact": "practice"})
inventory.keep_matching({"hypnogram": "night1"})
inventory.remove_files({"artifact": ["BASE_101_bad.xlsx"]})
inventory.remove_failed_checks(report, checks=["invalid_ids", "duplicate_ids"])
```

These methods return per-tag counts so scripts can log what changed.

## Read And Validate Data

```python
import pandas as pd

manifest.add_reader("hypnogram", pd.read_excel, engine="openpyxl")
manifest.add_validation(
  "hypnogram",
  colnames=["epoch", "stage"],
  ignore_case=True,
  allow_missing_values=False
)

data = manifest.read("hypnogram", "101")
manifest.read_all(columns=["hypnogram"], stop_on_error=False)
manifest.log()
manifest.loaded_data("hypnogram")
```

Custom validation functions are supported:

```python
def has_required_rows(df, minimum):
  return len(df) >= minimum

manifest.add_validation("hypnogram", func=has_required_rows, minimum=100)
```

## Examples

Run a complete terminal example:

```bash
python examples/basic_workflow.py
```

For line-by-line IDE exploration, open and run:

```bash
examples/interactive_workflow.py
```

Set your IDE working directory to the project root before running the interactive example.

## Persistence

Use CSV for normal, portable output:

```python
manifest.save("manifest.csv", index=False)
manifest.save_log("read_log.csv", index=False)
```

Pickle helpers are available for local trusted workflows only:

```python
manifest.save_pickle("manifest.pkl")
manifest = IDManifest.load_pickle("manifest.pkl")
```

Never load pickle files from untrusted sources.
