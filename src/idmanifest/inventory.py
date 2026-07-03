import glob
import os
import re
from collections import OrderedDict
from collections.abc import Iterable
from itertools import combinations
from pathlib import Path

from pandas import DataFrame

from .manifest import IDManifest
from .report import CheckReport, _copy_file_dict, _empty_file_dict


class PathInventory:
  """Find, validate, subset, and convert ID-coded files into a manifest."""

  VALID_DUPLICATE_POLICIES = {"all", "extras"}

  def __init__(
    self,
    paths,
    id_regex,
    sort=False,
    id_group=None,
    id_source="filename",
    id_normalizer=None,
    duplicate_policy="all",
    allow_empty=False
  ):
    if not isinstance(paths, dict):
      raise TypeError("`paths` must be a dictionary of tag -> glob pattern or file list")
    if not isinstance(id_regex, str):
      raise TypeError("`id_regex` must be a string")
    if not isinstance(sort, bool):
      raise TypeError("`sort` must be True or False")
    if not isinstance(allow_empty, bool):
      raise TypeError("`allow_empty` must be True or False")
    if id_source not in {"filename", "path"}:
      raise ValueError("`id_source` must be 'filename' or 'path'")
    if id_normalizer is not None and not callable(id_normalizer):
      raise TypeError("`id_normalizer` must be callable")
    if duplicate_policy not in self.VALID_DUPLICATE_POLICIES:
      raise ValueError("`duplicate_policy` must be 'all' or 'extras'")

    self._path_inputs = OrderedDict(paths)
    self._id_regex = id_regex
    self._id_pattern = re.compile(id_regex)
    self._id_group = id_group
    self._id_source = id_source
    self._id_normalizer = id_normalizer
    self._sort = sort
    self._allow_empty = allow_empty
    self._duplicate_policy = duplicate_policy
    self._all_files = self._find_files()
    self._kept_files = _copy_file_dict(self._all_files)
    self._removed_files = _empty_file_dict(self._all_files.keys())
    self._last_report = None
    self._check_results = self._new_check_results()

  def __repr__(self):
    total = sum(len(files) for files in self._kept_files.values())
    return f"PathInventory(tags={len(self._kept_files)}, files={total}, id_regex={self._id_regex!r})"

  def _find_files(self):
    files = OrderedDict()
    for tag, source in self._path_inputs.items():
      matched = self._files_from_source(source)
      if len(matched) == 0 and not self._allow_empty:
        raise FileNotFoundError(f"No files were found for `{tag}` using: {source}")
      files[tag] = sorted(matched) if self._sort else matched
    return files

  def _files_from_source(self, source):
    if isinstance(source, (str, os.PathLike)):
      return [str(path) for path in glob.glob(os.fspath(source))]
    if isinstance(source, Iterable):
      return [str(Path(path)) for path in source]
    raise TypeError("Each path source must be a glob pattern, Path, or iterable of files")

  def _new_check_results(self):
    return OrderedDict(
      (method, _empty_file_dict(self._all_files.keys()))
      for method in ("invalid_ids", "duplicate_ids", "duplicate_files", "path_filename_id_mismatches")
    )

  def _extract_id_from_source(self, source):
    match = self._id_pattern.search(source)
    if match is None:
      return None

    if self._id_group is not None:
      file_id = match.group(self._id_group)
    elif "id" in self._id_pattern.groupindex:
      file_id = match.group("id")
    elif self._id_pattern.groups == 1:
      file_id = match.group(1)
    else:
      file_id = match.group(0)
    return self._normalize_id(file_id)

  def _normalize_id(self, file_id):
    if file_id is None or self._id_normalizer is None:
      return file_id
    return self._id_normalizer(file_id)

  def _extract_id(self, file):
    source = file if self._id_source == "path" else os.path.basename(file)
    return self._extract_id_from_source(source)

  def _extract_filename_id(self, file):
    return self._extract_id_from_source(os.path.basename(file))

  def _extract_directory_id(self, file):
    return self._extract_id_from_source(os.path.dirname(file))

  def _normalize_tags(self, tags):
    if tags is None:
      return list(self._kept_files.keys())
    return list(tags)

  def _resolve_file_names(self, files, full_list):
    full_by_basename = {}
    for file in full_list:
      full_by_basename.setdefault(os.path.basename(file), []).append(file)

    resolved = []
    unresolved = []
    ambiguous = []
    for file in files:
      file = os.fspath(file)
      if file in full_list:
        resolved.append(file)
      else:
        matches = full_by_basename.get(os.path.basename(file), [])
        if len(matches) == 1:
          resolved.append(matches[0])
        elif len(matches) > 1:
          ambiguous.append(file)
        else:
          unresolved.append(file)

    if ambiguous:
      raise ValueError(f"Basename matched multiple files: {ambiguous}")
    if unresolved:
      raise FileNotFoundError(f"Files were not found in the current inventory: {unresolved}")
    return resolved

  def _replace_or_append_removed(self, tag, removed):
    self._kept_files[tag] = [file for file in self._kept_files[tag] if file not in removed]
    for file in removed:
      if file not in self._removed_files[tag]:
        self._removed_files[tag].append(file)

  def _keep_only(self, tag, kept):
    removed = [file for file in self._kept_files[tag] if file not in kept]
    self._kept_files[tag] = list(kept)
    for file in removed:
      if file not in self._removed_files[tag]:
        self._removed_files[tag].append(file)

  def id_regex(self):
    return self._id_regex

  def id_source(self):
    return self._id_source

  def id_normalizer(self):
    return self._id_normalizer

  def paths(self):
    return OrderedDict(self._path_inputs)

  def all_files(self):
    return _copy_file_dict(self._all_files)

  def kept_files(self):
    return _copy_file_dict(self._kept_files)

  def removed_files(self):
    return _copy_file_dict(self._removed_files)

  def check_results(self, method=None):
    if method is None:
      return OrderedDict((key, _copy_file_dict(value)) for key, value in self._check_results.items())
    return _copy_file_dict(self._check_results[method])

  def refresh(self):
    self._all_files = self._find_files()
    self.reset()

  def check_invalid_ids(self, tags=None):
    results = _empty_file_dict(self._all_files.keys())
    for tag in self._normalize_tags(tags):
      for file in self._kept_files[tag]:
        if self._extract_id(file) is None:
          results[tag].append({
            "id": None,
            "file": file
          })
    self._check_results["invalid_ids"] = _copy_file_dict(results)
    return results

  def check_duplicate_ids(self, tags=None, policy=None, force=False):
    policy = self._duplicate_policy if policy is None else policy
    if policy not in self.VALID_DUPLICATE_POLICIES:
      raise ValueError("`policy` must be 'all' or 'extras'")

    invalid = self.check_invalid_ids(tags=tags)
    if any(len(files) > 0 for files in invalid.values()) and not force:
      raise ValueError("Not all IDs are valid. Run `.check_invalid_ids()`, or use force=True to skip invalid files.")

    results = _empty_file_dict(self._all_files.keys())
    for tag in self._normalize_tags(tags):
      by_id = OrderedDict()
      for file in self._kept_files[tag]:
        file_id = self._extract_id(file)
        if file_id is None and force:
          continue
        by_id.setdefault(file_id, []).append(file)
      for file_id, files in by_id.items():
        if len(files) > 1:
          duplicate_files = files if policy == "all" else files[1:]
          results[tag].extend({"id": file_id, "file": file} for file in duplicate_files)

    self._check_results["duplicate_ids"] = _copy_file_dict(results)
    return results

  def check_duplicate_files(self, tags_to_compare=None):
    tags = self._normalize_tags(tags_to_compare)
    results = _empty_file_dict(self._all_files.keys())
    for tag1, tag2 in combinations(tags, 2):
      shared = sorted(set(self._kept_files[tag1]).intersection(set(self._kept_files[tag2])))
      for file in shared:
        file_id = self._extract_id(file)
        for tag in (tag1, tag2):
          if not any(value["file"] == file for value in results[tag]):
            results[tag].append({"id": file_id, "file": file})

    self._check_results["duplicate_files"] = _copy_file_dict(results)
    return results

  def _expected_count(self, expected, tag):
    if isinstance(expected, dict):
      if tag not in expected:
        raise KeyError(f"No expected count was provided for `{tag}`")
      return expected[tag]
    return expected

  def check_file_counts(self, expected=1, tags=None, force=False):
    if isinstance(expected, dict):
      for tag, count in expected.items():
        if not isinstance(count, int) or count < 0:
          raise ValueError("Expected counts must be non-negative integers")
    elif not isinstance(expected, int) or expected < 0:
      raise ValueError("`expected` must be a non-negative integer or tag -> count dictionary")

    invalid = self.check_invalid_ids(tags=tags)
    if any(len(files) > 0 for files in invalid.values()) and not force:
      raise ValueError("Not all IDs are valid. Run `.check_invalid_ids()`, or use force=True to skip invalid files.")

    rows = []
    for tag in self._normalize_tags(tags):
      counts = OrderedDict()
      for file in self._kept_files[tag]:
        file_id = self._extract_id(file)
        if file_id is None and force:
          continue
        counts[file_id] = counts.get(file_id, 0) + 1

      expected_count = self._expected_count(expected, tag)
      for file_id, count in counts.items():
        rows.append({
          "tag": tag,
          "id": file_id,
          "count": count,
          "expected": expected_count,
          "matches_expected": count == expected_count
        })

    return DataFrame(rows, columns=["tag", "id", "count", "expected", "matches_expected"])

  def check_path_filename_id_mismatches(self, tags=None):
    if self._id_source != "path":
      raise ValueError("Path/filename ID mismatch checks require `id_source='path'`")

    results = _empty_file_dict(self._all_files.keys())
    for tag in self._normalize_tags(tags):
      for file in self._kept_files[tag]:
        path_id = self._extract_directory_id(file)
        filename_id = self._extract_filename_id(file)
        if path_id is not None and path_id != filename_id:
          results[tag].append({
            "id": path_id,
            "filename_id": filename_id,
            "file": file
          })

    self._check_results["path_filename_id_mismatches"] = _copy_file_dict(results)
    return results

  def check(self, duplicate_policy=None, check_path_filename_ids=False):
    invalid_ids = self.check_invalid_ids()
    duplicate_ids = self.check_duplicate_ids(policy=duplicate_policy, force=True)
    duplicate_files = self.check_duplicate_files()
    path_filename_id_mismatches = None
    if check_path_filename_ids:
      path_filename_id_mismatches = self.check_path_filename_id_mismatches()
    self._last_report = CheckReport(
      invalid_ids,
      duplicate_ids,
      duplicate_files,
      path_filename_id_mismatches
    )
    return self._last_report

  def run_all_checks(self, duplicate_policy=None, check_path_filename_ids=False):
    report = self.check(
      duplicate_policy=duplicate_policy,
      check_path_filename_ids=check_path_filename_ids
    )
    if not report.is_valid:
      counts = ", ".join(f"{key}={value}" for key, value in report.counts().items())
      raise ValueError(f"Inventory checks failed: {counts}")
    return True

  def remove_files(self, files_by_tag):
    counts = OrderedDict()
    for tag, files in files_by_tag.items():
      resolved = self._resolve_file_names(files, self._kept_files[tag])
      self._replace_or_append_removed(tag, resolved)
      counts[tag] = len(resolved)
    return counts

  def keep_files(self, files_by_tag):
    counts = OrderedDict()
    for tag, files in files_by_tag.items():
      resolved = self._resolve_file_names(files, self._kept_files[tag])
      self._keep_only(tag, resolved)
      counts[tag] = len(resolved)
    return counts

  def remove_matching(self, patterns):
    to_remove = OrderedDict()
    for tag, pattern in patterns.items():
      regex = re.compile(pattern)
      to_remove[tag] = [
        file for file in self._kept_files[tag]
        if regex.search(os.path.basename(file)) is not None
      ]
    return self.remove_files(to_remove)

  def keep_matching(self, patterns):
    to_keep = OrderedDict()
    for tag, pattern in patterns.items():
      regex = re.compile(pattern)
      to_keep[tag] = [
        file for file in self._kept_files[tag]
        if regex.search(os.path.basename(file)) is not None
      ]
    return self.keep_files(to_keep)

  def remove_failed_checks(self, report=None, checks=None):
    report = report or self._last_report or self.check()
    check_names = checks or tuple(report.counts().keys())
    files = _empty_file_dict(self._all_files.keys())
    for check_name in check_names:
      for tag, check_files in report.files_for(check_name).items():
        files[tag].extend(file for file in check_files if file not in files[tag])
    return self.remove_files(files)

  def keep_failed_checks(self, report=None, checks=None):
    report = report or self._last_report or self.check()
    check_names = checks or tuple(report.counts().keys())
    files = _empty_file_dict(self._all_files.keys())
    for check_name in check_names:
      for tag, check_files in report.files_for(check_name).items():
        files[tag].extend(file for file in check_files if file not in files[tag])
    return self.keep_files(files)

  def to_manifest(self, validate=True, duplicate_policy=None, check_path_filename_ids=False):
    if validate:
      self.run_all_checks(
        duplicate_policy=duplicate_policy,
        check_path_filename_ids=check_path_filename_ids
      )
    return IDManifest(
      self._id_regex,
      self._kept_files,
      id_group=self._id_group,
      id_source=self._id_source,
      id_normalizer=self._id_normalizer
    )

  def create_manifest(self, validate=True, duplicate_policy=None, check_path_filename_ids=False):
    return self.to_manifest(
      validate=validate,
      duplicate_policy=duplicate_policy,
      check_path_filename_ids=check_path_filename_ids
    )

  def reset(self):
    self._kept_files = _copy_file_dict(self._all_files)
    self._removed_files = _empty_file_dict(self._all_files.keys())
    self._check_results = self._new_check_results()
    self._last_report = None
