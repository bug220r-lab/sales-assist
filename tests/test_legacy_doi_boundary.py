"""Independent synthetic-only regressions. Numeric 90000001 is fabricated."""
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import patch

from synthetic_sales_assist.domain.normalization import normalize_order_number
from synthetic_sales_assist.doi.source import normalize_synthetic_order_number, DOISourceError
from synthetic_sales_assist.doi.demo import DOI_DEMOS, DOI_APPLICATION_FIXTURES, execute_doi_demo


class LegacyBoundaryTests(unittest.TestCase):
    def test_neutral_normalization_preserves_guard_separation(self):
        self.assertEqual(normalize_order_number(' \t00090000001\r\n'), '90000001')
        with self.assertRaises(DOISourceError):
            normalize_synthetic_order_number('90000001')
        self.assertEqual(normalize_synthetic_order_number('SYN-ORDER-0001').value, 'SYN-ORDER-1')

    def test_all_nine_pure_fixture_definitions_reconcile_and_repeat(self):
        definitions = (*DOI_DEMOS, *DOI_APPLICATION_FIXTURES)
        self.assertEqual(len(definitions), 9)
        for definition in definitions:
            with self.subTest(fictional_fixture_alias=definition.alias):
                first = execute_doi_demo(definition.alias)
                second = execute_doi_demo(definition.alias)
                self.assertEqual(first.evaluation, second.evaluation)
                self.assertTrue(first.snapshot.order_id.value.value.startswith('SYN-ORDER-'))
                self.assertEqual(first.definition, definition)


class VerificationRunnerTests(unittest.TestCase):
    @staticmethod
    def runner():
        path = Path(__file__).resolve().parents[1] / 'tools' / 'run_doi_staging_checks.py'
        spec = importlib.util.spec_from_file_location('_doi_guard_contract', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_runner_loads_only_two_explicit_files_without_discovery(self):
        runner = self.runner()
        self.assertEqual(runner.INTENDED_TEST_FILES,
                         ('test_csv_staging_independent.py', 'test_legacy_doi_boundary.py'))
        root = Path('SYN-ROOT')
        with patch.object(runner, 'load_test_module', return_value=object()) as load, \
             patch.object(unittest.defaultTestLoader, 'loadTestsFromModule',
                          return_value=unittest.TestSuite()), \
             patch.object(unittest.defaultTestLoader, 'discover',
                          side_effect=AssertionError('UNINTENDED_DISCOVERY')):
            runner.load_intended_suite(root)
        self.assertEqual([call.args[0] for call in load.call_args_list],
                         [root / 'tests' / name for name in runner.INTENDED_TEST_FILES])

    def test_runner_guard_rejects_audited_mutations_without_performing_them(self):
        runner = self.runner()
        blocked = []
        guard = runner.make_audit_guard(blocked)
        events = ('os.remove', 'os.rename', 'os.rmdir', 'os.mkdir', 'os.truncate',
                  'os.link', 'os.symlink', 'os.chmod', 'os.chown', 'os.utime',
                  'os.setxattr', 'os.removexattr', 'shutil.copyfile', 'shutil.rmtree',
                  'socket.connect', 'sqlite3.connect', 'subprocess.Popen')
        for event in events:
            with self.subTest(audited_event=event), self.assertRaises(RuntimeError):
                guard(event, ('SYN-FILE',))
        self.assertEqual(blocked, list(events))
        with self.assertRaises(RuntimeError):
            guard('open', ('SYN-FILE', 'wb', 0))
        guard('open', ('SYN-FILE', 'rb', 0))


if __name__ == '__main__':
    unittest.main()
