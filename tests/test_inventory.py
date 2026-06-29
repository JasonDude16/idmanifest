import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from idmanifest import CheckReport, IDManifest, PathInventory


def touch(path):
  with open(path, 'w') as f:
    f.write('')


class PathInventoryTest(unittest.TestCase):

  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.root = self.tmp.name

  def tearDown(self):
    self.tmp.cleanup()

  def make_paths(self, files_by_tag):
    paths = {}
    for tag, filenames in files_by_tag.items():
      tag_dir = os.path.join(self.root, tag)
      os.makedirs(tag_dir)
      for filename in filenames:
        touch(os.path.join(tag_dir, filename))
      paths[tag] = os.path.join(tag_dir, '*.txt')
    return paths

  def test_remove_matching_removes_matching_files(self):
    paths = self.make_paths({
      'tag1': ['BASE_001_keep.txt', 'BASE_002_drop.txt']
    })
    inventory = PathInventory(paths, r'BASE_[0-9]{3}', sort=True)

    removed_counts = inventory.remove_matching({'tag1': 'drop'})

    kept = [os.path.basename(x) for x in inventory.kept_files()['tag1']]
    removed = [os.path.basename(x) for x in inventory.removed_files()['tag1']]
    self.assertEqual(removed_counts['tag1'], 1)
    self.assertEqual(kept, ['BASE_001_keep.txt'])
    self.assertEqual(removed, ['BASE_002_drop.txt'])

  def test_new_inventory_api_reports_and_removes_failed_checks(self):
    shared = os.path.join(self.root, 'BASE_003_shared.txt')
    touch(shared)
    paths = self.make_paths({
      'tag1': ['BASE_001_ok.txt', 'BASE_002_dup_a.txt', 'BASE_002_dup_b.txt', 'bad_id.txt'],
      'tag2': ['BASE_001_other.txt']
    })
    paths['tag3'] = shared
    paths['tag4'] = shared

    inventory = PathInventory(paths, r'BASE_[0-9]{3}', sort=True)
    report = inventory.check()

    self.assertIsInstance(report, CheckReport)
    self.assertFalse(report.is_valid)
    self.assertEqual(report.counts()['invalid_ids'], 1)
    self.assertEqual(report.counts()['duplicate_ids'], 2)
    self.assertEqual(report.counts()['duplicate_files'], 2)
    self.assertEqual(set(report.details()['check']), {'invalid_ids', 'duplicate_ids', 'duplicate_files'})

    removed = inventory.remove_failed_checks(report)

    self.assertEqual(removed['tag1'], 3)
    self.assertEqual(removed['tag3'], 1)
    self.assertEqual(removed['tag4'], 1)

  def test_new_inventory_api_creates_manifest(self):
    paths = self.make_paths({
      'tag1': ['BASE_001_a.txt'],
      'tag2': ['BASE_001_b.txt', 'BASE_002_b.txt']
    })
    inventory = PathInventory(paths, r'BASE_[0-9]{3}', sort=True)

    manifest = inventory.to_manifest()

    self.assertIsInstance(manifest, IDManifest)
    self.assertEqual(list(manifest.ids()), ['BASE_001', 'BASE_002'])

  def test_duplicate_file_check_compares_all_tag_pairs(self):
    shared = os.path.join(self.root, 'BASE_001_shared.txt')
    touch(shared)

    paths = self.make_paths({
      'tag1': ['BASE_001_a.txt'],
      'tag2': ['BASE_002_b.txt'],
      'tag3': ['BASE_003_c.txt']
    })
    paths['tag1'] = shared
    paths['tag3'] = shared

    inventory = PathInventory(paths, r'BASE_[0-9]{3}', sort=True)

    results = inventory.check_duplicate_files()
    self.assertEqual(results['tag1'], [{'id': 'BASE_001', 'file': shared}])
    self.assertEqual(results['tag3'], [{'id': 'BASE_001', 'file': shared}])

  def test_id_regex_can_use_first_capture_group(self):
    paths = self.make_paths({
      'tag1': ['subject-001_alpha.txt']
    })

    inventory = PathInventory(paths, r'subject-([0-9]{3})', sort=True)
    manifest = inventory.to_manifest()

    self.assertEqual(list(manifest.ids()), ['001'])

  def test_id_regex_can_use_named_capture_group(self):
    paths = self.make_paths({
      'tag1': ['subject-001_alpha.txt']
    })

    inventory = PathInventory(paths, r'subject-(?P<id>[0-9]{3})', sort=True)
    manifest = inventory.to_manifest()

    self.assertEqual(list(manifest.ids()), ['001'])

  def test_duplicate_id_policy_extras_only_flags_later_files(self):
    paths = self.make_paths({
      'tag1': ['BASE_001_a.txt', 'BASE_001_b.txt', 'BASE_001_c.txt']
    })

    inventory = PathInventory(paths, r'BASE_[0-9]{3}', sort=True)
    results = inventory.check_duplicate_ids(policy='extras')
    duplicate_files = [os.path.basename(item['file']) for item in results['tag1']]

    self.assertEqual(duplicate_files, ['BASE_001_b.txt', 'BASE_001_c.txt'])

  def test_accepts_explicit_file_lists(self):
    tag_dir = os.path.join(self.root, 'tag1')
    os.makedirs(tag_dir)
    file_path = os.path.join(tag_dir, 'BASE_001_a.txt')
    touch(file_path)

    inventory = PathInventory({'tag1': [file_path]}, r'BASE_[0-9]{3}')

    self.assertEqual(inventory.kept_files()['tag1'], [file_path])

  def test_allow_empty_accepts_empty_sources(self):
    inventory = PathInventory({'tag1': []}, r'BASE_[0-9]{3}', allow_empty=True)

    self.assertEqual(inventory.kept_files()['tag1'], [])

  def test_accessors_do_not_expose_internal_lists(self):
    paths = self.make_paths({
      'tag1': ['BASE_001_a.txt']
    })
    inventory = PathInventory(paths, r'BASE_[0-9]{3}', sort=True)

    kept = inventory.kept_files()
    kept['tag1'].append('/not/a/real/file.txt')

    self.assertEqual(len(inventory.kept_files()['tag1']), 1)

  def test_remove_files_accepts_basenames(self):
    paths = self.make_paths({
      'tag1': ['BASE_001_keep.txt', 'BASE_002_drop.txt']
    })
    inventory = PathInventory(paths, r'BASE_[0-9]{3}', sort=True)

    removed_counts = inventory.remove_files({'tag1': ['BASE_002_drop.txt']})

    kept = [os.path.basename(x) for x in inventory.kept_files()['tag1']]
    removed = [os.path.basename(x) for x in inventory.removed_files()['tag1']]
    self.assertEqual(removed_counts['tag1'], 1)
    self.assertEqual(kept, ['BASE_001_keep.txt'])
    self.assertEqual(removed, ['BASE_002_drop.txt'])


if __name__ == '__main__':
  unittest.main()
