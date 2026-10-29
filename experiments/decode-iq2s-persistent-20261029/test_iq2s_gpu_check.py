"""CPU-only controls for admission, exact receipts and owned fixture cleanup."""
import ast,copy,hashlib,json,pathlib,tempfile,types,unittest
from unittest.mock import patch,Mock
import iq2s_gpu_check as g

BIND={'invocation':'a'*32,'main_pid':10,'native_pid':11,'native_start_ticks':12}
def text(device):
    return '\n'.join(g.expected_case_ids()+[f'ALL 52 IQ2_S checks passed device{device}'])+'\n'

class Contracts(unittest.TestCase):
    def test_pending_normalization_is_idempotent(self):
        value={'status':'IQ2S_KERNEL_COMPLETE_SELECTED4096_RESTORED','verified':{'pending_public_probe':True}}
        g.normalize_pending(value);g.normalize_pending(value)
        self.assertEqual(value['resume_terminal_status'],'IQ2S_KERNEL_COMPLETE_SELECTED4096_RESTORED')
        self.assertEqual(value['status'],'IQ2S_KERNEL_SELECTED_RUNNING_PUBLIC_VERIFY_PENDING')
    def test_positive_both_devices(self):
        for device in [0,1]:self.assertEqual(g.check_result(text(device),0,device)['total_cases'],52)
    def test_nonzero_exit_rejected(self):
        with self.assertRaises(ValueError):g.check_result(text(0),1,0)
    def test_false_exit_rejected(self):
        with self.assertRaises(ValueError):g.check_result(text(0),False,0)
    def test_missing_row_rejected(self):
        with self.assertRaises(ValueError):g.check_result(text(0).splitlines()[0],0,0)
    def test_duplicate_row_rejected(self):
        with self.assertRaises(ValueError):g.check_result(text(0)+text(0),0,0)
    def test_wrong_device_rejected(self):
        with self.assertRaises(ValueError):g.check_result(text(1),0,0)
    def test_failure_output_rejected(self):
        with self.assertRaises(ValueError):g.check_result(text(0)+'FAIL canary\n',0,0)
    def test_partial_count_rejected(self):
        with self.assertRaises(ValueError):g.check_result(text(0).replace('ALL 52','ALL 51'),0,0)
    def test_each_phase_blocks(self):
        for k in ['active_private_phase','active_GPU_phase','active_gpu_experiment','private_window','active_cpu_build','production_restore_in_progress','production_verification_pending','production_temporarily_stopped']:
            self.assertFalse(g.phase_keys_free({k:True}),k)
    def test_no_phase_allows(self):self.assertTrue(g.phase_keys_free({}))
    def test_current_binding_supersedes_historical(self):
        old=dict(BIND,native_pid=20)
        self.assertEqual(g.selected_binding({'decode_optimization_current':{'selected_identity':{'start_binding':BIND}},'chunk4096_activation':{'selected_identity':{'start_binding':old}}}),BIND)
    def test_activation_binding_fallback(self):
        self.assertEqual(g.selected_binding({'chunk4096_activation':{'selected_identity':{'start_binding':BIND}}}),BIND)
    def test_binding_bool_refused(self):
        with self.assertRaises(ValueError):g.selected_binding({'chunk4096_activation':{'selected_identity':{'start_binding':dict(BIND,native_pid=True)}}})
    def test_binding_extra_refused(self):
        with self.assertRaises(ValueError):g.selected_binding({'chunk4096_activation':{'selected_identity':{'start_binding':dict(BIND,extra=1)}}})
    def test_binding_bad_invocation_refused(self):
        with self.assertRaises(ValueError):g.selected_binding({'chunk4096_activation':{'selected_identity':{'start_binding':dict(BIND,invocation='no')}}})
    def test_cgroup_exact_component(self):
        self.assertTrue(g.owned_cgroup('0::/system.slice/strata-deepseek-window.service\n'))
        self.assertFalse(g.owned_cgroup('0::/system.slice/strata-deepseek-window.service-foreign'))
    def test_paths_foreign(self):
        with self.assertRaises(ValueError):g.output_paths(pathlib.Path('/tmp/decode-iq2s-persistent-kernel-20261029T000000Z'))
    def test_paths_real_fresh(self):
        with tempfile.TemporaryDirectory() as d,patch.object(g,'E',pathlib.Path(d).resolve()):
            out=pathlib.Path(d).resolve()/'results/decode-iq2s-persistent-kernel-20261029T000000Z'
            out.parent.mkdir();(pathlib.Path(d).resolve()/'maintenance').mkdir()
            self.assertEqual(g.output_paths(out)[0],out)
    def test_existing_output_refused(self):
        with tempfile.TemporaryDirectory() as d,patch.object(g,'E',pathlib.Path(d).resolve()):
            out=pathlib.Path(d).resolve()/'results/decode-iq2s-persistent-kernel-20261029T000000Z';out.mkdir(parents=True);(g.E/'maintenance').mkdir()
            with self.assertRaises(ValueError):g.output_paths(out)
    def test_symlink_output_refused(self):
        with tempfile.TemporaryDirectory() as d,patch.object(g,'E',pathlib.Path(d).resolve()):
            out=pathlib.Path(d).resolve()/'results/decode-iq2s-persistent-kernel-20261029T000000Z';out.parent.mkdir();(g.E/'maintenance').mkdir();out.symlink_to('/not-present')
            with self.assertRaises(ValueError):g.output_paths(out)
    def test_fixture_contract_exact(self):
        with tempfile.TemporaryDirectory() as d,patch.object(g,'E',pathlib.Path(d).resolve()):
            (g.E/'results').mkdir();(g.E/'maintenance').mkdir()
            out=g.E/'results/decode-iq2s-persistent-kernel-20261029T000000Z'
            self.assertEqual(g.fixture_contract(g.P/'build-FIRST/ds4_gguf_test-candidate','a'*64,out,1)[1:],['--iq2s-persist-check','1'])
    def test_fixture_wrong_binary_refused(self):
        with patch.object(g,'output_paths',return_value=(pathlib.Path('/owned'),pathlib.Path('/meta'))):
            with self.assertRaises(ValueError):g.fixture_contract(pathlib.Path('/bin/true'),'a'*64,g.E/'results/decode-iq2s-persistent-kernel-20261029T000000Z',0)
    def test_fixture_bool_device_refused(self):
        with patch.object(g,'output_paths',return_value=(pathlib.Path('/owned'),pathlib.Path('/meta'))):
            with self.assertRaises(ValueError):g.fixture_contract(g.P/'build-FIRST/ds4_gguf_test-candidate','a'*64,g.E/'results/decode-iq2s-persistent-kernel-20261029T000000Z',True)

