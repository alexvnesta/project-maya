"""Fresh four-state owner controls; all process/service boundaries are synthetic."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import qv_owner as c
f = c.runtime.original_module('ms_fixtures')
r, config = c.runtime, c.config
q = c
SOURCE = r.original_model_dir / 'quality-fixtures-B.json'
BASE = f.E / 'decode-optimization-20261028/model-v1/base-config.json'


def cases(which='B'):
    return copy.deepcopy(json.loads(r.encoded_path(which).read_text())['cases'])


def sample(): return cases()[0]


def answer(case=None):
    case=case or sample()
    response={'status':200,'done':True,'cancelled':False,'finish_reason':'stop',
              'content':json.dumps(case['expected']),'reasoning':'synthetic only'}
    reuse=0 if case['expected_reuse']=='zero' else case['prompt_tokens']-1
    proof={'observed_tokens':7,'prompt_tokens':case['prompt_tokens'],'client_full_s':.02,
           'native':{'generated':7,'prompt_tokens':case['prompt_tokens'],'finish':'stop','reused':reuse,
                     'drafts_offered':3,'drafts_accepted':2,'prompt_ms':1.0,'decode_ms':2.0}}
    return response,proof


class Manifest(unittest.TestCase):
    def test_both_exact_original_four_state_manifests_no_encoding(self):
        with patch.object(f,'load_support',side_effect=AssertionError('No encoding')):
            for arm,which in [('QS0','A'),('QS1','B')]:
                original=json.loads(r.encoded_path(which).read_text())
                self.assertEqual(c.manifest('quality',arm),original)
                self.assertEqual([x['prompt_tokens'] for x in original['cases']],[8469,8469,8656,8469])
                self.assertEqual([x['length'] for x in original['cases'][2]['image_spans']],[206,206])

    def test_source_bytes_changed_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve();(p/'quality-fixtures-B.json').write_bytes(SOURCE.read_bytes()+b' ')
            with patch.object(r,'original_model_dir',p),patch.object(r,'original_module',return_value=f):
                with self.assertRaisesRegex(ValueError,'artifact'):r.quality_manifest('QS1')

    def test_changed_ids_refused_even_with_test_source_pin(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve();value=json.loads(SOURCE.read_text());value['cases'][0]['prompt_ids'][0]+=1
            target=p/'quality-fixtures-B.json';target.write_text(json.dumps(value))
            with patch.object(r,'original_model_dir',p),patch.object(r,'original_module',return_value=f), \
                 patch.dict(r.QUALITY_MANIFEST_PINS,{'B':r.sha(target)}):
                with self.assertRaises(ValueError):r.quality_manifest('QS1')

    def test_wrong_mode_arm_rejected_before_manifest(self):
        with patch.object(r,'quality_manifest') as read:
            for mode,arm in [('longcold','LC1'),('quality','QS2'),('prose','B1')]:
                with self.assertRaises(ValueError):c.manifest(mode,arm)
        read.assert_not_called()

    def test_exact_native_dump_policy_both_packs(self):
        base=json.loads(BASE.read_text())
        for arm in ('QS0','QS1'):
            folder=config.E/('results/maya-s-quality-v2-'+arm+'-20261030T180000Z/native')
            value=config.make_config(base,folder,'quality',arm)
            self.assertEqual(value['env']['DS4_SERVE_DUMP'],str(folder/'logits'))
            self.assertEqual(value['hosted_default_effort'],100)
            self.assertNotIn('max_tokens',value)


class Boundaries(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.p=Path(self.tmp.name).resolve();self.out=self.p/'output'
        self.old=types.SimpleNamespace(q8_phase=types.SimpleNamespace(admission=Mock(return_value='window')))
        self.patchers=[patch.object(c,'helpers',return_value=(object(),self.old,object(),object(),object(),object(),object())),
                      patch.object(c,'read_proof',return_value={'qualification_sha256':'a'*64}),
                      patch.object(r,'qualified',return_value={}),patch.object(c,'window_contract'),
                      patch.object(c,'manifest',return_value={'cases':[sample()]})]
        for x in self.patchers:x.start();self.addCleanup(x.stop)

    def test_fence_wraps_body_and_restores_before_terminal_receipt(self):
        events=[]
        class Fence:
            def __enter__(self):events.append('install');return {},[]
            def __exit__(self,*a):events.append('restore')
        emit=r.emit
        def write(path,value):events.append('receipt');emit(path,value)
        with patch.object(c.controls,'fenced_phase',return_value=Fence()), \
             patch.object(c,'phase_body',side_effect=lambda *a:(events.append('body') or {'passed':True})), \
             patch.object(r,'emit',side_effect=write):
            self.assertEqual(c.phase(self.out,'quality','QS0','unused'),0)
        self.assertEqual(events,['install','body','restore','receipt'])

    def test_failed_fence_restoration_never_publishes_terminal_success(self):
        class Fence:
            def __enter__(self):return {},[]
            def __exit__(self,*a):raise RuntimeError('restore failure')
        with patch.object(c.controls,'fenced_phase',return_value=Fence()),patch.object(c,'phase_body',return_value={}):
            with self.assertRaisesRegex(RuntimeError,'restore failure'):c.phase(self.out,'quality','QS0','unused')
        self.assertFalse((self.out/'receipt.json').exists())

    def test_fence_install_failure_blocks_body(self):
        with patch.object(c.controls,'fenced_phase',side_effect=RuntimeError('fence')),patch.object(c,'phase_body') as body:
            with self.assertRaises(RuntimeError):c.phase(self.out,'quality','QS0','unused')
        body.assert_not_called()

    def test_foreign_mode_blocks_before_support(self):
        with self.assertRaises(ValueError):c.phase(self.out,'prose','A1','unused')
        c.helpers.assert_not_called()

    def test_existing_output_blocks_replay(self):
        self.out.mkdir()
        with patch.object(c.controls,'fenced_phase') as fence:
            with self.assertRaises(FileExistsError):c.phase(self.out,'quality','QS0','unused')
        fence.assert_not_called()

class Custody(unittest.TestCase):
    def test_exact_window_entry_and_no_completed_or_foreign_window(self):
        output=r.E/'results/maya-s-quality-v2-QS0-20261030T180000Z';proof=r.E/'maintenance'/output.name/'proof.json'
        command=[str(c.R/'venv/bin/python3.14'),'-B',str(c.P/'qv_owner.py'),'--phase','--mode','quality',
                 '--arm','QS0','--output',str(output),'--proof',str(proof)]
        value={'command':command,'continued_from':'last-clean','test_returncode':None,'maintenance_held':False,'restored':False}
        old=types.SimpleNamespace(owned_window=Mock(return_value=(c.R/'windows/new.json',value)))
        c.window_contract(old,output,'quality','QS0',proof)
        for change in [{'test_returncode':0},{'restored':True},{'command':command[:2]+['ms_quality.py']+command[3:]}]:
            old.owned_window.return_value=(c.R/'windows/new.json',{**value,**change})
            with self.assertRaises(ValueError):c.window_contract(old,output,'quality','QS0',proof)

    def test_registry_reserves_baseline_once(self):
        with tempfile.TemporaryDirectory() as d,patch.object(c,'P',Path(d).resolve()),patch.object(r,'P',Path(d).resolve()):
            p=Path(d).resolve()/'quality-arms.json';p.write_text('{}')
            c.reserve('quality','QS0','owned-output','owned-proof');value=json.loads(p.read_text())
            self.assertEqual(list(value),['QS0']);self.assertFalse(value['QS0']['accepted'])
            with self.assertRaises(ValueError):c.reserve('quality','QS0','owned-output','owned-proof')
            self.assertEqual(json.loads(p.read_text()),value)

    def test_quality_requires_current_entry_and_CPU_membership(self):
        with tempfile.TemporaryDirectory() as d, patch.object(r,'P',Path(d).resolve()):
            p=Path(d).resolve(); path=p/'quality-qualification.json'; pin='a'*64
            names=('qv_config.py','qv_runtime.py','qv_controls.py','qv_owner.py','qv_audit.py','qv_dispatch.py')
            sources={n:'e'*64 for n in names}; files={str(p/n):v for n,v in sources.items()}
            files.update({str(r.E/k):v for k,v in r.PINS.items()})
            files.update({str(r.R/'window.py'):'170722b54e0245e7268bffe2f39f8e30bee2fc79c056544f4f9b03942c48f25f',
                          str(r.D/'config.json'):config.BASE_SHA,str(r.D/'bin/maya-ds4'):config.BASE_NATIVE})
            q={'mode':'quality','root_manual_review':True,'astra_manual_review':True,
               'authorization_sha256':'cb2698ff10b5bd42b029968f20f59aa78d3d6924b4b8a4b5548bc3b28e78ce5a',
               'context':1048576,'output_allowance':262144,'files':files,
               'CPU_groups':[{'source_sha256':sources,'proofs':{}}], 'pack_and_resource_prerequisite_reviewed':True,
               'private_memory_max':r.MEMORY_MAX,'host_margin':r.HOST_MARGIN}
            # Existing proof/pack contracts have separate real controls; isolate the new entry selector here.
            with patch.object(r,'sha',side_effect=lambda x:pin if Path(x)==path else files.get(str(x),'e'*64)), \
                 patch.object(r,'cpu_membership'),patch.object(r,'closed_cs1'),patch.object(r,'closed_lc1'),patch.object(r,'STORAGE_PINS',{}),patch.object(r,'pack_custody'),patch.object(r,'encoded_custody'):
                path.write_text(json.dumps(q)); self.assertEqual(r.qualified('quality',pin)['mode'],'quality')
                for missing in ('file','CPU'):
                    bad=copy.deepcopy(q)
                    if missing=='file':bad['files'].pop(str(p/'qv_owner.py'))
                    else:bad['CPU_groups'][0]['source_sha256'].pop('qv_owner.py')
                    path.write_text(json.dumps(bad))
                    with self.subTest(missing=missing),self.assertRaisesRegex(ValueError,'Executing changed source'):
                        r.qualified('quality',pin)

    def test_full_phase_proof_requires_same_owned_controller(self):
        with tempfile.TemporaryDirectory() as d:
            e=Path(d).resolve();p=e/'mode';p.mkdir();(e/'results').mkdir();(e/'maintenance').mkdir()
            output=e/'results/maya-s-quality-v2-QS0-20261030T180000Z';meta=e/'maintenance'/output.name;meta.mkdir()
            proof={'mode':'quality','arm':'QS0','output':str(output),'qualification_sha256':'a'*64,
                   'qualified_for_owned_maya_s':True}
            state={**proof,'status':r.statuses('quality')['running'],'controller_pid':99}
            active={'decode_optimization_current':state,'active_private_phase':str(meta),'active_gpu_experiment':True,
                    'maintenance_controller':str(meta/'state.json')}
            registry={'QS0':{'attempted':True,'output':str(output),'controller_pid':99}}
            for path,value in [(meta/'proof.json',proof),(meta/'state.json',state),(e/'STATE.json',active),(p/'quality-arms.json',registry)]:
                path.write_text(json.dumps(value))
            with patch.object(c,'E',e),patch.object(c,'P',p),patch.object(r,'E',e),patch.object(r,'P',p):
                self.assertEqual(c.read_proof(output,'quality','QS0',meta/'proof.json'),proof)
                active['decode_optimization_current']['controller_pid']=100;(e/'STATE.json').write_text(json.dumps(active))
                with self.assertRaises(ValueError):c.read_proof(output,'quality','QS0',meta/'proof.json')

class FileLimitTests(unittest.TestCase):
    def test_exact_native_only_preexec_composition(self):
        original = Mock(return_value=types.SimpleNamespace(pid=71)); server = types.SimpleNamespace(popen=original)
        storage = types.SimpleNamespace(HARD_FILE_BYTES=512*2**20, native_fsize_preexec=Mock(return_value=Mock()))
        cfg = {'exe':'selected','args':['x']}; before = Mock(); emitted = []
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'pack-state-A.json').write_text(json.dumps({'storage_geometry':{'ratios':[0], 'kv_sources':[2], 'index_sources':[2]}, 'engine_version':'0.1.27','pack_files':['p']}))
            with patch.object(q.runtime, 'original_model_dir', p), patch.object(q.config, 'expected_native_argv', return_value=['selected','--serve','']), \
                 patch.object(q.runtime, 'emit', side_effect=lambda path, value: emitted.append(value)):
                q.install_dump_limit(server,cfg,p,'quality','QS0',storage)
                proc = server.popen('the Strata engine',['selected','--serve'],preexec_fn=before)
                self.assertEqual(proc.pid,71)
                original.call_args.kwargs['preexec_fn']()
                self.assertEqual(before.call_count,1); self.assertEqual(storage.native_fsize_preexec.return_value.call_count,1)
                self.assertFalse(emitted[0]['API_limits_changed'])
                with self.assertRaises(ValueError): server.popen('the Strata engine',['selected','--serve'])
        self.assertEqual(original.call_count,1)
        self.assertEqual(storage.native_fsize_preexec.call_args.args[0]['ratios'],(0,))

    def test_dump_bound_forbidden_on_timing(self):
        with self.assertRaises(ValueError): q.install_dump_limit(object(),{},Path('/unused'),'prose','A1',object())

    def test_receipt_failure_terminates_captured_native(self):
        proc=types.SimpleNamespace(pid=71,poll=lambda:None,terminate=Mock(),wait=Mock(),kill=Mock())
        server=types.SimpleNamespace(popen=Mock(return_value=proc))
        storage=types.SimpleNamespace(HARD_FILE_BYTES=512*2**20,native_fsize_preexec=Mock(return_value=Mock()))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'pack-state-A.json').write_text(json.dumps({'storage_geometry':{'ratios':[], 'kv_sources':[], 'index_sources':[]}, 'engine_version':'0.1.27','pack_files':[]}))
            with patch.object(q.runtime,'original_model_dir',p),patch.object(q.config,'expected_native_argv',return_value=['n','']),patch.object(q.runtime,'emit',side_effect=RuntimeError('receipt write')):
                q.install_dump_limit(server,{},p,'quality','QS0',storage)
                with self.assertRaisesRegex(RuntimeError,'receipt write'):server.popen('the Strata engine',['n'])
        proc.terminate.assert_called_once();proc.wait.assert_called_once_with(timeout=10)


    def test_receipt_cleanup_fault_keeps_primary(self):
        proc=types.SimpleNamespace(pid=71,poll=lambda:None,terminate=Mock(side_effect=RuntimeError('terminate failed')))
        server=types.SimpleNamespace(popen=Mock(return_value=proc))
        storage=types.SimpleNamespace(HARD_FILE_BYTES=512*2**20,native_fsize_preexec=Mock(return_value=Mock()))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'pack-state-A.json').write_text(json.dumps({'storage_geometry':{'ratios':[], 'kv_sources':[], 'index_sources':[]}, 'engine_version':'0.1.27','pack_files':[]}))
            with patch.object(q.runtime,'original_model_dir',p),patch.object(q.config,'expected_native_argv',return_value=['n','']),patch.object(q.runtime,'emit',side_effect=RuntimeError('receipt first')):
                q.install_dump_limit(server,{},p,'quality','QS0',storage)
                with self.assertRaisesRegex(RuntimeError,'receipt first') as caught:server.popen('the Strata engine',['n'])
                self.assertIn('terminate failed',str(caught.exception.__notes__))

class Body(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.e=Path(self.tmp.name).resolve();self.out=self.e/'results/maya-s-quality-v2-QS0-20261030T180000Z'
        self.folder=self.out/'native';self.folder.mkdir(parents=True);(self.folder/'tmp').mkdir()
        self.d=self.e/'selected';self.d.mkdir();(self.d/'config.json').write_bytes(BASE.read_bytes())
        (self.d/'profile-seed.bin').write_bytes(b'synthetic seed')
        (self.folder/'engine.log').write_text('synthetic startup and exact skip5801,5988\n')
        self.proc=types.SimpleNamespace(pid=71);self.processes=[];self.issued=0;self.requests=cases('A')
        def body_cleanup(body,cleanup):
            try:return body()
            finally:cleanup()
        self.old=types.SimpleNamespace(
            q8_phase=types.SimpleNamespace(SEED_SHA=r.sha(self.d/'profile-seed.bin'),environment=Mock(return_value={}),
                wait_startup=Mock(return_value=({'pid':72},{'ok':True},{'data':[]})),
                native_paths=lambda path:sorted(Path(path).glob('native-[0-9][0-9][0-9]'))),
            body_and_cleanup=body_cleanup,stop_server=Mock())
        self.bounded=Mock()
        def issue(case,folder,pid,deadline,*,requester):
            self.assertEqual(pid,72);self.assertEqual(deadline,1100);self.issued+=1
            response,proof=answer(case);self.bounded.return_value=response
            actual=requester('private-test',case['request'],deadline)
            trace=Path(folder)/('native-%03d'%self.issued);trace.mkdir()
            (trace/'tokens.jsonl').write_text(''.join(json.dumps({'token':i,'seconds':i*.001})+'\n' for i in range(7)))
            return actual,proof
        self.skip=types.SimpleNamespace(issue=Mock(side_effect=issue),ControlBudgetStop=type('Stop',(Exception,),{}),
            activation=Mock(return_value={'activation_early_rows':[5801,5988]}))
        self.protocol=types.SimpleNamespace(Stream=Mock(),json_get=Mock(),wait_for=Mock())
        self.numerical=types.SimpleNamespace(dump_snapshot=Mock(return_value={'status':'COMPLETE_SIZE_ONLY'}),
            dump_size=Mock(return_value={'bytes':517120,'rows':1}),owned_storage_snapshot=Mock())
        self.storage=types.SimpleNamespace(HARD_FILE_BYTES=512*2**20)
        original_read=Path.read_text
        def read(path,*args,**kwargs):
            if str(path)=='/proc/72/limits':return 'Max file size             536870912            536870912            bytes\n'
            return original_read(path,*args,**kwargs)
        patches=[patch.object(c,'D',self.d),patch.object(config,'E',self.e),
            patch.object(c.time,'monotonic',return_value=101),patch.object(c.subprocess,'Popen',return_value=self.proc),
            patch.object(c.controls,'startup',return_value={}),patch.object(c.controls,'actual_native',return_value={'native_pid':72}),
            patch.object(c.controls,'fence_terminal',return_value={'passed':True}),
            patch.object(c.controls,'bounded_request',self.bounded),patch.object(Path,'read_text',read),
            patch.dict(c.sys.modules,{'skip_controls':self.skip,'protocol':self.protocol})]
        for p in patches:p.start();self.addCleanup(p.stop)

    def call(self):
        return c.phase_body(self.out,'quality','QS0',{}, {'allowed_automatic_cuts':{'A':[19]}},
            'window',{'cases':self.requests},self.folder,{},self.processes,100,
            object(),self.old,self.numerical,self.storage)

    def test_four_requests_shared_deadline_dump_contract_and_cleanup(self):
        result=self.call();self.assertTrue(result['arm_results']['complete'])
        self.assertEqual(result['arm_results']['native_request_count'],4)
        self.assertEqual([x['id'] for x in result['arm_results']['rows']],list(r.QUALITY_CASE_IDS))
        self.assertEqual([x['native']['reused'] for x in result['arm_results']['rows']],[0,8468,0,8468])
        self.assertEqual(self.skip.issue.call_count,4);self.assertEqual(self.processes,[self.proc])
        self.old.stop_server.assert_called_once_with(self.proc,self.folder,timeout=100)
        self.numerical.dump_snapshot.assert_called_once_with(self.folder,complete=True)
        self.assertEqual(self.numerical.dump_size.call_count,4)
        self.assertEqual([x.args[0].name for x in self.numerical.dump_size.call_args_list],['logits.%d.f32'%i for i in range(1,5)])
        self.assertTrue(all(call.args[4] is True for call in self.bounded.call_args_list))
        self.assertTrue(all(call.args[1]['max_tokens']==32768 and call.args[1]['reasoning_effort']==100 for call in self.bounded.call_args_list))
        cfg=json.loads((self.out/'candidate-config.json').read_text())
        self.assertEqual(cfg['env']['DS4_SERVE_DUMP'],str(self.folder/'logits'))
        self.assertEqual(json.loads((self.out/'candidate-config.shared-settings.json').read_text()),{'max_tokens':262144})
        self.assertIn(str(c.P/'qv_owner.py'),c.subprocess.Popen.call_args.args[0])

    def test_actual_native_wrong_file_limit_stops_before_requests(self):
        self.storage.HARD_FILE_BYTES+=1
        with self.assertRaisesRegex(ValueError,'FSIZE'):self.call()
        self.old.stop_server.assert_called_once();self.skip.issue.assert_not_called()

    def test_incomplete_dump_set_holds_without_request_replay(self):
        self.numerical.dump_snapshot.return_value={'status':'INCOMPLETE_HOLD'}
        result=self.call();self.assertFalse(result['arm_results']['complete'])
        self.assertEqual(self.skip.issue.call_count,4);self.old.stop_server.assert_called_once()

    def test_extra_native_trace_blocks_and_cleans_once(self):
        original=self.skip.issue.side_effect
        def extra(*args,**kwargs):
            value=original(*args,**kwargs);(self.folder/'native-099').mkdir();return value
        self.skip.issue.side_effect=extra
        with self.assertRaisesRegex(ValueError,'Exactly one trace'):self.call()
        self.old.stop_server.assert_called_once();self.skip.issue.assert_called_once()

    def test_first_receipt_fault_still_closes_captured_API(self):
        emit=r.emit
        def fault(path,value):
            if Path(path).name=='server-start.json':raise RuntimeError('first receipt')
            return emit(path,value)
        with patch.object(r,'emit',side_effect=fault):
            with self.assertRaisesRegex(RuntimeError,'first receipt'):self.call()
        self.assertEqual(self.processes,[self.proc]);self.old.stop_server.assert_called_once();self.skip.issue.assert_not_called()

    def test_wrong_image_skip_state_blocks_and_closes(self):
        self.skip.activation.return_value={'activation_early_rows':[5801,5987]}
        with self.assertRaisesRegex(ValueError,'skip state'):self.call()
        self.old.stop_server.assert_called_once()

    def test_startup_timeout_has_no_new_clock_or_requests(self):
        self.old.q8_phase.wait_startup.side_effect=TimeoutError('startup')
        with self.assertRaises(TimeoutError):self.call()
        self.assertEqual(self.old.q8_phase.wait_startup.call_args.args[-1],900)
        self.old.stop_server.assert_called_once();self.skip.issue.assert_not_called()

    def test_partial_issue_holds_remaining_cases_without_retry(self):
        original=self.skip.issue.side_effect
        def partial(*args,**kwargs):
            result=original(*args,**kwargs);result[0]['done']=False;return result
        self.skip.issue.side_effect=partial;self.skip.activation.return_value={'activation_early_rows':[5801]}
        result=self.call()['arm_results']
        self.assertFalse(result['complete']);self.assertEqual(self.skip.issue.call_count,1)
        self.assertEqual(len(result['unrun_ids']),3);self.old.stop_server.assert_called_once()


if __name__=='__main__':unittest.main()
