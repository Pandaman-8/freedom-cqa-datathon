"""Negative probes for the release scanner. All values below are generated fake markers."""
from pathlib import Path
import runpy
import unittest

scanner = runpy.run_path(str(Path(__file__).resolve().parents[4] / 'scripts/check-public-safety.py'))
findings, private_path = scanner['findings'], scanner['private_path']


class PublicSafetyTest(unittest.TestCase):
    def test_credential_markers_are_detected_without_printing_values(self):
        for prefix in ('gh' + 'p_', 'g' + 'sk_', 'github_' + 'pat_'):
            self.assertIn('credential-pattern', findings((prefix + 'x' * 45).encode()))

    def test_signed_external_url_and_userinfo(self):
        external = 'https://' + 'example.com/'
        self.assertIn('signed-or-keyed-url', findings((external + '?sig=synthetic-negative-marker').encode()))
        self.assertIn('url-userinfo', findings(('https://' + 'test:fake@example.com/').encode()))
        self.assertEqual([], findings(b'https://example.invalid/?sig=synthetic-fixture'))

    def test_private_files_and_explicit_example_exception(self):
        for name in ['ml-service/.env', 'data/official/guide.pdf', 'invoke.json', 'run.sqlite', 'run.sqlite-wal', 'recordings/call.wav',
                     'private/session.ml-approval.json', 'private/selected.approval-selection.json', 'private/hash.dataset-source.json']:
            self.assertTrue(private_path(name), name)
        for name in ['ml-service/.env.example', 'data/.gitkeep', 'examples/synthetic_dataset.json']:
            self.assertFalse(private_path(name), name)

    def test_renamed_private_binary_format(self):
        for raw in (b'%PDF-' + b'1.7\n', b'SQLite format 3\0' + b'fake'):
            self.assertIn('private-binary-format', findings(raw))


if __name__ == '__main__':
    unittest.main()
