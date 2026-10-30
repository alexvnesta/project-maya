"""Small negative controls for the new bounded CPU proof driver."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import tempfile

import qualify_cpu as c


class Policy(unittest.TestCase):
    def test_exact_order_and_summary_required(self):
        c.policy_output('PASS one\nPASS two\nALL 2 Q8_SHARE policy checks passed\n', ['one', 'two'])
    def test_duplicate_id_rejected(self):
        with self.assertRaises(ValueError): c.policy_output('PASS one\nPASS one\nALL 2 Q8_SHARE policy checks passed', ['one', 'two'])
    def test_wrong_order_rejected(self):
        with self.assertRaises(ValueError): c.policy_output('PASS two\nPASS one\nALL 2 Q8_SHARE policy checks passed', ['one', 'two'])
    def test_missing_summary_rejected(self):
        with self.assertRaises(ValueError): c.policy_output('PASS one', ['one'])
    def test_extra_trailing_output_rejected(self):
        with self.assertRaises(ValueError): c.policy_output('PASS one\nALL 1 Q8_SHARE policy checks passed\nextra', ['one'])
    def test_wrong_summary_count_rejected(self):
        with self.assertRaises(ValueError): c.policy_output('PASS one\nALL 2 Q8_SHARE policy checks passed', ['one'])


class Source(unittest.TestCase):
    def test_source_path_escape_rejected_before_read(self):
        with patch.object(c, 'sha') as sha, self.assertRaises(ValueError):
            c.pins({'source_sha256': {'../outside': 'pin'}, 'source_input_sha256': {}})
        sha.assert_not_called()
    def test_absolute_input_rejected_before_read(self):
        with patch.object(c, 'sha') as sha, self.assertRaises(ValueError):
            c.pins({'source_sha256': {}, 'source_input_sha256': {'/foreign': 'pin'}})
        sha.assert_not_called()
    def test_changed_source_rejected(self):
        with patch.object(c, 'sha', return_value='changed'), self.assertRaises(ValueError):
            c.pins({'source_sha256': {'build.py': 'pin'}, 'source_input_sha256': {}})
    def test_linux_limits_are_child_scoped(self):
        with patch.object(c.sys, 'platform', 'linux'), patch.object(c.resource, 'setrlimit') as limit, patch.object(c.os, 'nice') as nice:
            c.limits()
        self.assertEqual(limit.call_args_list[0].args, (c.resource.RLIMIT_CPU, (30,30)))
        self.assertEqual(limit.call_args_list[1].args, (c.resource.RLIMIT_AS, (512*2**20,512*2**20)))
        nice.assert_called_once_with(15)
    def test_mac_avoids_linux_address_space_limit(self):
        with patch.object(c.sys, 'platform', 'darwin'), patch.object(c.resource, 'setrlimit') as limit, patch.object(c.os, 'nice'):
            c.limits()
        self.assertEqual(limit.call_count, 1)
    def test_cleanup_returns_after_group_disappears(self):
        p = Mock(); p.pid = 123
        with patch.object(c.os, 'killpg', side_effect=[None, ProcessLookupError]):
            self.assertEqual(c.cleanup(p), [])
        p.wait.assert_called_once_with(timeout=3)


if __name__ == '__main__': unittest.main()
