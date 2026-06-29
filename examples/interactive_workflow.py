"""
Interactive idmanifest walkthrough.

This script is intentionally verbose. It is meant for IDE line-by-line use,
not as a unit test. Run it from the project root:

  /Volumes/Projects/personal/idmanifest

Objects such as tmp, root, inventory, report, manifest, and copied_manifest
are left in memory so you can inspect them after each section. The temporary
workspace is not deleted unless you run tmp.cleanup() at the bottom.
"""

from pathlib import Path
import sys
import tempfile

import pandas as pd

sys.path.insert(0, str(Path.cwd() / "src"))

from idmanifest import IDManifest, PathInventory


def section(title):
  print(f"\n=== {title} ===")


def show(title, value):
  print(f"\n{title}")
  print(value)
  return value


def write_csv(path, values, group="A", include_note=False):
  df = pd.DataFrame({"value": values, "group": [group] * len(values)})
  if include_note:
    df["note"] = ["ok"] * len(values)
  df.to_csv(path, index=False)


def read_csv_with_path(path):
  df = pd.read_csv(path)
  df.attrs["source_path"] = str(path)
  return df


def has_positive_values(df):
  return (df["value"] > 0).all()


def has_at_least_rows(df, minimum):
  return len(df) >= minimum


# 1. Create a temporary workspace that persists until tmp.cleanup().
section("Create example workspace")
tmp = tempfile.TemporaryDirectory()
root = Path(tmp.name)
data_dir = root / "data"
alpha_dir = data_dir / "alpha"
beta_dir = data_dir / "beta"
gamma_dir = data_dir / "gamma"
for directory in (alpha_dir, beta_dir, gamma_dir):
  directory.mkdir(parents=True)

root


# 2. Create sample files with intentional problems and edge cases.
section("Create example files")
write_csv(alpha_dir / "BASE_001_alpha.csv", [1, 2, 3], group="alpha")
write_csv(alpha_dir / "BASE_002_alpha.csv", [4, 5, 6], group="alpha")
write_csv(alpha_dir / "BASE_002_alpha_duplicate.csv", [7, 8, 9], group="alpha")
write_csv(alpha_dir / "BASE_004_practice_alpha.csv", [10, 11], group="alpha")
write_csv(alpha_dir / "no_id_alpha.csv", [12, 13], group="alpha")

write_csv(beta_dir / "BASE_001_beta.csv", [21, 22, 23], group="beta")
write_csv(beta_dir / "BASE_003_beta.csv", [31, 32, 33], group="beta")
write_csv(beta_dir / "BASE_004_practice_beta.csv", [41, 42], group="beta")

write_csv(gamma_dir / "BASE_001_gamma.csv", [101, 102], group="gamma", include_note=True)
write_csv(gamma_dir / "BASE_003_gamma_bad.csv", [-1, 2], group="gamma", include_note=True)
write_csv(gamma_dir / "BASE_005_gamma.csv", [501, 502], group="gamma", include_note=True)

paths = {
  "alpha": str(alpha_dir / "*.csv"),
  "beta": str(beta_dir / "*.csv"),
  "gamma": str(gamma_dir / "*.csv")
}

show("Glob inputs", paths)


# 3. Build a PathInventory with a capture-group ID regex.
section("Build an inventory")
inventory = PathInventory(paths, id_regex=r"BASE_([0-9]{3})", sort=True)
inventory
inventory.id_regex()
inventory.paths()
all_files = inventory.all_files()
show("All files", all_files)


# 4. Run checks and inspect both summary and detailed report rows.
section("Check the inventory")
report = inventory.check(duplicate_policy="all")
report.is_valid
report.counts()
summary = report.summary()
details = report.details()
failed_files = report.failed_files
show("Check summary", summary)
show("Check details", details)
show("Failed files", failed_files)

# You can also run one check at a time.
invalid_only = inventory.check_invalid_ids()
duplicate_ids_all = inventory.check_duplicate_ids(policy="all", force=True)
duplicate_ids_extras = inventory.check_duplicate_ids(policy="extras", force=True)
duplicate_files = inventory.check_duplicate_files()
invalid_only
duplicate_ids_all
duplicate_ids_extras
duplicate_files


