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
  path_filename_id_mismatches: OrderedDict = None

  def _result_sets(self):
    results = OrderedDict({
      "invalid_ids": self.invalid_ids,
      "duplicate_ids": self.duplicate_ids,
      "duplicate_files": self.duplicate_files
    })
    if self.path_filename_id_mismatches is not None:
      results["path_filename_id_mismatches"] = self.path_filename_id_mismatches
    return results

  @property
  def is_valid(self):
    return all(count == 0 for count in self.counts().values())

  @property
  def failed_files(self):
    failed = _empty_file_dict(self.invalid_ids.keys())
    for results in self._result_sets().values():
      for tag, files in results.items():
        for value in files:
          file = value["file"] if isinstance(value, dict) else value
          if file not in failed[tag]:
            failed[tag].append(file)
    return failed

  def counts(self):
    return OrderedDict(
      (check_name, sum(len(files) for files in results.values()))
      for check_name, results in self._result_sets().items()
    )

  def summary(self):
    counts = self.counts()
    return DataFrame({
      "check": list(counts.keys()),
      "failed_file_count": list(counts.values())
    })

  def details(self):
    rows = []
    check_reasons = {
      "invalid_ids": "Filename did not match the ID pattern",
      "duplicate_ids": "ID appeared more than once within a tag",
      "duplicate_files": "Same file path appeared in more than one tag",
      "path_filename_id_mismatches": "ID in the file path did not match the ID in the filename"
    }
    for check_name, results in self._result_sets().items():
      reason = check_reasons[check_name]
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
    columns = ["check", "tag", "id", "file", "reason"]
    extra_columns = []
    for row in rows:
      for column in row.keys():
        if column not in columns and column not in extra_columns:
          extra_columns.append(column)
    return DataFrame(rows, columns=columns + extra_columns)

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
    path_filename_id_mismatches = None
    if self.path_filename_id_mismatches is not None:
      path_filename_id_mismatches = _copy_file_dict(self.path_filename_id_mismatches)
    return CheckReport(
      _copy_file_dict(self.invalid_ids),
      _copy_file_dict(self.duplicate_ids),
      _copy_file_dict(self.duplicate_files),
      path_filename_id_mismatches
    )
