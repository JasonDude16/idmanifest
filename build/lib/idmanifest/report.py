from collections import OrderedDict
from dataclasses import dataclass

from pandas import DataFrame


def _empty_file_dict(tags):
  return OrderedDict((tag, []) for tag in tags)


def _copy_file_dict(file_dict):
  return OrderedDict((tag, list(files)) for tag, files in file_dict.items())


@dataclass
class CheckReport:
  """Results from validating a path inventory."""

  invalid_ids: OrderedDict
  duplicate_ids: OrderedDict
  duplicate_files: OrderedDict

  @property
  def is_valid(self):
    return all(count == 0 for count in self.counts().values())

  @property
  def failed_files(self):
    failed = _empty_file_dict(self.invalid_ids.keys())
    for results in (self.invalid_ids, self.duplicate_ids, self.duplicate_files):
      for tag, files in results.items():
        for value in files:
          file = value["file"] if isinstance(value, dict) else value
          if file not in failed[tag]:
            failed[tag].append(file)
    return failed

  def counts(self):
    return OrderedDict({
      "invalid_ids": sum(len(files) for files in self.invalid_ids.values()),
      "duplicate_ids": sum(len(files) for files in self.duplicate_ids.values()),
      "duplicate_files": sum(len(files) for files in self.duplicate_files.values())
    })

  def summary(self):
    counts = self.counts()
    return DataFrame({
      "check": list(counts.keys()),
      "failed_file_count": list(counts.values())
    })

  def details(self):
    rows = []
    for check_name, reason, results in (
      ("invalid_ids", "Filename did not match the ID pattern", self.invalid_ids),
      ("duplicate_ids", "ID appeared more than once within a tag", self.duplicate_ids),
      ("duplicate_files", "Same file path appeared in more than one tag", self.duplicate_files)
    ):
      for tag, files in results.items():
        for file_info in files:
          if isinstance(file_info, dict):
            row = dict(file_info)
            row.setdefault("check", check_name)
            row.setdefault("tag", tag)
            row.setdefault("reason", reason)
          else:
            row = {
              "check": check_name,
              "tag": tag,
              "id": None,
              "file": file_info,
              "reason": reason
            }
          rows.append(row)
    return DataFrame(rows, columns=["check", "tag", "id", "file", "reason"])

  def files_for(self, check_name):
    results = getattr(self, check_name)
    files = _empty_file_dict(results.keys())
    for tag, values in results.items():
      for value in values:
        file = value["file"] if isinstance(value, dict) else value
        if file not in files[tag]:
          files[tag].append(file)
    return files

  def copy(self):
    return CheckReport(
      _copy_file_dict(self.invalid_ids),
      _copy_file_dict(self.duplicate_ids),
      _copy_file_dict(self.duplicate_files)
    )