# 5. Demonstrate duplicate policies.
section("Duplicate ID policies")
inventory_all_policy = PathInventory(paths, r"BASE_([0-9]{3})", sort=True, duplicate_policy="all")
inventory_extras_policy = PathInventory(paths, r"BASE_([0-9]{3})", sort=True, duplicate_policy="extras")

report_all_policy = inventory_all_policy.check()
report_extras_policy = inventory_extras_policy.check()

show("All duplicate files are flagged", report_all_policy.details())
show("Only duplicate extras are flagged", report_extras_policy.details())


# 6. Remove invalid files, duplicate extras, and practice files.
section("Clean inventory with explicit choices")
clean_inventory = PathInventory(paths, r"BASE_([0-9]{3})", sort=True, duplicate_policy="extras")
clean_report = clean_inventory.check()

# Remove only invalid IDs and duplicate extras. This keeps the first BASE_002 alpha file.
removed_failed = clean_inventory.remove_failed_checks(
  clean_report,
  checks=["invalid_ids", "duplicate_ids"]
)

# Remove practice files by filename pattern.
removed_practice = clean_inventory.remove_matching({
  "alpha": "practice",
  "beta": "practice"
})

removed_failed
removed_practice
clean_inventory.kept_files()
clean_inventory.removed_files()

# Basename removal works when basenames are unique in the current tag.
removed_by_basename = clean_inventory.remove_files({
  "gamma": ["BASE_005_gamma.csv"]
})
removed_by_basename
clean_inventory.kept_files()


# 7. Demonstrate keep workflows on a separate inventory.
section("Keep workflows")
keep_demo = PathInventory(paths, r"BASE_([0-9]{3})", sort=True, duplicate_policy="extras")
keep_demo.keep_matching({"alpha": "BASE_001|BASE_002"})
keep_demo.kept_files()
keep_demo.removed_files()
keep_demo.reset()
keep_demo.kept_files()


# 8. Demonstrate explicit file-list input and allow_empty.
section("Explicit file lists and empty tags")
explicit_inventory = PathInventory(
  {
    "alpha": [alpha_dir / "BASE_001_alpha.csv", alpha_dir / "BASE_002_alpha.csv"],
    "empty_ok": []
  },
  id_regex=r"BASE_([0-9]{3})",
  sort=True,
  allow_empty=True
)
explicit_inventory.all_files()
explicit_inventory.check().summary()


# 9. Demonstrate named and explicit ID groups.
section("ID extraction styles")
named_group_inventory = PathInventory(
  {"alpha": str(alpha_dir / "BASE_001_alpha.csv")},
  id_regex=r"BASE_(?P<id>[0-9]{3})"
)
explicit_group_inventory = PathInventory(
  {"alpha": str(alpha_dir / "BASE_001_alpha.csv")},
  id_regex=r"(BASE)_([0-9]{3})",
  id_group=2
)

named_group_inventory.to_manifest().ids().to_list()
explicit_group_inventory.to_manifest().ids().to_list()


# 10. Create a manifest from the cleaned inventory.
section("Create manifest")
manifest = clean_inventory.to_manifest()
manifest
manifest.dataframe()
manifest.summary()
manifest.ids().to_list()
manifest.columns().to_list()
manifest.complete_cases()
manifest.complete_cases(columns=["id", "alpha", "beta", "gamma"])


# 10.5. Add expected IDs to make intentionally missing rows explicit.
section("Expected IDs and ranges")
expected_ids = ["001", "002", "003", "004", "005"]
manifest.missing_ids(expected_ids)
manifest.extra_ids(expected_ids)
manifest.ensure_ids(expected_ids, extras="keep")
manifest.dataframe()

base_manifest = clean_inventory.to_manifest()
base_manifest.missing_id_range(1, 5, width=3)
base_manifest.ensure_id_range(1, 5, width=3, extras="keep")
base_manifest.dataframe()

# This mirrors a BASE101-BASE260 workflow when your extracted IDs include the prefix.
base_prefixed = PathInventory({"alpha": str(alpha_dir / "*.csv")}, r"(BASE[0-9]{3})", sort=True, duplicate_policy="extras")
base_prefixed.remove_failed_checks(base_prefixed.check(), checks=["invalid_ids", "duplicate_ids"])
base_prefixed_manifest = base_prefixed.to_manifest()
base_prefixed_manifest.missing_id_range(1, 5, prefix="BASE", width=3)
base_prefixed_manifest.ensure_id_range(1, 5, prefix="BASE", width=3, extras="keep")
base_prefixed_manifest.dataframe()


