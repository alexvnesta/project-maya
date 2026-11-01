"""Focused new adapter/policy/custody controls; no imports of model runtimes."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import runtime as r


def config():
    return {'exe': '/selected', 'args': ['--pack', '/selected-pack', '--serve', '--tp', '1',
        '--max-context', '1048576', '--prefill-chunk', '4096', '--dspark', 'on', '--dspark-conf', '0.65',
        '--cpu-threads', '24', '--mmap-experts', 'off', '--expert-profile', '/seed', '--ablate-scale', '1',
        '--ablate', str(r.D / 'runtime-direction-L22.gguf')],
        'env': {'STRATA_DS4_DISK_SKIP_W': '0', 'DS4_YOCO': '1', 'STRATA_DS4_PROMPT_SKIP': '1',
            'DS4_REQUIRE_ALL_RAM': '1', 'DS4_STREAM': '0', 'STRATA_DS4_Q8_BATCH': '1', 'DS4_Q8_CHECK': '1',
            'DS4_LT_STORE': '/selected-lt', 'STRATA_DS4_SLOT_DIR': '/selected-cache'}}


def profile():
    return {'exe': '/new/maya-ds4', 'pack': '/new/pack', 'native_payload': '/new/native.cpu',
            'native_map_sha256': 'a'*64, 'native_artifact_sha256': 'b'*64}


class Essential(unittest.TestCase):
    def test_exact_panel_policy_and_fresh_candidate_config_preserve_base(self):
        panel = r.panel(); self.assertEqual(len(panel.fixture()['cases']), 2)
        self.assertEqual(panel.POLICY['reasoning_effort'], 100); self.assertEqual(panel.POLICY['max_tokens'], 32768)
        base = config(); before = copy.deepcopy(base); folder = Path('/fresh/native')
        c = r.make_config(base, folder, 'B0', profile())
        self.assertEqual(base, before); self.assertEqual(c['env']['DS4_COPY_DIRECT'], '1')
        self.assertEqual(c['args'][-6:], ['--cpu-native', '/new/native.cpu', '--cpu-native-map', 'a'*64,
                                        '--cpu-native-identity', 'b'*64])
        self.assertIn('--profile-readonly', c['args']); self.assertIn('/fresh/native/routing.bin', c['args'])
        a = r.make_config(base, folder, 'A0', dict(profile(), exe='/selected', pack='/selected-pack'))
        self.assertNotIn('--cpu-native', a['args']); self.assertNotIn('DS4_COPY_DIRECT', a['env'])
        self.assertNotIn('--profile-readonly', a['args']); self.assertNotIn('--profile-out', a['args'])

    def test_arm_specific_schedule_keeps_final_known_answer_and_two_mains_identical(self):
        from types import SimpleNamespace
        def case(i): return {'id':i,'kind':'literal','request':{'messages':[{'role':'user','content':i}]},'expected':'ok'}
        fixtures = SimpleNamespace(request=lambda text:{'messages':[{'role':'user','content':text}]},
            source_images=lambda:([],[]),quality_cases=lambda urls:[case('image-state-'+str(i)) for i in range(4)],
            lifecycle_cases=lambda:[case('life0'),case('life1'),case('cancel'),dict(case('recovery'),dependency='cancel')])
        b, a = r.expected_cases(fixtures,'B0'), r.expected_cases(fixtures,'A0')
        self.assertEqual((len(b),len(a)),(11,3))
        self.assertEqual([c['request'] for c in b[-3:]],[c['request'] for c in a])
        self.assertNotIn('dependency',a[0]);self.assertFalse(any('logprobs' in c['request'] or 'top_logprobs' in c['request'] for c in a+b))
        self.assertEqual(b[0]['id'],'s2-source-known-answer');self.assertEqual(b[0]['kind'],'literal')
        encoded = [dict(c,prompt_ids=[1,2],prompt_tokens=2,prompt_ids_sha256=r.digest([1,2]),request_sha256=r.digest(c['request'])) for c in a]
        manifest = {'context_total':1048576,'output_allowance':262144,'cases':encoded}
        r.fixture_contract(manifest,fixtures,'A0')
        manifest['cases'][-1]['request'] = {'altered':True}
        with self.assertRaises(ValueError):r.fixture_contract(manifest,fixtures,'A0')

    def test_published_asset_chain_accepts_actual_fingerprint_not_invented_hash_child(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t).resolve()/'published';path.write_bytes(b'publication')
            stamp=r.fingerprint(path)
            q={'files':{'raw-terminal':'pin','raw-constructor':'pin'},
               'artifact_chains':{'original':{'kind':'selected-publication','raw_paths':['raw-terminal','raw-constructor']}},
               'large_verified':{str(path):{'chain':'original','sha256':'publishedSHA','fingerprint':stamp}}}
            evidence={str(path):{'chain':'original','sha256':'publishedSHA','fingerprint':stamp,
                                'raw_paths':['raw-terminal','raw-constructor'],'owned_writer_lock_free':True}}
            r.asset_contract(q,lambda checked:evidence)
            with self.assertRaises(ValueError):r.asset_contract(q,lambda checked:{'passed':True})
            wrong=copy.deepcopy(evidence);wrong[str(path)]['owned_writer_lock_free']=False
            with self.assertRaises(ValueError):r.asset_contract(q,lambda checked:wrong)
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError):r.asset_contract(q,lambda checked:evidence)

    def test_actual_ALL8_terminal_schema_requires_published_revision_hash_and_all_rows(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();acq=root/'base-acquisition-v2';acq.mkdir()
            manifest={'repo':'peasantsmith/DeepSeek-V4.1-Flash-1017-Maya-GGUF',
                'revision':'d1fc01009f21e26157acb6858c315d0365483b72','total_bytes':347445667721,
                'files':[{'path':'part%d'%i,'size':347445667714 if i==0 else 1,'sha256':'%064x'%i} for i in range(8)]}
            terminal={'status':'ALL_EIGHT_ASSETS_VERIFIED_NO_MODEL_RUN','returncode':0,
                'manifest_sha256':'22ecce3e7085e29520fadaa67d603beb8cc0905f834ff3563029f6038825034b',
                'asset_root':str(root/'base-acquisition-v1/assets'),
                'files':[dict(path=x['path'],bytes=x['size'],sha256=x['sha256'],status='DOWNLOADED_VERIFIED') for x in manifest['files']]}
            mp,tp=acq/'ASSET_MANIFEST.json',acq/'acquisition-state.json'
            mp.write_text(json.dumps(manifest));tp.write_text(json.dumps(terminal))
            raw=[str(mp),str(tp),'pinned-attempt','pinned-controller-exit','pinned-constructor']
            assets={str(root/'base-acquisition-v1/assets'/x['path']):{'chain':'base','sha256':x['sha256'],
                'fingerprint':[1,i,x['size'],2,3]} for i,x in enumerate(manifest['files'])}
            q={'files':dict({p:'pin' for p in raw},**{str(mp):terminal['manifest_sha256']}),
                'artifact_chains':{'base':{'kind':'base-acquisition-publication','raw_paths':raw}},'large_verified':assets}
            actual={name:dict(row,raw_paths=raw,owned_writer_lock_free=True) for name,row in assets.items()}
            with patch.object(r,'Q',root),patch.object(r,'fingerprint',side_effect=lambda name:assets[str(name)]['fingerprint']):
                r.asset_contract(q,lambda checked:actual)
                for key,value in (('returncode',1),('status','GENERIC_PASSED'),('files',terminal['files'][:-1])):
                    tp.write_text(json.dumps(dict(terminal,**{key:value})))
                    with self.assertRaises(ValueError):r.asset_contract(q,lambda checked:actual)

    def test_capacity_drafter_skip_helper_or_foreign_state_cannot_enter(self):
        for flag, value in (('--max-context', '262144'), ('--prefill-chunk', '1024'), ('--dspark', 'off'),
                            ('--dspark-conf', '0.2'), ('--ablate-scale', '0'), ('--cpu-threads', '12')):
            c = config(); c['args'][c['args'].index(flag)+1] = value
            with self.subTest(flag=flag), self.assertRaises(ValueError): r.make_config(c, Path('/fresh/native'), 'B0', profile())
        for key, value in (('STRATA_DS4_DISK_SKIP_W', '.01'), ('MAYA_DS4_RAM_SKIP_W', '.1'),
                           ('DS4_HELPER', '1'), ('DS4_STORE_GB', '3'), ('DS4_SERVE_DUMP', 'x'), ('DS4_REQUIRE_ALL_RAM', '0')):
            c = config(); c['env'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): r.make_config(c, Path('/fresh/native'), 'B0', profile())
        c = config(); c['args'].append('--expert-cache')
        with self.assertRaises(ValueError): r.make_config(c, Path('/fresh/native'), 'B0', profile())

    def test_actual_native_process_contract_rejects_argv_env_cgroup_and_executable(self):
        c = r.make_config(config(), Path('/fresh/native'), 'B0', profile())
        argv = [c['exe'], '--serve', *c['args'], '--layer-split', 'auto', '']
        group = '0::/user.slice/strata-deepseek-window.service'
        r.process_contract(c, argv, c['env'], group, True)
        for args, env, cg, same in ((argv[:-1], c['env'], group, True),
                                  (argv, dict(c['env'], DS4_HELPER='1'), group, True),
                                  (argv, c['env'], '0::/foreign', True), (argv, c['env'], group, False)):
            with self.assertRaises(ValueError): r.process_contract(c, args, env, cg, same)

    def test_cached_foreign_support_origin_is_rejected_before_import(self):
        from types import SimpleNamespace
        names = ('pv_runtime','pv_config','pv_controls','ae_runtime','ae_config','ae_controls',
                 'imma_config','imma_fixtures','imma_storage','protocol','skip_controls','q8_phase')
        q = {'import_origins':{name:'/expected/'+name+'.py' for name in names},
             'files':{'/expected/'+name+'.py':'pin' for name in names}}
        with patch.object(r,'sha',return_value='pin'), patch.dict(r.sys.modules,{'pv_runtime':SimpleNamespace(__file__='/foreign/pv_runtime.py')}):
            with self.assertRaises(ValueError):r.import_origins(q)

    def test_profile_snapshots_count_trunk_and_drafter_but_only_sensitive_selected_CPU(self):
        before = [0]*(43*384); after = before.copy(); slots = [[-1]*384 for _ in range(40)]
        after[23*384+1] = 50; after[24*384+2] = 3; after[42*384] = 10
        observed = r.participation(before, after, [[23,1], [24,2]], slots)
        self.assertEqual(observed['sensitive_selected_CPU_hits'], [[24,2,3]])
        self.assertFalse(observed['direct_native_counter_telemetry'])
        slots[24][2] = 0
        with self.assertRaises(ValueError): r.participation(before, after, [[24,2]], slots)
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)/'routing.bin'; self.assertEqual(r.profile_snapshot(p), before)
            p.write_bytes(bytes(43*384*4)); self.assertEqual(r.profile_snapshot(p), before)
            p.write_bytes(bytes(40*384*4))
            with self.assertRaises(ValueError): r.profile_snapshot(p)

    def test_returned_logprob_check_is_finite_bounded_not_equivalence(self):
        def response(v): return {'events': [{'choices': [{'logprobs': {'content': [
            {'logprob': v, 'top_logprobs': [{'logprob': -2.}]}]}}]}]}
        self.assertFalse(r.finite_logprobs(response(-1.))['full_vocabulary_or_equivalence_claim'])
        for value in (float('nan'), float('inf'), None, True):
            with self.assertRaises(ValueError): r.finite_logprobs(response(value))
        with self.assertRaises(ValueError): r.finite_logprobs({'events': []})

    def test_profile_snapshot_waits_for_current_request_atomic_publication(self):
        now = [0.]
        with patch.object(r, 'profile_generation', return_value='old'):
            with self.assertRaises(ValueError):
                r.saved_profile('unused', 'old', clock=lambda: now[0], pause=lambda s: now.__setitem__(0, now[0]+s))
        with patch.object(r, 'profile_generation', side_effect=['new', 'new', 'new']), \
             patch.object(r, 'profile_snapshot', return_value=[1]):
            self.assertEqual(r.saved_profile('unused', 'old'), [1])

    def test_existing_STAT_identity_hash_activity_and_done_required(self):
        with tempfile.TemporaryDirectory() as t:
            trace = Path(t)/'native-003'; trace.mkdir()
            raw = 'STAT cpu=1.2 ram=1.2 draft_ms=2 verify_ms=3 draft_rounds=1'
            row = {'native_pid': 123, 'trace_number': 3, 'seconds': .1, 'raw': raw}
            (trace/'stat-lines.jsonl').write_text(json.dumps(row)+'\n')
            proof = {'native_pid': 123, 'trace_number': 3, 'complete': True, 'DONE_observed': True,
                'capture_error': None, 'primary_error': None, 'samples': 1,
                'raw_lines_sha256': hashlib.sha256((raw+'\n').encode()).hexdigest()}
            (trace/'stat-receipt.json').write_text(json.dumps(proof))
            self.assertEqual(r.stat_activity(trace, 123, True)['draft_rounds'], 1)
            with self.assertRaises(ValueError): r.stat_activity(trace, 124, True)
            oldraw='STAT cpu=1.2 ram=1.2'
            oldrow=dict(row,raw=oldraw);(trace/'stat-lines.jsonl').write_text(json.dumps(oldrow)+'\n')
            oldproof=dict(proof,raw_lines_sha256=hashlib.sha256((oldraw+'\n').encode()).hexdigest())
            (trace/'stat-receipt.json').write_text(json.dumps(oldproof))
            self.assertEqual(r.stat_activity(trace,123,True,candidate=False)['cpu'],1.2)
            proof['DONE_observed'] = False; (trace/'stat-receipt.json').write_text(json.dumps(proof))
            with self.assertRaises(ValueError): r.stat_activity(trace, 123, True)

    def test_B0_then_separately_accepted_restored_A0_no_loop_or_replay(self):
        r.prerequisite('B0', {})
        registry = {'B0': {'output': 'candidate'}}
        closure = dict(arm='B0', fully_manually_read=True, source_numerical_core_passed=True,
            natural_two_tasks_passed=True, independent_code_grade_passed=True, prose_facts_accepted=True,
            owned_execution_closed=True, selected_restored=True, output='candidate', promotion_performed=False)
        r.prerequisite('A0', registry, closure)
        for key in ('fully_manually_read', 'source_numerical_core_passed', 'natural_two_tasks_passed',
                    'independent_code_grade_passed', 'prose_facts_accepted', 'owned_execution_closed', 'selected_restored'):
            with self.subTest(key=key), self.assertRaises(ValueError): r.prerequisite('A0', registry, dict(closure, **{key: False}))
        with self.assertRaises(ValueError): r.prerequisite('B0', registry)
        with self.assertRaises(ValueError): r.prerequisite('A0', {})

    def test_fresh_namespace_alias_and_residue_hold(self):
        with tempfile.TemporaryDirectory() as t:
            e = Path(t).resolve(); (e/'results').mkdir(); (e/'maintenance').mkdir()
            with patch.object(r, 'E', e):
                out = e/'results/s2-essential-B0-20261101T210000Z'; r.paths(out, 'B0')
                with self.assertRaises(ValueError): r.paths(out, 'A0')
                out.mkdir()
                with self.assertRaises(ValueError): r.paths(out, 'B0')
                r.paths(out, 'B0', True)
            f = out/'receipt.json'; r.emit(f, {'x': 1}); f.with_suffix('.json.tmp').write_text('residue')
            with self.assertRaises(ValueError): r.emit(f, {'x': 2})

    def test_owned_window_exact_phase_and_not_terminal(self):
        from types import SimpleNamespace
        output, proof = Path('/owned/output'), Path('/owned/proof')
        argv = [str(r.R/'venv/bin/python3.14'), '-B', str(r.HERE/'runtime.py'), '--phase', '--arm', 'B0',
                '--output', str(output), '--proof', str(proof)]
        row = {'command': argv, 'continued_from': 'old', 'test_returncode': None, 'maintenance_held': False, 'restored': False}
        old = SimpleNamespace(owned_window=lambda: ('window', row))
        self.assertEqual(r.window(old, output, 'B0', proof), 'window')
        for key, value in (('command', argv[:-1]), ('test_returncode', 0), ('restored', True), ('maintenance_held', True)):
            changed = dict(row, **{key: value})
            with self.assertRaises(ValueError): r.window(SimpleNamespace(owned_window=lambda: ('window', changed)), output, 'B0', proof)

    def test_phase_requires_same_controller_qualification_registry_and_active_custody(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t).resolve(); here = root/'adapter'; here.mkdir()
            (root/'results').mkdir(); (root/'maintenance').mkdir()
            out = root/'results/s2-essential-B0-20261101T220000Z'
            meta = root/'maintenance'/out.name; meta.mkdir()
            proof = {'mode':r.MODE,'arm':'B0','output':str(out),'qualification_sha256':'q','controller_pid':123}
            active = dict(proof,status=r.RUNNING)
            state = {'decode_optimization_current':active,'active_private_phase':str(meta),
                'maintenance_controller':str(meta/'state.json'),'active_gpu_experiment':True,'active_cpu_build':None}
            (meta/'proof.json').write_text(json.dumps(proof)); (meta/'state.json').write_text(json.dumps(active))
            (here/'arms.json').write_text(json.dumps({'B0':dict(proof,attempted=True)}))
            (root/'STATE.json').write_text(json.dumps(state))
            with patch.object(r,'E',root),patch.object(r,'HERE',here):
                self.assertEqual(r.phase_proof(out,'B0',meta/'proof.json'),proof)
                for key,value in (('active_cpu_build',{'foreign':True}),('active_private_phase','foreign'),('active_gpu_experiment',False)):
                    changed=dict(state,**{key:value});(root/'STATE.json').write_text(json.dumps(changed))
                    with self.assertRaises(ValueError):r.phase_proof(out,'B0',meta/'proof.json')
                (root/'STATE.json').write_text(json.dumps(state))
                (here/'arms.json').write_text(json.dumps({'B0':dict(proof,attempted=True,controller_pid=124)}))
                with self.assertRaises(ValueError):r.phase_proof(out,'B0',meta/'proof.json')

    def test_bothhost_CPU_contract_requires_exact_source_IDs_limits_group_and_exit(self):
        review = {'source_map': {'runtime.py': 'x'}, 'input_map': {'panel': 'p'}, 'test_ids': ['one']}
        observed = {'pid': 123, 'ppid': 122, 'pgid': 123, 'platform': 'linux', 'cpu': [30,30], 'as': [512*2**20]*2,
            'nice': 15, 'dont_write_bytecode': True, 'environment': {k:v for k,v in r.CPU_ENV.items() if k not in ('PATH','LANG','LC_ALL')}}
        proof = dict(review, passed=True, returncode=0, failures=0, errors=0, controls=1, observed=observed,
                     supervisor_pid=122, isolated=True)
        child = {'pid':123,'returncode':0,'error':None,'cleanup':[],'elapsed_seconds':.1}
        r.cpu_contract(proof, child, review, 'linux')
        for key, value in (('passed',False),('controls',0),('failures',1),('errors',1),('returncode',1),('isolated',False)):
            with self.assertRaises(ValueError): r.cpu_contract(dict(proof, **{key:value}),child,review,'linux')
        for key, value in (('pid',124),('returncode',1),('cleanup',['survived'])):
            with self.assertRaises(ValueError): r.cpu_contract(proof,dict(child, **{key:value}),review,'linux')


if __name__ == '__main__': unittest.main(verbosity=2)
