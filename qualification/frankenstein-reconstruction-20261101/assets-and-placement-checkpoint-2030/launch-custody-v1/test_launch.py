import json
from pathlib import Path
import sys
import tempfile
import unittest
import launch as l


class Launch(unittest.TestCase):
    def test_actual_child_stdout_stderr_pid_and_exit0_persisted(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve()/'capture'
            self.assertEqual(l.capture([sys.executable,'-I','-B','-c',"import sys;print('OUT');print('ERR',file=sys.stderr)"],root),0)
            start=json.loads((root/'controller-start.json').read_text());end=json.loads((root/'controller-exit.json').read_text())
            self.assertEqual(start['pid'],end['pid']);self.assertEqual(end['returncode'],0);self.assertTrue(end['actual_wait_observed'])
            self.assertEqual((root/'stdout.log').read_text(),'OUT\n');self.assertEqual((root/'stderr.log').read_text(),'ERR\n')
            self.assertEqual(end['target_signals_sent'],0);self.assertFalse(end['retry'])

    def test_actual_nonzero_preserved_without_retry_or_regrade(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve()/'failed'
            self.assertEqual(l.capture([sys.executable,'-I','-B','-c','raise SystemExit(7)'],root),7)
            end=json.loads((root/'controller-exit.json').read_text());self.assertEqual(end['returncode'],7)
            self.assertIsNone(end['error']);self.assertEqual(end['target_signals_sent'],0)

    def test_missing_executable_is_explicit_unobserved_no_pid_claim_or_replay(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve()/'missing'
            with self.assertRaises(FileNotFoundError):l.capture(['/does/not/exist'],root)
            end=json.loads((root/'controller-exit.json').read_text());self.assertIsNone(end['pid'])
            self.assertIsNone(end['returncode']);self.assertFalse(end['actual_wait_observed'])
            with self.assertRaises(ValueError):l.capture([sys.executable],root)


if __name__=='__main__':unittest.main(verbosity=2)