# 11. Add readers and validations.
section("Readers and validations")
manifest.add_reader("alpha", read_csv_with_path)
manifest.add_reader("beta", read_csv_with_path)
manifest.add_reader("gamma", read_csv_with_path)

manifest.add_validation(
  "alpha",
  colnames=["value", "group"],
  ncols=2,
  allow_missing_values=False,
  func=has_positive_values
)
manifest.add_validation(
  "beta",
  colnames=["value", "group"],
  ncols=2,
  allow_missing_values=False,
  func=has_positive_values
)
manifest.add_validation(
  "gamma",
  colnames=["value", "group", "note"],
  ncols=3,
  allow_missing_values=False,
  func=has_positive_values
)

manifest.readers()
manifest.validations()


# 12. Read one file and inspect dataframe metadata.
section("Read one file")
alpha_001 = manifest.read("alpha", "001")
alpha_001
alpha_001.attrs

# Direct validation is available if you already have a dataframe.
manifest.validate_data(alpha_001, colnames=["value", "group"], func=has_at_least_rows, kwargs={"minimum": 3})


# 13. Read all files, logging validation failures instead of stopping.
section("Read all files with logging")
manifest.read_all(stop_on_error=False)
read_log = manifest.log()
loaded_alpha = manifest.loaded_data("alpha")
loaded_gamma_001 = manifest.loaded_data("gamma", "001")
loaded_gamma_003 = manifest.loaded_data("gamma", "003")

show("Read log", read_log)
loaded_alpha
loaded_gamma_001
loaded_gamma_003


# 14. Read a subset of columns and IDs.
section("Read a subset")
manifest.read_all(columns=["beta"], ids=["001", "003"], stop_on_error=False)
manifest.log()
manifest.loaded_data("beta")


# 15. Demonstrate error handling with try/except.
section("Expected errors")
try:
  manifest.read("alpha", "999")
except KeyError as error:
  missing_id_error = error

try:
  manifest.read("missing_column", "001")
except KeyError as error:
  missing_column_error = error

try:
  clean_inventory.remove_files({"alpha": ["not_in_inventory.csv"]})
except FileNotFoundError as error:
  missing_file_error = error

missing_id_error
missing_column_error
missing_file_error


# 16. Save and reload manifest CSV and log CSV.
section("Save and load CSV outputs")
outputs_dir = root / "outputs"
outputs_dir.mkdir()
manifest_path = outputs_dir / "manifest.csv"
log_path = outputs_dir / "read_log.csv"
manifest.save(manifest_path, index=False)
manifest.save_log(log_path, index=False)

reloaded_manifest_df = manifest.load(manifest_path)
reloaded_log_df = manifest.load_log(log_path)
manifest_path
log_path
reloaded_manifest_df
reloaded_log_df


# 17. Copy source files into a clean output tree and rewrite manifest paths.
section("Copy files and replace paths")
copy_root = root / "copied_files"
manifest.copy_files(copy_root, mk_dirs=True)
copy_root
sorted(path.name for path in (copy_root / "alpha").glob("*.csv"))
sorted(path.name for path in (copy_root / "beta").glob("*.csv"))
sorted(path.name for path in (copy_root / "gamma").glob("*.csv"))

copied_manifest = manifest.replace_paths(use_copy_root_path=True)
copied_manifest


# 18. Pickle is available for local trusted workflows only.
section("Pickle local object state")
pickle_path = outputs_dir / "manifest.pkl"
manifest.save_pickle(pickle_path)
loaded_manifest = IDManifest.load_pickle(pickle_path)
loaded_manifest
loaded_manifest.dataframe()


# 19. Refresh example after adding a new file.
section("Refresh inventory")
refresh_inventory = PathInventory({"alpha": str(alpha_dir / "*.csv")}, r"BASE_([0-9]{3})", sort=True)
len(refresh_inventory.all_files()["alpha"])
write_csv(alpha_dir / "BASE_006_alpha_new.csv", [61, 62], group="alpha")
refresh_inventory.refresh()
len(refresh_inventory.all_files()["alpha"])
refresh_inventory.all_files()


# 20. Cleanup when finished.
section("Cleanup")
root
# Run this manually when you are finished exploring:
# tmp.cleanup()
