"""Synthetic source-form outputs only; never execute the numerical ELF."""
import copy
import json
import unittest

import output_parser as p


def sample(n=2304, mode='optimized', pair=None, own=0):
    gu, down = pair or [17, 17]; mixed = pair is not None
    tested = down if n == 2304 else gu
    paths = (2 if n == 256 else 4 if n == 2304 else 6) - int(tested in (16, 22))
    job = {'id': f'mixed-{gu}-{down}-{n}-{mode}' if mixed else f'pure-{n}-{mode}',
           'n': n, 'mode': mode, 'pair': pair}
    lines = ['DISPATCH type=17 one=%d multi=%d expected=%s' % (mode == 'optimized', mode == 'optimized', mode)]
    if mixed: lines.append('MIXED_DISPATCH gu=%d down=%d tested=%d selected_own=%d direct_rows1=%d' %
                           (gu, down, tested, own, tested in (17, 18)))
    for nt in ([1, 16] if mixed else range(1, 17)):
        for pad in (0, 32):
            for pat in range(6):
                for lo, hi in ((0, 7), (1, 6), (3, 3)):
                    lines.append('PASS gu=%d down=%d n=%d nt=%d pad=%d pattern=%d range=%d:%d paths=%d' %
                                 (gu, down, n, nt, pad, pat, lo, hi, paths))
    lines.append(json.dumps(dict(status='PASS', gu_type=gu, down_type=down, n=n,
        cases=72 if mixed else 576, paths_per_case=paths, mixed=mixed, expect=mode)))
    return job, ('\n'.join(lines) + '\n').encode()


class Parse(unittest.TestCase):
    def test_all_six_pure_jobs_and_complete_counts(self):
        for n in (256, 2304, 5120):
            for mode in ('optimized', 'fallback'):
                job, raw = sample(n, mode)
                result = p.parse(raw, b'', job)
                self.assertEqual(result['cases'], 576); self.assertTrue(result['passed'])

    def test_all_forty_actual_mixed_jobs_and_paths(self):
        total = 0
        for pair in p.PAIRS:
            for n in (2304, 5120):
                for mode in ('optimized', 'fallback'):
                    job, raw = sample(n, mode, list(pair))
                    result = p.parse(raw, b'', job); total += result['cases']
                    tested = pair[1] if n == 2304 else pair[0]
                    self.assertEqual(result['paths_per_case'], (4 if n == 2304 else 6) - int(tested in (16, 22)))
        self.assertEqual(total, 2880)

    def test_non17_selected_own_is_measured_not_assumed(self):
        for pair, n in (([22, 16], 5120), ([17, 18], 2304), ([16, 22], 5120)):
            for own in (0, 1):
                job, raw = sample(n, pair=pair, own=own)
                self.assertEqual(p.parse(raw, b'', job)['selected_own'], own)

    def test_type17_selected_own_cannot_bypass_native(self):
        job, raw = sample(pair=[17, 17], own=1)
        with self.assertRaisesRegex(ValueError, 'Type17'): p.parse(raw, b'', job)

    def test_missing_duplicate_or_reordered_case_refused(self):
        job, raw = sample(); lines = raw.decode().splitlines()
        for altered in (lines[:2] + lines[3:], lines[:2] + [lines[1]] + lines[2:],
                        lines[:1] + [lines[2], lines[1]] + lines[3:]):
            with self.assertRaisesRegex(ValueError, 'inventory'): p.parse(('\n'.join(altered)+'\n').encode(), b'', job)

    def test_missing_empty_range_tail_pad_or_nt16_refused(self):
        job, raw = sample(5120, pair=[22, 17])
        for field in ('range=3:3', 'pad=32', 'nt=16', 'range=1:6'):
            lines = [s for s in raw.decode().splitlines() if field not in s]
            with self.assertRaises(ValueError): p.parse(('\n'.join(lines)+'\n').encode(), b'', job)

    def test_wrong_dispatch_and_skipped_success_refused(self):
        job, raw = sample()
        for changed in (raw.replace(b'one=1', b'one=0', 1), raw.replace(b'multi=1', b'multi=0', 1),
                        raw.replace(b'DISPATCH', b'SKIPPED', 1)):
            with self.assertRaises(ValueError): p.parse(changed, b'', job)

    def test_wrong_mixed_tested_type_and_direct_path_refused(self):
        job, raw = sample(pair=[17, 18])
        for changed in (raw.replace(b'tested=18', b'tested=17'), raw.replace(b'direct_rows1=1', b'direct_rows1=0')):
            with self.assertRaisesRegex(ValueError, 'Mixed dispatch'): p.parse(changed, b'', job)

    def test_wrong_paths_cannot_hide_skipped_supported_path(self):
        job, raw = sample(5120)
        with self.assertRaisesRegex(ValueError, 'inventory'): p.parse(raw.replace(b'paths=6', b'paths=5'), b'', job)

    def test_final_json_strict_types_fields_and_values(self):
        job, raw = sample(); lines = raw.decode().splitlines(); final = json.loads(lines[-1])
        changes = [('cases', True), ('n', 2304.0), ('mixed', 0), ('status', 'SKIP'), ('cases', 575), ('expect', 'fallback')]
        for key, val in changes:
            value = dict(final, **{key: val})
            with self.assertRaisesRegex(ValueError, 'typed final'): p.parse(('\n'.join(lines[:-1]+[json.dumps(value)])+'\n').encode(), b'', job)
        for value in (dict(final, extra=1), {k:v for k,v in final.items() if k!='cases'}):
            with self.assertRaises(ValueError): p.parse(('\n'.join(lines[:-1]+[json.dumps(value)])+'\n').encode(), b'', job)

    def test_final_nonfinite_and_duplicate_key_refused(self):
        job, raw = sample(); lines = raw.decode().splitlines()
        for tail in ('{"status":"PASS","status":"PASS"}', '{"n":NaN}', '{"n":Infinity}'):
            with self.assertRaises(ValueError): p.parse(('\n'.join(lines[:-1]+[tail])+'\n').encode(), b'', job)

    def test_stderr_first_fault_refused(self):
        job, raw = sample()
        with self.assertRaisesRegex(ValueError, 'empty stderr'): p.parse(raw, b'IQ2_XS_FIRST_FAULT: mismatch\n', job)

    def test_output_bound_and_partial_or_extra_output_refused(self):
        job, raw = sample()
        for changed in (raw[:-1], raw+b'\n', raw+b'PASS\n', raw.replace(b'\n', b'\r\n'), b'x'*(p.MAX_BYTES+1)):
            with self.assertRaises(ValueError): p.parse(changed, b'', job)

    def test_wrong_job_scope_and_bool_types_refused(self):
        job, raw = sample()
        for value in (dict(job,n=True), dict(job,pair=[True,17]), dict(job,id='foreign'),
                      dict(job,pair=[21,17]), dict(job,extra=1)):
            with self.assertRaises(ValueError): p.parse(raw, b'', value)
        job, raw = sample(256,pair=[17,17])
        with self.assertRaises(ValueError): p.parse(raw,b'',job)