class FixturePhase(unittest.TestCase):
    def run_phase(self,mode='ok'):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d).resolve();p=root/'candidate';p.mkdir();out=root/'results/decode-iq2s-persistent-kernel-20261029T000000Z';out.parent.mkdir()
            binary=p/'build-FIRST/ds4_gguf_test-candidate';binary.parent.mkdir();binary.write_bytes(b'not executable; child mocked')
            meta=root/'maintenance'/out.name;meta.mkdir(parents=True)
            proof=meta/'proof.json';proof.write_text(json.dumps({'qualified_for_owned_iq2s_kernel':True,'output':str(out),'qualification_sha256':'a'*64}))
            (meta/'state.json').write_text(json.dumps({'status':'IQ2S_KERNEL_PRIVATE_RUNNING','output':str(out),'qualification_sha256':'a'*64}))
            (root/'STATE.json').write_text(json.dumps({'maintenance_controller':str(meta/'state.json'),'active_private_phase':str(meta)}))
            (p/'gpu-attempt.json').write_text(json.dumps({'metadata':str(meta),'output':str(out)}))
            q={'fixture_binary':str(binary),'fixture_sha256':g.sha(binary),'qualification_sha256':'a'*64}
            children=[]
            def popen(command,**kw):
                device=int(command[-1]);kw['stdout'].write(text(device).encode());kw['stdout'].flush()
                child=Mock(pid=100+device,returncode=0)
                child.wait.return_value=0;child.poll.return_value=0
                if mode in ['timeout','receipt_failure']:
                    child.returncode=None;child.wait.side_effect=[g.subprocess.TimeoutExpired(command,120),-15];child.poll.return_value=None
                if mode=='bad_exit':child.returncode=1;child.wait.return_value=1
                if mode=='bad_identity':child.returncode=None;child.poll.return_value=None;child.wait.return_value=-15
                if mode=='bad_text':kw['stdout'].write(b'FAIL canary\n');kw['stdout'].flush()
                children.append(child);return child
            if mode=='foreign_proof':proof=root/'foreign.json'
            if mode=='changed_qualification':q['qualification_sha256']='b'*64
            original=pathlib.Path.read_text
            def read(path,*args,**kw):
                if str(path)=='/proc/self/cgroup':return '0::/system.slice/strata-deepseek-window.service\n' if mode!='foreign_cgroup' else '0::/user.slice/foreign\n'
                return original(path,*args,**kw)
            fake=types.SimpleNamespace(owned_window=lambda:(root/'window.json',{}))
            identity=Mock(return_value={'pid':100,'cgroup':'owned','start_ticks':2})
            if mode=='bad_identity':identity.side_effect=ValueError('Wrong actual child')
            real_emit=g.emit
            def phase_emit(path,value):
                if mode=='receipt_failure' and path.name=='gpu0-exit.json':raise OSError('receipt failed')
                real_emit(path,value)
            def qualification(pin):
                if pin!=q['qualification_sha256']:raise ValueError('Qualification changed')
                return q
            with patch.object(g,'emit',side_effect=phase_emit),patch.object(g,'P',p),patch.object(g,'E',root),patch.object(g,'qualified',side_effect=qualification),patch.dict('sys.modules',native_worker=fake),patch.object(pathlib.Path,'read_text',read),patch.object(g.subprocess,'Popen',side_effect=popen),patch.object(g,'child_identity',identity):
                if mode=='ok':
                    self.assertEqual(g.fixture_phase(out,proof),0)
                    result=json.loads((out/'kernel-receipt.json').read_text());self.assertTrue(result['passed']);self.assertEqual(len(result['devices']),2)
                    self.assertEqual(len(children),2)
                else:
                    with self.assertRaises((ValueError,RuntimeError,g.subprocess.TimeoutExpired)) as failure:g.fixture_phase(out,proof)
                    if mode=='receipt_failure':self.assertIn('receipt failed',failure.exception.__notes__[0])
                    self.assertFalse((out/'kernel-receipt.json').exists())
                    if children and mode!='receipt_failure':self.assertTrue((out/'gpu0-exit.json').is_file())
                    self.assertLessEqual(len(children),1)
                    if mode in ['timeout','bad_identity','receipt_failure']:children[0].terminate.assert_called_once()
    def test_two_device_terminal_success(self):self.run_phase()
    def test_first_nonzero_blocks_second(self):self.run_phase('bad_exit')
    def test_first_bad_text_blocks_second(self):self.run_phase('bad_text')
    def test_timeout_owned_child_cleanup_no_retry(self):self.run_phase('timeout')
    def test_actual_identity_fault_owned_cleanup(self):self.run_phase('bad_identity')
    def test_foreign_cgroup_no_child(self):self.run_phase('foreign_cgroup')
    def test_foreign_proof_path_no_read_or_child(self):self.run_phase('foreign_proof')
    def test_changed_qualification_no_child(self):self.run_phase('changed_qualification')
    def test_exit_receipt_fault_preserves_timeout(self):self.run_phase('receipt_failure')

