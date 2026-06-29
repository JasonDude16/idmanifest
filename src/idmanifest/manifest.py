import os
import pickle
import re
import shutil
from collections import OrderedDict
from pathlib import Path
import warnings

from pandas import DataFrame, concat, read_csv


class IDManifest:
  """ID-indexed table of paths plus optional readers and data validation."""

  def __init__(self, id_regex, files_by_tag, id_group=None):
    self._id_col = "id"
    self._id_regex = id_regex
    self._id_pattern = re.compile(id_regex)
    self._id_group = id_group
    self._copy_root_path = None
    self._df = self._create_dataframe(files_by_tag)
    self._readers = {}
    self._validations = {}
    self._data = OrderedDict()
    self._log = None

  def __repr__(self):
    return f"IDManifest(rows={self.shape()[0]}, columns={list(self.columns())!r})"

  def _extract_id(self, file):
    match = self._id_pattern.search(os.path.basename(file))
    if match is None:
      return None
    if self._id_group is not None:
      return match.group(self._id_group)
    if "id" in self._id_pattern.groupindex:
      return match.group("id")
    if self._id_pattern.groups == 1:
      return match.group(1)
    return match.group(0)

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
    columns = all_columns if columns is None else list(columns)
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
    copy_cols=None, mk_dirs=False, overwrite=False, tag_dict=None):
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
      if any(out_dir.iterdir()) and not overwrite:
        raise FileExistsError("The directory is not empty. Set `overwrite=True` to overwrite current files")
      for file in dataframe.loc[dataframe[column].notna(), column]:
        shutil.copy2(file, out_dir / os.path.basename(file))

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
