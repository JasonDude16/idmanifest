from pathlib import Path
import tempfile
import sys

import pandas as pd

sys.path.insert(0, str(Path.cwd() / "src"))

from idmanifest import PathInventory


# 1. Create a temporary workspace that stays alive until tmp.cleanup().
tmp = tempfile.TemporaryDirectory()
root = Path(tmp.name)
data_dir = root / "data"
alpha_dir = data_dir / "alpha"
beta_dir = data_dir / "beta"
alpha_dir.mkdir(parents=True)
beta_dir.mkdir(parents=True)

print(root)


# 2. Create some small CSV files to work with.
def write_csv(path, values):
  pd.DataFrame({"value": values}).to_csv(path, index=False)


write_csv(alpha_dir / "BASE_001_alpha.csv", [1, 2, 3])
write_csv(alpha_dir / "BASE_002_alpha.csv", [4, 5, 6])
write_csv(alpha_dir / "BASE_002_alpha_duplicate.csv", [7, 8, 9])
write_csv(alpha_dir / "no_id_alpha.csv", [10, 11, 12])

write_csv(beta_dir / "BASE_001_beta.csv", [13, 14, 15])
write_csv(beta_dir / "BASE_003_beta.csv", [16, 17, 18])


# 3. Build a file inventory.
paths = {
  "alpha": str(alpha_dir / "*.csv"),
  "beta": str(beta_dir / "*.csv")
}

inventory = PathInventory(paths, id_regex=r"BASE_([0-9]{3})", sort=True)

inventory.all_files()


# 4. Check the inventory.
report = inventory.check()
report.is_valid
report.counts()
report.summary()
report.details()
report.failed_files


# 5. Remove files that failed validation.
removed_counts = inventory.remove_failed_checks(report)

removed_counts
inventory.kept_files()
inventory.removed_files()


# 6. Create an ID-indexed manifest.
manifest = inventory.to_manifest()

manifest.dataframe()
manifest.summary()
manifest.ids()
manifest.complete_cases()


# 7. Add file readers and validations.
def has_positive_values(df):
  return (df["value"] > 0).all()


manifest.add_reader("alpha", pd.read_csv)
manifest.add_reader("beta", pd.read_csv)

manifest.add_validation(
  "alpha",
  colnames=["value"],
  ncols=1,
  allow_missing_values=False,
  func=has_positive_values
)

manifest.add_validation(
  "beta",
  colnames=["value"],
  ncols=1,
  allow_missing_values=False,
  func=has_positive_values
)

manifest.readers()
manifest.validations()


# 8. Read one file, then read all available files.
alpha_001 = manifest.read("alpha", "001")
alpha_001

manifest.read_all(stop_on_error=False)

manifest.log()
manifest.loaded_data("alpha")
manifest.loaded_data("beta", "003")


# 9. Save outputs to the temporary workspace.
manifest_path = root / "manifest.csv"
log_path = root / "read_log.csv"

manifest.save(manifest_path, index=False)
manifest.save_log(log_path, index=False)

manifest_path
log_path

# 10. Clean up when you are finished.
# tmp.cleanup()