class ActualIdentity(unittest.TestCase):
    def check(self,mode):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d).resolve();binary=root/'fixture';binary.write_bytes(b'fixture');proc=root/'123';proc.mkdir();(proc/'exe').symlink_to(binary)
            command=[str(binary),'--iq2s-persist-check','0']
            (proc/'cmdline').write_bytes(('\x00'.join(command)+'\x00').encode())
            (proc/'cgroup').write_text('0::/system.slice/strata-deepseek-window.service\n')
            (proc/'stat').write_text('123 (fixture name) '+ ' '.join(['S']+['0']*18+['987']))
            if mode=='argv':(proc/'cmdline').write_bytes(b'foreign\x00')
            if mode=='group':(proc/'cgroup').write_text('0::/foreign')
            if mode=='exe':(proc/'exe').unlink();(proc/'exe').symlink_to('/bin/sh')
            if mode=='ok':self.assertEqual(g.child_identity(123,binary,command,root)['start_ticks'],987)
            else:
                with self.assertRaises(ValueError):g.child_identity(123,binary,command,root)
    def test_pid_exe_argv_cgroup_ticks(self):self.check('ok')
    def test_foreign_executable(self):self.check('exe')
    def test_foreign_argv(self):self.check('argv')
    def test_foreign_cgroup(self):self.check('group')

