import os
import pickle
import re
import shutil
from collections import OrderedDict
from pathlib import Path
import warnings

from pandas import DataFrame, concat, isna, read_csv


class IDManifest:
  """ID-indexed table of paths plus optional readers and data validation."""

  def __init__(self, id_regex, files_by_tag, id_group=None, id_source="filename",
    id_normalizer=None):
    self._id_col = "id"
    self._id_regex = id_regex
    self._id_pattern = re.compile(id_regex)
    self._id_group = id_group
    if id_source not in {"filename", "path"}:
      raise ValueError("`id_source` must be 'filename' or 'path'")
    if id_normalizer is not None and not callable(id_normalizer):
      raise TypeError("`id_normalizer` must be callable")
    self._id_source = id_source
    self._id_normalizer = id_normalizer
    self._copy_root_path = None
    self._df = self._create_dataframe(files_by_tag)
    self._readers = {}
    self._validations = {}
    self._data = OrderedDict()
    self._log = None

  def __repr__(self):
    return f"IDManifest(rows={self.shape()[0]}, columns={list(self.columns())!r})"

  def _extract_id(self, file):
    source = file if self._id_source == "path" else os.path.basename(file)
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

  def _create_id_dict(self, files_by_tag):
    id_dict = OrderedDict()
    for tag, files in files_by_tag.items():
      for file in files:
        file = os.fspath(file)
        file_id = self._extract_id(file)
        if file_id is None:
          raise ValueError(f"File does not contain an ID: {file}")
        id_dict.setdefault(file_id, []).append((tag, file))
    return id_dict

  def _create_dataframe(self, files_by_tag):
    id_dict = self._create_id_dict(files_by_tag)
    columns = [self._id_col] + list(files_by_tag.keys())
    rows = []
    for file_id in sorted(id_dict.keys()):
      row = {self._id_col: file_id}
      for tag, file in id_dict[file_id]:
        row[tag] = file
      rows.append(row)
    return DataFrame(rows, columns=columns)

  def dataframe(self):
    return self._df.copy()

  def ids(self):
    return self._df[self._id_col].copy()

  def columns(self):
    return self._df.columns

  def shape(self):
    return self._df.shape

  def complete_cases(self, columns=None, how="any"):
    if columns is None:
      columns = list(self.columns())
    return self._df[columns].dropna(axis=0, how=how).copy()

  def _normalize_ids(self, ids):
    return [str(file_id) for file_id in ids]

  def _id_range(self, start, stop, prefix="", suffix="", width=None):
    if stop < start:
      raise ValueError("`stop` must be greater than or equal to `start`")
    return [
      f"{prefix}{str(value).zfill(width) if width is not None else value}{suffix}"
      for value in range(start, stop + 1)
    ]

  def missing_ids(self, expected_ids):
    expected = self._normalize_ids(expected_ids)
    observed = set(self.ids().astype(str))
    return [file_id for file_id in expected if file_id not in observed]

  def extra_ids(self, expected_ids):
    expected = set(self._normalize_ids(expected_ids))
    return [file_id for file_id in self.ids().astype(str).to_list() if file_id not in expected]

  def missing_id_range(self, start, stop, prefix="", suffix="", width=None):
    return self.missing_ids(self._id_range(start, stop, prefix=prefix, suffix=suffix, width=width))

  def extra_id_range(self, start, stop, prefix="", suffix="", width=None):
    return self.extra_ids(self._id_range(start, stop, prefix=prefix, suffix=suffix, width=width))

  def ensure_ids(self, expected_ids, extras="keep"):
    if extras not in {"keep", "drop", "raise"}:
      raise ValueError("`extras` must be 'keep', 'drop', or 'raise'")

    expected = self._normalize_ids(expected_ids)
    current = self._df.copy()
    current[self._id_col] = current[self._id_col].astype(str)
    extra = [file_id for file_id in current[self._id_col].to_list() if file_id not in set(expected)]

    if extras == "raise" and extra:
      raise ValueError(f"Manifest contains IDs outside the expected set: {extra}")

    expected_df = DataFrame({self._id_col: expected})
    merged = expected_df.merge(current, how="left", on=self._id_col)

    if extras == "keep" and extra:
      extra_rows = current[current[self._id_col].isin(extra)]
      merged = concat([merged, extra_rows], ignore_index=True)

    self._df = merged.reindex(columns=current.columns)
    return self.dataframe()

  def ensure_id_range(self, start, stop, prefix="", suffix="", width=None, extras="keep"):
    return self.ensure_ids(
      self._id_range(start, stop, prefix=prefix, suffix=suffix, width=width),
      extras=extras
    )

  def summary(self):
    missing = self._df.isna().sum()
    present = self._df.count()
    row_count = self.shape()[0]
    return DataFrame({
      "nonmiss_count": present,
      "nonmiss_perc": round(present / row_count, 2) if row_count else 0,
      "miss_count": missing,
      "miss_perc": round(missing / row_count, 2) if row_count else 0
    })

  def _tracker_read_result(self, column, file_id, present):
    if not present:
      return "missing", None
    if self._log is None:
      return "not_read", None

    value = self._log.loc[self._log[self._id_col] == file_id, column]
    if value.empty or value.isna().all() or value.iloc[0] == "":
      return "not_read", None
    if value.iloc[0] == "Read":
      return "read", None
    if value.iloc[0] == "MISSING":
      return "missing", None
    return "error", value.iloc[0]

  def tracker(self):
    tags = [column for column in list(self.columns()) if column != self._id_col]
    rows = []

    for _, manifest_row in self._df.iterrows():
      file_id = manifest_row[self._id_col]
      row = {self._id_col: file_id}
      present_count = 0
      missing_count = 0
      error_count = 0
      pending_count = 0

      for tag in tags:
        file = manifest_row[tag]
        present = not isna(file)
        status, error = self._tracker_read_result(tag, file_id, present)
        data = self._data.get(tag, {}).get(file_id)

        if present:
          present_count += 1
        else:
          missing_count += 1
        if status == "error":
          error_count += 1
        if status == "not_read":
          pending_count += 1

        row[f"{tag}_path"] = file
        row[f"{tag}_present"] = present
        row[f"{tag}_reader_registered"] = tag in self._readers
        row[f"{tag}_validation_registered"] = tag in self._validations
        row[f"{tag}_read_status"] = status
        row[f"{tag}_read_error"] = error
        row[f"{tag}_nrows"] = getattr(data, "shape", (None, None))[0] if data is not None else None
        row[f"{tag}_ncols"] = getattr(data, "shape", (None, None))[1] if data is not None else None

      if error_count > 0:
        overall_status = "error"
      elif missing_count > 0:
        overall_status = "incomplete"
      elif pending_count > 0:
        overall_status = "pending"
      else:
        overall_status = "complete"

      row["overall_present_count"] = present_count
      row["overall_missing_count"] = missing_count
      row["overall_error_count"] = error_count
      row["overall_pending_count"] = pending_count
      row["overall_status"] = overall_status
      rows.append(row)

    return DataFrame(rows)

  def save_tracker(self, path, **kwargs):
    self.tracker().to_csv(path, **kwargs)

  def add_reader(self, column, func, **kwargs):
    if column not in list(self.columns()):
      raise KeyError(f"{column} not found in manifest")
    self._readers[column] = {"func": func, "kwargs": kwargs}

  def add_validation(self, column, colnames=None, ignore_case=False, check_col_order=True,
    ncols=None, nrows=None, allow_missing_values=False, func=None, **kwargs):
    if column not in list(self.columns()):
      raise KeyError(f"{column} not found in manifest")
    self._validations[column] = {
      "colnames": colnames,
      "ignore_case": ignore_case,
      "check_col_order": check_col_order,
      "ncols": ncols,
      "nrows": nrows,
      "allow_missing_values": allow_missing_values,
      "func": func,
      "kwargs": kwargs
    }

  def validations(self, column=None):
    if column is not None:
      return self._validations.get(column)
    return self._validations.copy()

  def readers(self):
    return self._readers.copy()

  def validate_data(self, data, colnames=None, ignore_case=False, check_col_order=True,
    ncols=None, nrows=None, allow_missing_values=False, func=None, kwargs=None):
    if ncols is not None and ncols != data.shape[1]:
      raise AssertionError(f"`ncols` is {ncols}, but there are {data.shape[1]} columns")
    if nrows is not None and nrows != data.shape[0]:
      raise AssertionError(f"`nrows` is {nrows}, but there are {data.shape[0]} rows")

    if colnames is not None:
      actual = list(data.columns)
      expected = list(colnames)
      if ignore_case:
        actual = [col.lower() for col in actual]
        expected = [col.lower() for col in expected]
      if check_col_order and expected != actual:
        raise AssertionError("Not all columns match in order")
      if not check_col_order and set(expected) != set(actual):
        raise AssertionError("Not all column names match")

    if not allow_missing_values and not data.notna().all().all():
      raise AssertionError("Some columns have missing values")

    if func is not None:
      if kwargs is None:
        kwargs = {}
      result = func(data, **kwargs)
      if result is not None and not result:
        raise AssertionError("Custom validation function failed")

  def read(self, column, file_id, validate=True):
    if column not in list(self.columns()):
      raise KeyError(f"{column} not found in manifest")
    if column not in self._readers:
      raise KeyError(f"You must first add a reader for `{column}`")
    if file_id not in list(self.ids()):
      raise KeyError(f"{file_id} does not exist in manifest")

    file = self._df.loc[self._df[self._id_col] == file_id, column]
    if file.isna().all():
      raise FileNotFoundError(f"{file_id} has no file for `{column}`")

    reader = self._readers[column]
    data = reader["func"](file.iloc[0], **reader["kwargs"])
    if validate and column in self._validations:
      self.validate_data(data, **self._validations[column])
    return data

  def read_all(self, columns=None, ids=None, ignore_missing=True, validate=True,
    log=True, keep_data=True, stop_on_error=True):
    all_columns = [col for col in list(self.columns()) if col != self._id_col]
    columns = all_columns if columns is None else [columns] if isinstance(columns, str) else list(columns)
    ids = list(self.ids()) if ids is None else list(ids)

    missing_readers = set(columns).difference(set(self._readers.keys()))
    if len(missing_readers) > 0:
      raise KeyError(f"The following columns are missing readers: {missing_readers}")

    if validate:
      missing_validations = set(columns).difference(set(self._validations.keys()))
      if len(missing_validations) == len(columns):
        warnings.warn("No validations are registered for these columns; files will be read without validation checks.")
      elif len(missing_validations) > 0:
        warnings.warn(f"The following columns have no validations registered: {missing_validations}")

    self._data = OrderedDict((column, OrderedDict()) for column in columns)
    if log:
      self._log = self._df.copy()
      self._log.loc[:, self._log.columns != self._id_col] = ""
      for column in all_columns:
        self._log.loc[self._df[column].isna(), column] = "MISSING"

    for column in columns:
      ids_to_read = ids
      if ignore_missing:
        present_ids = self._df.loc[self._df[column].notna(), self._id_col].to_list()
        ids_to_read = [file_id for file_id in ids if file_id in present_ids]

      for file_id in ids_to_read:
        try:
          data = self.read(column, file_id, validate=validate)
        except (Exception, AssertionError) as error:
          if stop_on_error:
            raise RuntimeError(f"{file_id} in `{column}`: {error}") from error
          if log:
            self._log.loc[self._log[self._id_col] == file_id, column] = str(error)
          continue

        if log:
          self._log.loc[self._log[self._id_col] == file_id, column] = "Read"
        if keep_data:
          self._data[column][file_id] = data

  def log(self):
    if self._log is None:
      raise RuntimeError("No log exists yet. Run `.read_all(log=True)` first.")
    return self._log.copy()

  def loaded_data(self, column=None, file_id=None):
    if column is not None and file_id is not None:
      return self._data.get(column, {}).get(file_id)
    if column is not None:
      return self._data.get(column)
    if file_id is not None:
      return {column: values.get(file_id) for column, values in self._data.items()}
    return self._data.copy()

  def copy_files(self, root_path, dataframe=None, id_col="id",
    copy_cols=None, mk_dirs=False, overwrite=False, copy_new_only=False, tag_dict=None):
    if overwrite and copy_new_only:
      raise ValueError("`overwrite` and `copy_new_only` cannot both be True")

    self._copy_root_path = os.fspath(root_path)
    dataframe = self._df if dataframe is None else dataframe
    if copy_cols is None:
      copy_cols = dataframe[dataframe.columns.difference([id_col])].columns

    for column in copy_cols:
      out_name = tag_dict.get(column, column) if tag_dict is not None else column
      out_dir = Path(root_path) / out_name
      if not out_dir.is_dir():
        if mk_dirs:
          out_dir.mkdir(parents=True)
        else:
          raise FileNotFoundError("The directory does not exist and `mk_dirs` was set to False")
      if any(out_dir.iterdir()) and not overwrite and not copy_new_only:
        raise FileExistsError(
          "The directory is not empty. Set `overwrite=True` to overwrite files or "
          "`copy_new_only=True` to skip existing files"
        )
      for file in dataframe.loc[dataframe[column].notna(), column]:
        destination = out_dir / os.path.basename(file)
        if copy_new_only and destination.exists():
          continue
        shutil.copy2(file, destination)

  def replace_paths(self, paths=None, use_copy_root_path=False, tag_dict=None):
    if paths is not None and use_copy_root_path:
      raise ValueError("You cannot provide paths and also use the copy root path")
    if paths is None:
      if not use_copy_root_path:
        raise ValueError("Either paths must be specified or `use_copy_root_path` should be True")
      if self._copy_root_path is None:
        raise RuntimeError("You must copy files before using the copy root path")
      paths = {
        column: self._copy_root_path
        for column in self._df.columns
        if column != self._id_col
      }

    df = self._df.copy()
    for column, root_path in paths.items():
      out_name = tag_dict.get(column, column) if tag_dict is not None else column
      for row_idx in df.index[df[column].notna()]:
        file = df.loc[row_idx, column]
        df.loc[row_idx, column] = str(Path(root_path) / out_name / os.path.basename(file))
    self._df = df
    return self.dataframe()

  def save(self, path, **kwargs):
    self._df.to_csv(path, **kwargs)

  def save_log(self, path, **kwargs):
    self.log().to_csv(path, **kwargs)

  def load(self, path, **kwargs):
    self._df = read_csv(path, **kwargs)
    return self.dataframe()

  def load_log(self, path, **kwargs):
    self._log = read_csv(path, **kwargs)
    return self.log()

  def save_pickle(self, path):
    with open(path, "wb") as file:
      pickle.dump(self, file)

  @classmethod
  def load_pickle(cls, path):
    with open(path, "rb") as file:
      return pickle.load(file)
