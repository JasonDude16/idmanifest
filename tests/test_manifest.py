import os
import sys
import tempfile
import unittest
from pathlib import Path

from pandas import DataFrame

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from idmanifest import PathInventory


def write_file(path, text='value'):
  with open(path, 'w') as f:
    f.write(text)


def dataframe_reader(path):
  return DataFrame({'path': [path]})


class IDManifestTest(unittest.TestCase):

  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.root = self.tmp.name
    self.src = os.path.join(self.root, 'src')
    os.makedirs(self.src)

  def tearDown(self):
    self.tmp.cleanup()


  def make_paths_with_ids(self, filenames):
    tag1 = os.path.join(self.src, 'range_tag')
    os.makedirs(tag1)
    paths = []
    for filename in filenames:
      path = os.path.join(tag1, filename)
      write_file(path)
      paths.append(path)
    return paths

  def make_id_df(self):
    tag1 = os.path.join(self.src, 'tag1')
    tag2 = os.path.join(self.src, 'tag2')
    os.makedirs(tag1, exist_ok=True)
    os.makedirs(tag2, exist_ok=True)
    write_file(os.path.join(tag1, 'BASE_001_a.txt'))
    write_file(os.path.join(tag2, 'BASE_001_b.txt'))
    write_file(os.path.join(tag2, 'BASE_002_b.txt'))

    inventory = PathInventory({
      'tag1': os.path.join(tag1, '*.txt'),
      'tag2': os.path.join(tag2, '*.txt')
    }, r'BASE_[0-9]{3}', sort=True)
    return inventory.to_manifest()

  def test_read_does_not_require_registered_validations(self):
    id_df = self.make_id_df()

    id_df.add_reader('tag1', dataframe_reader)
    result = id_df.read('tag1', 'BASE_001')

    self.assertEqual(result.shape, (1, 1))

  def test_validations_can_return_single_column(self):
    id_df = self.make_id_df()
    id_df.add_validation('tag1', ncols=1)

    self.assertEqual(id_df.validations('tag1')['ncols'], 1)
    self.assertIsNone(id_df.validations('missing'))

  def test_replace_paths_updates_dataframe_paths(self):
    id_df = self.make_id_df()
    id_df.replace_paths({'tag1': '/new/root'})

    df = id_df.dataframe()
    tag1_path = df.loc[df['id'] == 'BASE_001', 'tag1'].iloc[0]
    tag2_path = df.loc[df['id'] == 'BASE_001', 'tag2'].iloc[0]
    self.assertEqual(tag1_path, '/new/root/tag1/BASE_001_a.txt')
    self.assertTrue(tag2_path.endswith('BASE_001_b.txt'))

  def test_read_all_supports_keep_data_argument(self):
    id_df = self.make_id_df()

    id_df.add_reader('tag1', dataframe_reader)
    id_df.read_all(columns=['tag1'], keep_data=False)

    self.assertEqual(id_df.loaded_data('tag1'), {})

  def test_custom_assertion_function_runs(self):
    id_df = self.make_id_df()
    df = DataFrame({'a': [1], 'b': [2]})

    def has_column(frame, name):
      return name in frame.columns

    id_df.validate_data(df, func=has_column, kwargs={'name': 'a'})
    with self.assertRaises(AssertionError):
      id_df.validate_data(df, func=has_column, kwargs={'name': 'missing'})

  def test_registered_custom_assertion_runs_when_reading_file(self):
    id_df = self.make_id_df()

    def has_path_column(frame):
      return 'path' in frame.columns

    id_df.add_reader('tag1', dataframe_reader)
    id_df.add_validation('tag1', func=has_path_column)

    result = id_df.read('tag1', 'BASE_001')

    self.assertEqual(result.shape, (1, 1))

  def test_save_helpers_write_manifest_log_and_object(self):
    id_df = self.make_id_df()

    id_df.add_reader('tag1', dataframe_reader)
    id_df.read_all(columns=['tag1'])

    df_path = os.path.join(self.root, 'paths.csv')
    log_path = os.path.join(self.root, 'log.csv')
    obj_path = os.path.join(self.root, 'paths.pkl')

    id_df.save(df_path, index=False)
    id_df.save_log(log_path, index=False)
    id_df.save_pickle(obj_path)

    self.assertTrue(os.path.isfile(df_path))
    self.assertTrue(os.path.isfile(log_path))
    loaded_df = id_df.load(df_path)
    loaded_log = id_df.load_log(log_path)
    loaded = id_df.load_pickle(obj_path)
    self.assertEqual(loaded_df.shape[0], id_df.shape()[0])
    self.assertEqual(loaded_log.shape[0], id_df.shape()[0])
    self.assertEqual(list(loaded.ids()), list(id_df.ids()))

  def test_read_all_logs_reader_and_validation_errors(self):
    id_df = self.make_id_df()

    def bad_reader(path):
      return DataFrame({'wrong': [1]})

    id_df.add_reader('tag1', bad_reader)
    id_df.add_validation('tag1', colnames=['path'])

    id_df.read_all(columns=['tag1'], stop_on_error=False)

    log_value = id_df.log().loc[id_df.log()['id'] == 'BASE_001', 'tag1'].iloc[0]
    self.assertIn('Not all columns match', log_value)

  def test_missing_and_extra_ids_report_expected_set_differences(self):
    id_df = self.make_id_df()

    self.assertEqual(id_df.missing_ids(['BASE_001', 'BASE_002', 'BASE_003']), ['BASE_003'])
    self.assertEqual(id_df.extra_ids(['BASE_001']), ['BASE_002'])

  def test_ensure_ids_adds_missing_rows_and_keeps_extras_by_default(self):
    id_df = self.make_id_df()

    df = id_df.ensure_ids(['BASE_001', 'BASE_003'])

    self.assertEqual(df['id'].to_list(), ['BASE_001', 'BASE_003', 'BASE_002'])
    self.assertTrue(df.loc[df['id'] == 'BASE_003', 'tag1'].isna().all())
    self.assertEqual(id_df.shape()[0], 3)

  def test_ensure_ids_can_drop_or_raise_on_extras(self):
    id_df = self.make_id_df()

    df = id_df.ensure_ids(['BASE_001', 'BASE_003'], extras='drop')

    self.assertEqual(df['id'].to_list(), ['BASE_001', 'BASE_003'])
    self.assertTrue(df.loc[df['id'] == 'BASE_003', 'tag2'].isna().all())

    id_df = self.make_id_df()
    with self.assertRaises(ValueError):
      id_df.ensure_ids(['BASE_001'], extras='raise')

  def test_id_range_helpers_are_inclusive_and_support_prefix_padding_suffix(self):
    paths = self.make_paths_with_ids(['BASE001_a.txt', 'BASE003_a.txt'])
    inventory = PathInventory({'tag1': paths}, r'(BASE[0-9]{3})', sort=True)
    id_df = inventory.to_manifest()

    self.assertEqual(id_df.missing_id_range(1, 3, prefix='BASE', width=3), ['BASE002'])
    df = id_df.ensure_id_range(1, 3, prefix='BASE', width=3)

    self.assertEqual(df['id'].to_list(), ['BASE001', 'BASE002', 'BASE003'])
    self.assertTrue(df.loc[df['id'] == 'BASE002', 'tag1'].isna().all())


if __name__ == '__main__':
  unittest.main()
