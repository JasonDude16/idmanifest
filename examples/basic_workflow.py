import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from idmanifest import PathInventory


ID_REGEX = r"BASE_([0-9]{3})"


def write_csv(path, values):
  pd.DataFrame({"value": values}).to_csv(path, index=False)


def print_file_dict(title, file_dict):
  print(f"\n{title}")
  for tag, files in file_dict.items():
    print(f"  {tag}:")
    for file in files:
      print(f"    - {Path(file).name}")


def build_example_files(root):
  data_dir = root / "data"
  alpha_dir = data_dir / "alpha"
  beta_dir = data_dir / "beta"
  alpha_dir.mkdir(parents=True)
  beta_dir.mkdir(parents=True)

  write_csv(alpha_dir / "BASE_001_alpha.csv", [1, 2, 3])
  write_csv(alpha_dir / "BASE_002_alpha.csv", [4, 5, 6])
  write_csv(alpha_dir / "BASE_002_alpha_duplicate.csv", [7, 8, 9])
  write_csv(alpha_dir / "no_id_alpha.csv", [10, 11, 12])

  write_csv(beta_dir / "BASE_001_beta.csv", [13, 14, 15])
  write_csv(beta_dir / "BASE_003_beta.csv", [16, 17, 18])

  return {
    "alpha": str(alpha_dir / "*.csv"),
    "beta": str(beta_dir / "*.csv")
  }


def has_positive_values(df):
  return (df["value"] > 0).all()


def main():
  with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    paths = build_example_files(root)

    print("Example workspace")
    print(root)

    inventory = PathInventory(paths, id_regex=ID_REGEX, sort=True)
    print_file_dict("All files found", inventory.all_files())

    report = inventory.check(duplicate_policy="all")
    print("\nCheck summary")
    print(report.summary().to_string(index=False))
    print("\nCheck details")
    print(report.details().to_string(index=False))
    print_file_dict("Files that failed checks", report.failed_files)

    removed_counts = inventory.remove_failed_checks(report)
    print("\nRemoved failed files")
    for tag, count in removed_counts.items():
      print(f"  {tag}: {count}")

    print_file_dict("Files kept after cleanup", inventory.kept_files())

    manifest = inventory.to_manifest()
    print("\nManifest")
    print(manifest.dataframe().to_string(index=False))

    print("\nManifest summary")
    print(manifest.summary().to_string())

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

    alpha_001 = manifest.read("alpha", "001")
    print("\nRead one file: alpha / 001")
    print(alpha_001.to_string(index=False))

    manifest.read_all(stop_on_error=False)
    print("\nRead log")
    print(manifest.log().to_string(index=False))

    manifest_path = root / "manifest.csv"
    log_path = root / "read_log.csv"
    manifest.save(manifest_path, index=False)
    manifest.save_log(log_path, index=False)

    print("\nSaved outputs")
    print(f"  manifest: {manifest_path}")
    print(f"  read log: {log_path}")


if __name__ == "__main__":
  main()