class Pending(unittest.TestCase):
    def pending(self,mode):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d).resolve();meta=root/'maintenance/decode-iq2s-persistent-kernel-20261029T000000Z';meta.mkdir(parents=True)
            value={'status':'IQ2S_KERNEL_SELECTED_RUNNING_PUBLIC_VERIFY_PENDING','start_binding':BIND,'kernel_since':'2026-10-29 00:00:00 UTC','qualification_sha256':'a'*64}
            current={'production_verification_pending':str(meta/'state.json'),'maintenance_controller':str(meta/'state.json')}
            if mode=='foreign':current['maintenance_controller']='foreign'
            if mode=='phase':current['active_gpu_experiment']=True
            (meta/'state.json').write_text(json.dumps(value));(root/'STATE.json').write_text(json.dumps(current))
            host=Mock();host.idle.return_value=mode!='busy';host.start_command_cleanup_error=None
            host.verify_target.return_value={'passed':True,'selected_identity':{'native_pid':11,'start_binding':BIND}}
            if mode=='race':host.verify_target.return_value={'pending_public_probe':True}
            if mode=='public_fault':host.verify_target.side_effect=ValueError('public fault')
            if mode=='changed_custody':
                def change(expected_pid):
                    foreign=dict(current,maintenance_controller='foreign')
                    (root/'STATE.json').write_text(json.dumps(foreign))
                    return {'passed':True,'selected_identity':{'native_pid':11,'start_binding':BIND}}
                host.verify_target.side_effect=change
            a=types.SimpleNamespace(real_ancestors=lambda p:None)
            with patch.object(g,'E',root),patch.object(g,'qualified',side_effect=ValueError('qualification changed') if mode=='q_changed' else None,return_value={}),patch.object(g,'host_class',return_value=lambda:host):
                if mode=='q_changed':
                    before=(root/'STATE.json').read_bytes()
                    with self.assertRaises(ValueError):g.verify_pending(a,meta)
                    host.verify_target.assert_not_called();host.cleanup_owned_target.assert_not_called()
                    self.assertEqual((root/'STATE.json').read_bytes(),before)
                elif mode in ['public_fault','changed_custody']:
                    with self.assertRaises(ValueError):g.verify_pending(a,meta)
                    if mode=='public_fault':host.cleanup_owned_target.assert_called_once_with(11)
                    else:
                        host.cleanup_owned_target.assert_not_called()
                        self.assertEqual(json.loads((root/'STATE.json').read_text())['maintenance_controller'],'foreign')
                elif mode in ['foreign','phase']:
                    with self.assertRaises(ValueError):g.verify_pending(a,meta)
                    host.guard_binding.assert_not_called();host.verify_target.assert_not_called()
                else:
                    result=g.verify_pending(a,meta)
                    if mode in ['busy','race']:
                        self.assertEqual(result['status'],'DEFERRED_BUSY_UNTOUCHED');self.assertEqual(json.loads((meta/'state.json').read_text()),value)
                    else:
                        self.assertEqual(result['status'],'IQ2S_KERNEL_COMPLETE_SELECTED4096_RESTORED')
                        self.assertFalse(json.loads((root/'STATE.json').read_text())['production_verification_pending'])
                    host.restore_ds.assert_not_called();host.launch.assert_not_called()
    def test_pending_success_no_restart(self):self.pending('ok')
    def test_pending_busy_no_queued_generation(self):self.pending('busy')
    def test_pending_race_stays_pending(self):self.pending('race')
    def test_foreign_controller_preserved(self):self.pending('foreign')
    def test_other_phase_preserved(self):self.pending('phase')
    def test_public_failure_cleans_only_bound_owner(self):self.pending('public_fault')
    def test_changed_controller_after_probe_is_not_stopped_or_overwritten(self):self.pending('changed_custody')
    def test_changed_qualification_blocks_probe_without_restart_or_cleanup(self):self.pending('q_changed')

