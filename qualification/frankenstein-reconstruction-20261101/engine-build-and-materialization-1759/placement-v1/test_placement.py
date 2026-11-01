"""Focused new placement policy, actual-map, ownership and refusal controls."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import placement as p


def config():
    return {'args': ['--pack', '/old/pack', '--serve', '--max-context', '1048576',
            '--prefill-chunk', '4096', '--tp', '1', '--dspark', 'on', '--cpu-threads', '24',
            '--mmap-experts', 'off', '--expert-profile', '/old/profile'],
            'env': {'DS4_YOCO': '1', 'STRATA_DS4_PROMPT_SKIP': '1', 'DS4_REQUIRE_ALL_RAM': '1',
                    'DS4_STREAM': '0', 'STRATA_DS4_Q8_BATCH': '1', 'DS4_Q8_CHECK': '1'}}


def plan():
    rows = []
    for layer in range(40):
        sensitive = 24 <= layer <= 28
        rows.append({'layer': layer, 'members': 1, 'slots': list(range(256)) + [-1]*128,
                     'counts': [1]*384, 'role_types': [21,21,18] if sensitive else [16,16,18],
                     'role_bytes': [5068800,5068800,4515840] if sensitive else [3041280,3041280,4515840]})
    return {'schema': 'ds4-actual-placement-v1', 'context_total': 1048576, 'prefill_chunk': 4096,
            'drafter_blocks': 3, 'routed_experts_loaded': False, 'inference_executed': False,
            'expert_cache': False, 'CPU_experts': 5120, 'GPU_experts': 10240,
            'CPU_base_payload_bytes': sum(sum(r['role_bytes'])*128 for r in rows), 'layers': rows}


class Placement(unittest.TestCase):
    def test_exact_new_namespace_and_preserved_existing_output(self):
        out = p.E / 'results/s2-placement-P0-20261101T190000Z'
        self.assertEqual(p.paths(out)[1], p.E / 'maintenance' / out.name)
        for name in ('s2-placement-P1-20261101T190000Z', 'maya-s-old-20261101T190000Z', '../elsewhere'):
            with self.assertRaises(ValueError): p.paths(p.E / 'results' / name)

    def test_argv_is_diagnostic_only_same_capacity_and_drafter(self):
        base = config(); before = copy.deepcopy(base)
        args = p.argv(base, Path('/tmp/native'))
        self.assertEqual(base, before); self.assertNotIn('--serve', args)
        self.assertEqual(args[0], str(p.NATIVE))
        self.assertEqual(args[-2:], ['--placement-plan', '/tmp/native/actual-placement.json'])
        self.assertEqual(args.count('--no-expert-cache'), 1)
        self.assertEqual(args[args.index('--pack')+1], str(p.PACK))
        self.assertEqual(args[args.index('--max-context')+1], '1048576')

    def test_capacity_or_drafter_reductions_and_foreign_modes_refused(self):
        for key, value in (('--max-context','262144'), ('--dspark','off'), ('--tp','2'), ('--mmap-experts','on')):
            cfg = config(); cfg['args'][cfg['args'].index(key)+1] = value
            with self.assertRaises(ValueError): p.argv(cfg, Path('/tmp/native'))
        for key in ('--cpu-native', '--expert-cache', '--placement-plan', '--layer-split', '--ids'):
            cfg = config(); cfg['args'].append(key)
            with self.assertRaises(ValueError): p.argv(cfg, Path('/tmp/native'))

    def test_environment_rebases_only_private_namespaces(self):
        env = p.environment(config(), Path('/tmp/native'), {'WINDOW_OWNED':'yes'})
        self.assertEqual(env['WINDOW_OWNED'], 'yes')
        self.assertEqual(env['STRATA_DS4_SLOT_DIR'], '/tmp/native/cache')
        self.assertEqual(env['DS4_REQUIRE_ALL_RAM'], '1')
        for key, value in (('DS4_STREAM','1'), ('DS4_Q8_CHECK','0'), ('DS4_REQUIRE_ALL_RAM','0'), ('DS4_FLOW','1')):
            cfg = config(); cfg['env'][key] = value
            with self.assertRaises(ValueError): p.environment(cfg, Path('/tmp/native'), {})

    def test_actual_complete_map_and_sensitive_iq3_roles(self):
        value = plan(); counts, gpu = p.validate_plan(value)
        self.assertEqual(len(counts),40); self.assertEqual(gpu[24],list(range(256)))
        self.assertEqual(sum(384-len(row) for row in gpu),5120)
        self.assertFalse(value['routed_experts_loaded']); self.assertFalse(value['inference_executed'])

    def test_duplicate_holey_invalid_slots_and_empty_counts_refused(self):
        for mutation in ('duplicate','hole','negative','empty','bool'):
            value = plan(); row = value['layers'][0]
            if mutation == 'duplicate': row['slots'][1] = 0
            if mutation == 'hole': row['slots'][255] = 256
            if mutation == 'negative': row['slots'][383] = -2
            if mutation == 'empty': row['counts'] = [0]*384
            if mutation == 'bool': row['counts'][0] = True
            with self.assertRaises(ValueError): p.validate_plan(value)

    def test_wrong_total_bytes_context_drafter_quant_or_role_refused(self):
        for key, wrong in (('CPU_experts',5119), ('GPU_experts',10241), ('CPU_base_payload_bytes',1),
                           ('context_total',262144), ('drafter_blocks',0), ('expert_cache',True), ('inference_executed',True)):
            value = plan(); value[key] = wrong
            with self.assertRaises(ValueError): p.validate_plan(value)
        value = plan(); value['layers'][24]['role_types'][0] = 16
        with self.assertRaises(ValueError): p.validate_plan(value)

    def test_actual_memory_floor_is_bounded_without_lowering_requirement(self):
        now = [0]; values = iter((80*2**30,87*2**30,88*2**30))
        def pause(sec): now[0] += sec
        self.assertEqual(p.memory_floor(lambda:next(values),clock=lambda:now[0],pause=pause),88*2**30)
        now[0] = 0
        with self.assertRaises(p.ResourceDeferred):
            p.memory_floor(lambda:87*2**30,clock=lambda:now[0],pause=pause)
        self.assertEqual(now[0],60)

    def test_owned_child_cleanup_never_signals_unrelated_pid(self):
        class Proc:
            pid=12345
            def poll(self): return 0
        with patch.object(p.os,'killpg',side_effect=ProcessLookupError) as kill:
            p.stop_child(Proc()); kill.assert_called_once_with(12345,0)
        with patch.object(p.os,'killpg') as kill:
            with self.assertRaises(RuntimeError): p.stop_child(Proc())
            self.assertEqual([call.args[0] for call in kill.call_args_list],[12345,12345])

    def test_atomic_receipt_preserves_partial_residue_and_alias(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / 'receipt.json'; p.emit(path, {'passed':True})
            self.assertTrue(json.loads(path.read_text())['passed'])
            path.with_suffix('.json.tmp').write_text('partial')
            with self.assertRaises(ValueError): p.emit(path, {'passed':False})
            alias = Path(t) / 'alias'; alias.symlink_to(path)
            with self.assertRaises(ValueError): p.emit(alias,{})

    def test_cpu_proofs_require_both_physical_maps_ids_resources_and_clean_exit(self):
        sources = {'placement.py':'a'}
        proofs = {}
        for label, platform in (('mac','darwin'),('ubuntu','linux')):
            proofs[label] = {'passed':True,'returncode':0,'controls':1,'test_ids':['one'],
                'source_sha256':sources,'input_sha256':{'shared':'pin'},'failures':0,'errors':0,
                'observed':{'platform':platform,'cpu':[30,30],'nice':15,
                    'as':[512*2**20]*2 if platform=='linux' else None,'pid':123,'pgid':123,
                    'dont_write_bytecode':True,'environment':{'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1',
                        'OPENBLAS_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1'}}}
        p.cpu_contract(proofs,sources)
        for key, wrong in (('controls',0),('returncode',1),('test_ids',['other']),('passed',False)):
            changed = copy.deepcopy(proofs); changed['ubuntu'][key] = wrong
            with self.assertRaises(ValueError): p.cpu_contract(changed,sources)
        changed = copy.deepcopy(proofs); changed['ubuntu']['observed']['as'] = None
        with self.assertRaises(ValueError): p.cpu_contract(changed,sources)


if __name__ == '__main__': unittest.main(verbosity=2)
