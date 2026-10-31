"""CPU-only guard controls; no model, service or network operation."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import cpu_guard as g


def observations():
    return ({'status': 'ok', 'service': 'strata', 'model': 'deepseek-v4.1-flash-iq2-xs',
             'loaded': True, 'images': True, 'max_context': 1048576, 'busy': False,
             'switcher': {'active_model': 'deepseek', 'default_model': 'deepseek',
                          'fault': None, 'inflight': 0, 'waiting': 0}},
            {'work': {'active': 0, 'queued': 0, 'admission_reserved': 0}})


class Health(unittest.TestCase):
    def test_idle_and_healthy_busy_CPU_only_positives(self):
        h, t = observations()
        self.assertFalse(g.health_contract(h, t)['busy'])
        h['busy'] = True; h['switcher'].update(inflight=2, waiting=3)
        t['work'].update(active=2, queued=3, admission_reserved=1)
        value = g.health_contract(h, t)
        self.assertTrue(value['ordinary_hosted_work_allowed_for_CPU_only'])
        self.assertEqual(value['work'], t['work'])

    def test_every_model_health_capacity_predicate_fails_closed(self):
        for key, values in {'status': ['error', None], 'service': ['foreign', None],
                'model': ['other', None], 'loaded': [False, 1, None],
                'images': [False, 1, None], 'max_context': [262144, True, '1048576', None],
                'busy': [0, 1, 'false', None]}.items():
            for value in values:
                h, t = observations(); h[key] = value
                with self.assertRaises(ValueError): g.health_contract(h, t)

    def test_default_active_and_fault_are_not_work_exceptions(self):
        for key, value in [('active_model', 'qwen'), ('default_model', 'qwen'), ('fault', 'fault')]:
            h, t = observations(); h['switcher'][key] = value
            with self.assertRaises(ValueError): g.health_contract(h, t)
        h, t = observations(); del h['switcher']['fault']
        with self.assertRaises(ValueError): g.health_contract(h, t)

    def test_all_counters_reject_missing_negative_bool_and_unknown_types(self):
        for which, names in [('switcher', ['inflight', 'waiting']),
                             ('work', ['active', 'queued', 'admission_reserved'])]:
            for name in names:
                for val in [-1, True, 1.0, '0', None]:
                    h, t = observations(); (h['switcher'] if which == 'switcher' else t['work'])[name] = val
                    with self.assertRaises(ValueError): g.health_contract(h, t)

    def test_missing_or_malformed_observations_refuse(self):
        h, t = observations()
        for a, b in [(None, t), (h, None), ({}, t), (dict(h, switcher=[]), t), (h, {}), (h, {'work': []})]:
            with self.assertRaises(ValueError): g.health_contract(a, b)


class Guard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'STATE.json'
        self.state = {'active_cpu_build': False, 'phase': None, 'selected': {'pid': 123}}
        self.path.write_text(json.dumps(self.state))
        self.runtime = Mock(PHASE_KEYS=('active_cpu_build', 'phase'))
        self.runtime.current_binding.side_effect = lambda s: s['selected']
        self.host = Mock(); h, t = observations()
        self.host.get.side_effect = lambda path: copy.deepcopy(h if path == '/health' else t)
        self.binding = {'pid': 123}
        self.space = patch.object(g.shutil, 'disk_usage', return_value=Mock(free=140 * 2**30))
        self.space.start(); self.addCleanup(self.space.stop)

    def call(self, reservation=None): return g.guard(self.runtime, self.host, self.binding, self.path, reservation)

    def test_positive_checks_binding_without_idle_or_service_actions(self):
        self.assertEqual(self.call(), self.state)
        self.host.guard_binding.assert_called_once(); self.host.idle.assert_not_called()
        self.host.stop_ds.assert_not_called(); self.host.restore_ds.assert_not_called()

    def test_complete_guard_accepts_healthy_busy_work_with_same_owner(self):
        health, telemetry = observations(); health['busy'] = True
        health['switcher'].update(inflight=1, waiting=1)
        telemetry['work'].update(active=1, queued=1, admission_reserved=1)
        self.host.get.side_effect = lambda path: health if path == '/health' else telemetry
        self.assertEqual(self.call(), self.state)
        self.host.guard_binding.assert_called_once(); self.host.idle.assert_not_called()

    def test_private_build_restoration_or_changed_owner_refuses_before_health(self):
        for key in ['active_cpu_build', 'phase']:
            state = dict(self.state, **{key: {'foreign': True}}); self.path.write_text(json.dumps(state))
            with self.assertRaises(ValueError): self.call()
        self.path.write_text(json.dumps(dict(self.state, selected={})))
        with self.assertRaisesRegex(ValueError, 'owner'): self.call()
        self.host.get.assert_not_called()

    def test_only_exact_own_reservation_is_allowed(self):
        record = {'owner': 'own'}; self.path.write_text(json.dumps(dict(self.state, active_cpu_build=record)))
        self.assertEqual(self.call(record)['active_cpu_build'], record)
        with self.assertRaisesRegex(ValueError, 'reservation'): self.call({'owner': 'other'})

    def test_binding_fault_and_low_root_are_not_suppressed(self):
        self.host.guard_binding.side_effect = ValueError('native identity')
        with self.assertRaisesRegex(ValueError, 'native identity'): self.call()
        self.host.guard_binding.side_effect = None
        with patch.object(g.shutil, 'disk_usage', return_value=Mock(free=131 * 2**30)):
            with self.assertRaisesRegex(ValueError, 'Root132'): self.call()

    def test_coordination_change_during_health_refuses(self):
        original = self.host.get.side_effect
        def get(path):
            self.path.write_text(json.dumps(dict(self.state, phase='foreign')))
            return original(path)
        self.host.get.side_effect = get
        with self.assertRaisesRegex(ValueError, 'Coordination changed'): self.call()

    def test_health_transport_fault_is_not_caught(self):
        self.host.get.side_effect = OSError('transport fault')
        with self.assertRaisesRegex(OSError, 'transport fault'): self.call()