def canonical_coordinate():
    # Run the exact reviewed existing coordinate body with scripted host/backends only.
    path=pathlib.Path(__file__).resolve().parents[2]/'decode-profile-v1/maintenance.py'
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!='276a78f6f62d9ae7760e9b436863a6279715d58ea0960bb396bdb7adcc3776dd':raise ValueError('Canonical coordinate changed')
    node=next(n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name=='coordinate')
    namespace={'AdmissionDeferred':type('AdmissionDeferred',(RuntimeError,),{}),'pathlib':pathlib,
               'emit':g.emit,'time':types.SimpleNamespace(sleep=lambda _:None)}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),namespace)
    return namespace['coordinate'],namespace['AdmissionDeferred']

class CanonicalLifecycle(unittest.TestCase):
    def run_case(self,mode):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d).resolve();p=root/'candidate';p.mkdir();out=root/'results/decode-iq2s-persistent-kernel-20261029T000000Z'
            out.parent.mkdir();meta=root/'maintenance'/out.name;meta.mkdir(parents=True)
            current={'chunk4096_activation':{'selected_identity':{'native_pid':11,'start_binding':BIND}},'keep':'unchanged'}
            (root/'STATE.json').write_text(json.dumps(current));before=(root/'STATE.json').read_bytes()
            coordinate,deferred=canonical_coordinate();a=types.SimpleNamespace(m=types.SimpleNamespace(old=types.SimpleNamespace(coordinate=coordinate)))
            host=Mock();host.baseline_binding=BIND;host.start_binding=None;host.restored_pid=None;host.since='2026-10-29 00:00:00 UTC';host.start_command_cleanup_error=None
            host.preflight.return_value={'qualified_for_owned_iq2s_kernel':True,'output':str(out),'qualification_sha256':'a'*64}
            host.previous.return_value=root/'prior.json';host.native_pid.return_value=11;host.idle.return_value=True
            host.launch.return_value='owned-window'
            restored=dict(BIND,native_pid=21,main_pid=20)
            def restore():
                host.restored_pid=21;host.start_binding=restored
                if mode=='partial_restore':
                    host.start_command_cleanup_error='systemctl cleanup fault';raise ValueError('start failed')
            host.restore_ds.side_effect=restore
            host.verify.return_value={'passed':True,'selected_identity':{'native_pid':21,'start_binding':restored}}
            if mode=='pending':host.verify.return_value={'pending_public_probe':True,'selected_identity':{'native_pid':21,'start_binding':restored}}
            if mode in ['public_fault','cleanup_fault']:host.verify.side_effect=ValueError('public failed')
            if mode=='cleanup_fault':host.cleanup_owned_target.side_effect=ValueError('cleanup failed')
            if mode=='busy':host.idle.return_value=False
            if mode=='preflight_defer':host.preflight.side_effect=deferred('busy')
            if mode=='foreign_before_drain':
                def idle():
                    state=json.loads((root/'STATE.json').read_text());state['active_private_phase']='foreign'
                    (root/'STATE.json').write_text(json.dumps(state));return True
                host.idle.side_effect=idle
            state={'utc':host.since,'output':str(out),'proof_path':str(meta/'proof.json'),'qualification_sha256':'a'*64,
                   'running_status':'IQ2S_KERNEL_PRIVATE_RUNNING','complete_status':'IQ2S_KERNEL_COMPLETE_SELECTED4096_RESTORED'}
            with patch.object(g,'E',root),patch.object(g,'P',p):
                save=g.make_saver(host,meta,run=mode!='readonly')
                if mode in ['partial_restore','public_fault','cleanup_fault','foreign_before_drain']:
                    with self.assertRaises(ValueError):g.coordinate_kernel(a,host,out,state,save,root_free=lambda:140*2**30)
                    if mode=='foreign_before_drain':
                        host.stop_router.assert_not_called();host.cleanup_owned_target.assert_not_called()
                        self.assertEqual(json.loads((root/'STATE.json').read_text())['active_private_phase'],'foreign')
                    else:
                        host.cleanup_owned_target.assert_called_once_with(21)
                        saved=json.loads((meta/'state.json').read_text());self.assertEqual(saved['status'],'STOPPED_FOR_OFFLINE_DIAGNOSIS')
                        if mode=='partial_restore':self.assertEqual(saved['start_command_cleanup_error'],'systemctl cleanup fault')
                        if mode=='cleanup_fault':
                            self.assertIn('public failed',saved['error']);self.assertIn('cleanup failed',saved['cleanup_error'])
                else:
                    result=g.coordinate_kernel(a,host,out,state,save,preflight_only=mode=='readonly',root_free=lambda:140*2**30)
                    if mode in ['readonly','busy','preflight_defer']:
                        self.assertEqual((root/'STATE.json').read_bytes(),before);host.stop_router.assert_not_called();host.launch.assert_not_called()
                    else:
                        self.assertEqual(result['status'],'IQ2S_KERNEL_SELECTED_RUNNING_PUBLIC_VERIFY_PENDING')
                        self.assertEqual(json.loads((meta/'state.json').read_text())['status'],result['status'])
                        self.assertEqual(json.loads((root/'STATE.json').read_text())['production_verification_pending'],str(meta/'state.json'))
                        self.assertEqual(result['resume_terminal_status'],'IQ2S_KERNEL_COMPLETE_SELECTED4096_RESTORED')
    def test_actual_canonical_readonly_preserves_global_identity(self):self.run_case('readonly')
    def test_actual_canonical_late_busy_preserves_global_identity(self):self.run_case('busy')
    def test_actual_canonical_preflight_defer_preserves_global_identity(self):self.run_case('preflight_defer')
    def test_actual_canonical_pending_normalizes_return_and_saved_state(self):self.run_case('pending')
    def test_actual_canonical_partial_start_cleans_only_bound_restored_owner(self):self.run_case('partial_restore')
    def test_actual_canonical_public_fault_cleans_only_bound_restored_owner(self):self.run_case('public_fault')
    def test_actual_canonical_foreign_claim_blocks_before_drain(self):self.run_case('foreign_before_drain')
    def test_actual_canonical_cleanup_fault_preserves_primary_and_secondary(self):self.run_case('cleanup_fault')

