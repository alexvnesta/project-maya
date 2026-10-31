import copy
import json
from pathlib import Path
import unittest
import engine_profile as p


class Profile(unittest.TestCase):
    def base(self):
        return json.loads((Path(__file__).parent / 'profile-base-config.json').read_text())

    def directory(self, v='TP1'):
        return p.E / ('results/maya145-decode-mayas-' + v + '-20261031T150000Z/native')

    def log(self, variant='TP1'):
        q = " Q8 batch check: 8 jobs (k 32 .. 5120, rows 1 .. 16, strided, one input read with two k, two jobs sharing a rounding): 50976 int8 and 1593 scales the per-job launches' bit for bit, every guard intact (DS4_Q8_CHECK)"
        s = ''.join('ds4: CUDA%d%s\n' % (d, q) for d in (0, 1))
        s += ''.join('abliteration check: device %d rows 2 dim 5120 target blocks 40 drafter untouched max_abs 1e-7 PASS\n' % d for d in (0, 1))
        for d in (0, 1):
            if variant == 'TP1':
                prefix = 'ds4: CUDA%d layers [%d, %d]%s' % (d, 0 if d == 0 else 19, 42 if d == 0 else 39, ' + head' if d else '')
            else:
                prefix = 'ds4: CUDA%d layers [0, %d] (tensor parallel 2, part %d)%s' % (d, 42 if d == 0 else 39, d, ' + head' if d else '')
            s += prefix + ': weights 3.31 GB, experts 58.32 GB (5746 of 15744 in VRAM), caches 0.58 GB, 2026 MiB free\n'
        if variant == 'TP2':
            s += "ds4: TP check passed (2 expert formats and rotations, all the split layers have) (DS4_TP_CHECK)\n"
            s += "ds4: DS4_AR2=1: the prompt chunks' all-reduces on CUDA0, CUDA1 pipelined (8 blocks, 8 KB pieces), the other member's rows read 16 bytes a lane; the sums bit for bit\n"
        return s

    def test_tp1_keeps_policy_and_base_unchanged(self):
        base = self.base(); before = copy.deepcopy(base); c = p.profile(base, self.directory(), 'TP1')
        self.assertEqual(base, before)
        for option in ('--max-context', '--dspark', '--cpu-threads', '--mmap-experts', '--prefill-chunk'):
            i = base['args'].index(option); j = c['args'].index(option)
            self.assertEqual(base['args'][i+1], c['args'][j+1])
        self.assertEqual(c['hosted_default_effort'], 100)
        self.assertEqual(c['env']['DS4_YOCO'], '1')
        self.assertEqual(c['env']['DS4_Q8_CHECK'], '1')
        self.assertEqual(c['exe'], str(p.NATIVE)); self.assertEqual(c['tokenizer'], str(p.PACK / 'tokenizer'))

    def test_tp2_explicit_uneven_blocks_and_real_checks(self):
        c = p.profile(self.base(), self.directory('TP2'), 'TP2')
        self.assertEqual(c['args'][c['args'].index('--tp')+1], '2')
        self.assertEqual(c['env']['DS4_TP_GGUF_UNEVEN'], '1')
        self.assertEqual(c['env']['DS4_TP_CHECK'], '1')
        self.assertEqual(c['env']['DS4_AR2'], '1')
        self.assertNotIn('DS4_DRAFT_VRAM', c['env'])
        self.assertNotIn('DS4_FLOW_TP', c['env'])

    def test_no_old_cache_crossload(self):
        c = p.profile(self.base(), self.directory(), 'TP1')
        for key in ('STRATA_DS4_SLOT_DIR', 'DS4_LANE_CAL', 'DS4_LT_STORE'):
            self.assertTrue(c['env'][key].startswith(str(self.directory()) + '/'))

    def test_modified_model_quality_context_base_refused(self):
        for key, value in (('hosted_default_effort', 50), ('tokenizer', '/other')):
            base = self.base(); base[key] = value
            with self.assertRaises(ValueError): p.profile(base, self.directory(), 'TP1')
        base = self.base(); base['args'][base['args'].index('--max-context')+1] = '262144'
        with self.assertRaises(ValueError): p.profile(base, self.directory(), 'TP1')

    def test_wrong_variant_namespace_refused(self):
        for v in ('TP3', 'tp2', '', None):
            with self.assertRaises(ValueError): p.factor(v)
        with self.assertRaises(ValueError): p.profile(self.base(), self.directory('TP2'), 'TP1')

    def test_old_namespace_refused(self):
        with self.assertRaises(ValueError): p.profile(self.base(), p.E / 'results/maya-s-prose-v2-B1-20261031T150000Z/native', 'TP1')

    def test_new_tp1_startup(self):
        r = p.startup(self.log(), 'TP1')
        self.assertTrue(r['passed']); self.assertFalse(r['model_quality_or_speed_proof'])

    def test_new_tp2_startup(self):
        r = p.startup(self.log('TP2'), 'TP2')
        self.assertTrue(r['passed']); self.assertEqual([x['tp'] for x in r['placement']], [2, 2])

    def test_old_q8_footer_refused(self):
        with self.assertRaises(ValueError): p.startup(self.log().replace('50976 int8 and 1593', '42784 int8 and 1337'), 'TP1')

    def test_duplicate_or_missing_device_check_refused(self):
        line = self.log().splitlines()[0]
        for text in (self.log() + line + '\n', self.log().replace(line + '\n', '')):
            with self.assertRaises(ValueError): p.startup(text, 'TP1')

    def test_projection_drafter_dim_or_finite_failure_refused(self):
        for old, new in (('target blocks 40', 'target blocks 43'), ('dim 5120', 'dim 4096'),
                         ('max_abs 1e-7', 'max_abs 1e999'), ('max_abs 1e-7', 'max_abs -1')):
            with self.assertRaises(ValueError): p.startup(self.log().replace(old, new), 'TP1')

    def test_real_tp_fallback_refused(self):
        with self.assertRaises(ValueError): p.startup(self.log(), 'TP2')

    def test_tp2_missing_arithmetic_check_refused(self):
        with self.assertRaises(ValueError): p.startup(self.log('TP2').replace('ds4: TP check passed (', 'ds4: TP not checked ('), 'TP2')

    def test_tp2_fp16_wire_or_disabled_reduce_refused(self):
        for value in ('2', '0'):
            with self.assertRaises(ValueError): p.startup(self.log('TP2').replace('DS4_AR2=1:', 'DS4_AR2=' + value + ':'), 'TP2')

    def test_identical_snapshots_recorded_without_extra_owners(self):
        for variant in ('TP1','TP2'):
            log=self.log(variant);rows=[l for l in log.splitlines() if 'layers [' in l]
            value=p.startup(log+'\n'.join(rows)+'\n',variant)
            self.assertEqual(len(value['placement']),2);self.assertEqual(value['identical_placement_repeat_rows'],2)
    def test_conflicting_same_device_snapshots_refused(self):
        for variant in ('TP1','TP2'):
            log=self.log(variant);row=next(l for l in log.splitlines() if 'layers [' in l)
            with self.assertRaises(ValueError):p.startup(log+row.replace('5746 of','5745 of')+'\n',variant)

    def test_third_gpu_check_or_placement_refused(self):
        for row in (self.log().splitlines()[0], next(l for l in self.log().splitlines() if 'layers [' in l)):
            with self.assertRaises(ValueError): p.startup(self.log() + row.replace('CUDA0', 'CUDA2') + '\n', 'TP1')

    def test_bad_expert_count_refused(self):
        with self.assertRaises(ValueError): p.startup(self.log().replace('(5746 of 15744', '(15745 of 15744'), 'TP1')

    def test_unknown_or_partial_trunk_refused(self):
        with self.assertRaises(ValueError): p.startup(self.log('TP2').replace('layers [0, 39]', 'layers [19, 39]'), 'TP2')

    def test_stale_native_cannot_enter_new_profile(self):
        value = p.profile(self.base(), self.directory(), 'TP1')
        self.assertTrue(p.check_profile(self.base(), value, self.directory(), 'TP1'))
        for exe in (str(p.P/'native-build-FIRST/maya-ds4'), '/home/alex/deepseek-hosted-20261025/bin/maya-ds4'):
            bad = copy.deepcopy(value); bad['exe'] = exe
            with self.assertRaises(ValueError): p.check_profile(self.base(), bad, self.directory(), 'TP1')

    def test_quality_capacity_output_reductions_refused(self):
        for key, new in (('hosted_default_effort',50),('max_tokens',32768)):
            value=p.profile(self.base(),self.directory(),'TP1'); value[key]=new
            with self.assertRaises(ValueError):p.check_profile(self.base(),value,self.directory(),'TP1')
        value=p.profile(self.base(),self.directory(),'TP1');value['args'][value['args'].index('--dspark')+1]='off'
        with self.assertRaises(ValueError):p.check_profile(self.base(),value,self.directory(),'TP1')


class TimedProfile(unittest.TestCase):
    def test_diagnostic_dump_and_round_logger_absent(self):
        base=json.loads((Path(__file__).parent/'profile-base-config.json').read_text())
        value=p.profile(base,p.E/'results/maya145-decode-mayas-TP2-20261031T150000Z/native','TP2')
        self.assertNotIn('DS4_SERVE_DUMP',value['env']);self.assertNotIn('DS4_ROUND_LOG',value['env'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
