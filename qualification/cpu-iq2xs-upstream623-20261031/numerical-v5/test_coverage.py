"""Saved synthetic-result custody controls. Never execute a numerical fixture."""
from contextlib import ExitStack
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import coverage as c
import output_parser as parser
import runner as r

b = r.load_build()


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


class Prior(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.prior = Path(self.tmp.name).resolve() / 'numerical-v4'; self.prior.mkdir()
        original = r.N / 'numerical-v4'
        review = json.loads((original / 'PARTIAL_ROOT_REVIEW.json').read_text())
        names = [*review['raw_sha256'], 'qualification.json', 'PARTIAL_ROOT_REVIEW.json', 'PARTIAL_ASTRA_REVIEW.json']
        self.names = names
        for relative in names:
            src = original / relative; dest = self.prior / relative
            dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, dest)
        old = json.loads((self.prior / 'qualification.json').read_text())
        self.q = copy.deepcopy(old); self.q['jobs'] = r.jobs()
        self.q['files'].update({str(c.REMOTE / 'numerical-v4' / name): digest(self.prior / name) for name in names})
        self.stack = ExitStack(); self.addCleanup(self.stack.close)

    def call(self): return c.check(b, self.q, parser, self.prior, r.full_jobs())

    def refresh_synthetic_custody(self):
        """Permit a unit mutation to reach deep checks; real review pins remain hardcoded."""
        for name, constant in [('PARTIAL_ROOT_REVIEW.json', 'ROOT_REVIEW'),
                               ('PARTIAL_ASTRA_REVIEW.json', 'ASTRA_REVIEW')]:
            path = self.prior / name; review = json.loads(path.read_text())
            review['raw_sha256'] = {rel: digest(self.prior / rel) for rel in review['raw_sha256']}
            path.write_text(json.dumps(review))
            self.stack.enter_context(patch.object(c, constant, digest(path)))
        self.q['files'].update({str(c.REMOTE / 'numerical-v4' / name): digest(self.prior / name) for name in self.names})

    def edit(self, relative, mutate):
        path = self.prior / relative; value = json.loads(path.read_text()); mutate(value)
        path.write_text(json.dumps(value)); self.refresh_synthetic_custody()

    def test_saved_accepted_25_compose_only_with_exact_remaining_21(self):
        value = self.call()
        self.assertEqual((value['prior_accepted_jobs'], value['prior_case_rows']), (25, 4824))
        self.assertEqual((value['new_required_jobs'], value['new_required_case_rows']), (21, 1512))
        self.assertFalse(value['old_v4_complete']); self.assertFalse(value['old_unaccepted_child_regraded'])

    def test_passed_prefix_is_not_in_new_command_whitelist(self):
        self.assertEqual(r.jobs(), r.full_jobs()[25:])
        for job in r.full_jobs()[:25]:
            with self.assertRaises(ValueError): r.command(job)

    def test_suffix_overlap_missing_duplicate_or_bool_refuses(self):
        for jobs in [r.full_jobs()[24:], r.jobs()[:-1], r.jobs() + [r.jobs()[0]],
                     [dict(r.jobs()[0], n=True), *r.jobs()[1:]]]:
            self.q['jobs'] = jobs
            with self.assertRaisesRegex(ValueError, 'suffix'): self.call()

    def test_prior_qualification_membership_omission_refuses(self):
        old = json.loads((self.prior / 'qualification.json').read_text())
        key = next(k for k in old['files'] if 'numerical-v4' not in k)
        self.q['files'].pop(key)
        with self.assertRaisesRegex(ValueError, 'qualification file omitted'): self.call()

    def test_changed_fixture_parser_CPU_or_native_identity_refuses(self):
        for key in ['fixture_sha256', 'CPU_capability_receipt_sha256', 'selected_native_sha256']:
            old = self.q[key]; self.q[key] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'arithmetic identity'): self.call()
            self.q[key] = old
        self.q['source_sha256']['output_parser.py'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'arithmetic identity'): self.call()

    def test_missing_changed_or_escaping_reviewed_raw_refuses(self):
        relative = next(iter(json.loads((self.prior / 'PARTIAL_ROOT_REVIEW.json').read_text())['raw_sha256']))
        key = str(c.REMOTE / 'numerical-v4' / relative); self.q['files'].pop(key)
        with self.assertRaisesRegex(ValueError, 'membership'): self.call()

    def test_ordinary_busy_deferral_cannot_hide_fault_or_uncertain_cleanup(self):
        for key, value in [('status', 'HOLD'), ('error', 'actual arithmetic fault'),
                           ('error_notes', ['cleanup fault']), ('own_claim_released', False)]:
            path = 'numerical-supervision-FIRST/result.json'
            original = (self.prior / path).read_bytes()
            self.edit(path, lambda row: row.update({key: value}))
            with self.assertRaisesRegex(ValueError, 'busy deferral'): self.call()
            (self.prior / path).write_bytes(original); self.refresh_synthetic_custody()

    def test_prefix_missing_duplicate_or_reordered_rows_refuses(self):
        path = 'numerical-FIRST/partial.json'
        for change in [lambda d: d['completed'].pop(),
                       lambda d: d['completed'].__setitem__(1, d['completed'][0]),
                       lambda d: d['completed'].reverse()]:
            original = (self.prior / path).read_bytes(); self.edit(path, change)
            with self.assertRaisesRegex(ValueError, 'accepted prefix'): self.call()
            (self.prior / path).write_bytes(original); self.refresh_synthetic_custody()

    def test_prior_attempted_inventory_or_returncode_change_refuses(self):
        self.edit('numerical-supervision-FIRST/result.json',
                  lambda d: d['owned_groups_absence']['children'][0].update(returncode=1))
        with self.assertRaisesRegex(ValueError, 'attempted child inventory'): self.call()

    def test_accepted_child_digest_or_result_change_refuses(self):
        job = r.full_jobs()[0]['id']; path = self.prior / 'numerical-FIRST' / job / 'stdout'
        path.write_bytes(path.read_bytes().replace(b'PASS gu=', b'FAIL gu=', 1))
        self.refresh_synthetic_custody()
        with self.assertRaisesRegex(ValueError, 'output digest'): self.call()

    def test_old_unaccepted_child_is_never_silently_promoted(self):
        job = r.full_jobs()[25]['id']
        self.edit('numerical-FIRST/' + job + '/child.json', lambda d: d.update(status='PASS'))
        with self.assertRaisesRegex(ValueError, 'was regraded'): self.call()

    def test_unknown_prior_artifact_is_not_read_outside_namespace(self):
        path = self.prior / 'PARTIAL_ROOT_REVIEW.json'; value = json.loads(path.read_text())
        value['raw_sha256']['../foreign'] = '0' * 64; path.write_text(json.dumps(value))
        self.stack.enter_context(patch.object(c, 'ROOT_REVIEW', digest(path)))
        self.q['files'][str(c.REMOTE / 'numerical-v4/PARTIAL_ROOT_REVIEW.json')] = digest(path)
        with self.assertRaisesRegex(ValueError, 'Foreign prior'): self.call()

    def test_child_identity_resources_environment_and_argv_are_not_just_hashes(self):
        job = r.full_jobs()[0]['id']; base = 'numerical-FIRST/' + job + '/'
        changes = [('child.json', 'child_sha256', 'argv', ['foreign']),
                   ('child.json', 'child_sha256', 'cleanup', ['uncertain']),
                   ('observed.json', 'observed_sha256', 'pid', 1),
                   ('observed.json', 'observed_sha256', 'cpu', [31, 31]),
                   ('observed.json', 'observed_sha256', 'environment', {}),
                   ('dispatch-environment.json', 'dispatch_sha256', 'dispatch', {})]
        partial = self.prior / 'numerical-FIRST/partial.json'
        for name, field, key, value in changes:
            path = self.prior / base / name; saved = path.read_bytes(); saved_partial = partial.read_bytes()
            row = json.loads(path.read_text()); row[key] = value; path.write_text(json.dumps(row))
            data = json.loads(partial.read_text()); data['completed'][0][field] = digest(path)
            partial.write_text(json.dumps(data)); self.refresh_synthetic_custody()
            with self.assertRaises(ValueError): self.call()
            path.write_bytes(saved); partial.write_bytes(saved_partial); self.refresh_synthetic_custody()