class QualificationAndPaths(unittest.TestCase):
    def test_changed_qualification_refused_before_json_or_artifact_access(self):
        with tempfile.TemporaryDirectory() as d,patch.object(g,'P',pathlib.Path(d).resolve()):
            (g.P/'gpu-qualification.json').write_text('not JSON; changed')
            with patch.object(g.json,'loads') as parse:
                with self.assertRaises(ValueError):g.qualified('a'*64)
            parse.assert_not_called()
    def qualification(self,missing=None,bad_child=None):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d).resolve();p=root/'p';p.mkdir();r=root/'r';r.mkdir();e=root/'e';e.mkdir()
            window=r/'window.py';window.write_text('window')
            coordinate=e/'decode-profile-v1/maintenance.py';coordinate.parent.mkdir();coordinate.write_text('coordinate')
            paths=[window,coordinate,p/'qualify_iq2s_gpu_cpu.py',p/'iq2s_gpu_check.py',p/'test_iq2s_gpu_check.py',p/'build-FIRST/ds4_gguf_test-candidate']
            for path in paths[2:]:path.parent.mkdir(exist_ok=True);path.write_text('fixture '+path.name)
            sources={name:g.sha(p/name) for name in ['iq2s_gpu_check.py','test_iq2s_gpu_check.py']}
            for host in ['darwin','linux']:
                directory=p/('gpu-CPU-'+host);directory.mkdir()
                proof={'passed':True,'source_sha256':sources,'test_ids':['one'],'controls':1,'GPU_execution':False,'native_execution':False}
                child={'returncode':0,'CPU_s':30,'wall_s':90,'nice':15,'CUDA_hidden':True,
                       'Linux_AS_MiB':512 if host=='linux' else None,'error':None,'cleanup_errors':[]}
                if bad_child and host=='linux':child.update(bad_child)
                (directory/'receipt.json').write_text(json.dumps(proof));(directory/'child.json').write_text(json.dumps(child));(directory/'child.log').write_text('raw')
                paths += [directory/name for name in ['receipt.json','child.json','child.log']]
            q={'source_manually_reviewed':True,'CPU_both_hosts_passed':True,'source_sha256':sources,'test_ids':['one'],
               'fixture_binary':str(p/'build-FIRST/ds4_gguf_test-candidate'),'fixture_sha256':g.sha(p/'build-FIRST/ds4_gguf_test-candidate'),
               'files':{str(path):g.sha(path) for path in paths}}
            if missing is not None:del q['files'][str(p/missing)]
            file=p/'gpu-qualification.json';file.write_text(json.dumps(q));digest=g.sha(file)
            with patch.object(g,'P',p),patch.object(g,'R',r),patch.object(g,'E',e),patch.object(g,'WINDOW_SHA',g.sha(window)),patch.object(g,'COORDINATE_SHA',g.sha(coordinate)):
                if missing is None and bad_child is None:self.assertEqual(g.qualified(digest)['qualification_sha256'],digest)
                else:
                    with self.assertRaises(ValueError):g.qualified(digest)
    def test_complete_exact_qualification_and_CPU_proofs(self):self.qualification()
    def test_missing_CPU_raw_log_pin_refused(self):self.qualification('gpu-CPU-linux/child.log')
    def test_missing_driver_pin_refused(self):self.qualification('qualify_iq2s_gpu_cpu.py')
    def test_failed_CPU_child_refused(self):self.qualification(bad_child={'returncode':1})
    def test_boolean_CPU_exit_refused(self):self.qualification(bad_child={'returncode':False})
    def test_CPU_time_bound_required(self):self.qualification(bad_child={'CPU_s':31})
    def test_wall_bound_required(self):self.qualification(bad_child={'wall_s':91})
    def test_Linux_AS_bound_required(self):self.qualification(bad_child={'Linux_AS_MiB':513})
    def test_CUDA_hidden_required(self):self.qualification(bad_child={'CUDA_hidden':False})
    def test_CPU_supervision_error_refused(self):self.qualification(bad_child={'error':'timeout'})
    def test_CPU_cleanup_error_refused(self):self.qualification(bad_child={'cleanup_errors':['still alive']})
    def test_symlink_ancestor_refused_before_descendant_stat(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d).resolve();real=root/'real';real.mkdir();alias=root/'alias';alias.symlink_to(real)
            touched=[];original=pathlib.Path.is_dir
            def inspect(path):touched.append(path);return original(path)
            with patch.object(pathlib.Path,'is_dir',inspect):
                with self.assertRaises(ValueError):g.real_directory(alias/'descendant')
            self.assertNotIn(alias/'descendant',touched)
    def test_existing_metadata_refused_for_new_action(self):
        with tempfile.TemporaryDirectory() as d,patch.object(g,'E',pathlib.Path(d).resolve()):
            (g.E/'results').mkdir();meta=g.E/'maintenance/decode-iq2s-persistent-kernel-20261029T000000Z';meta.mkdir(parents=True)
            with self.assertRaises(ValueError):g.output_paths(g.E/'results'/meta.name,metadata_state='absent')
    def test_pending_state_symlink_refused_before_read(self):
        with tempfile.TemporaryDirectory() as d,patch.object(g,'E',pathlib.Path(d).resolve()):
            meta=g.E/'maintenance/decode-iq2s-persistent-kernel-20261029T000000Z';meta.mkdir(parents=True)
            (meta/'state.json').symlink_to('/absent')
            with self.assertRaises(ValueError):g.pending_paths(meta)

if __name__=='__main__':unittest.main()
