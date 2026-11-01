"""Real small temporary files: protect selection, aliases, drift and durable intent.
No serving imports, payload reads, real model deletion or native/GPU operations.
"""
from pathlib import Path
import copy,json,os,tempfile,unittest
from unittest.mock import patch
import remove_exact_payloads_admitted as c
class Removal(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.p=self.root/'payload.gguf';self.p.write_bytes(b'public synthetic bytes')
        self.row={'path':str(self.p),'signature':c.signature(self.p.stat()),'previously_verified_sha256':'a'*64}
    def test_exact_file_removed_with_other_files_untouched(self):
        other=self.root/'selected.gguf';other.write_bytes(b'selected');events=[]
        answer=c.unlink_record(self.row,{(other.stat().st_dev,other.stat().st_ino)},events.append)
        self.assertFalse(self.p.exists());self.assertEqual(other.read_bytes(),b'selected');self.assertEqual(answer['bytes'],22);self.assertEqual(events[0]['stage'],'INTENT')
    def test_protected_inode_refused_and_retained(self):
        t=self.p.stat()
        with self.assertRaises(ValueError):c.unlink_record(self.row,{(t.st_dev,t.st_ino)},lambda x:None)
        self.assertTrue(self.p.exists())
    def test_changed_size_refused(self):
        self.p.write_bytes(b'changed')
        with self.assertRaises(ValueError):c.unlink_record(self.row,set(),lambda x:None)
        self.assertEqual(self.p.read_bytes(),b'changed')
    def test_same_size_replacement_inode_refused(self):
        q=self.root/'replacement';q.write_bytes(self.p.read_bytes());q.replace(self.p)
        with self.assertRaises(ValueError):c.unlink_record(self.row,set(),lambda x:None)
        self.assertTrue(self.p.exists())
    def test_hardlink_refused_without_deleting_either_name(self):
        q=self.root/'shared';os.link(self.p,q)
        with self.assertRaises(ValueError):c.unlink_record(self.row,set(),lambda x:None)
        self.assertTrue(self.p.exists());self.assertTrue(q.exists())
    def test_symlink_leaf_refused_target_retained(self):
        q=self.root/'alias';q.symlink_to(self.p);self.row['path']=str(q)
        with self.assertRaises(ValueError):c.unlink_record(self.row,set(),lambda x:None)
        self.assertTrue(self.p.exists());self.assertTrue(q.is_symlink())
    def test_symlink_parent_refused(self):
        q=self.root/'alias';q.symlink_to(self.root,target_is_directory=True);self.row['path']=str(q/self.p.name)
        with self.assertRaises(ValueError):c.unlink_record(self.row,set(),lambda x:None)
        self.assertTrue(self.p.exists())
    def test_missing_leaf_is_not_silent_success(self):
        self.p.unlink()
        with self.assertRaises(FileNotFoundError):c.unlink_record(self.row,set(),lambda x:None)
    def test_foreign_owner_refused(self):
        with patch.object(c.os,'getuid',return_value=os.getuid()+1):
            with self.assertRaises(ValueError):c.unlink_record(self.row,set(),lambda x:None)
        self.assertTrue(self.p.exists())
    def test_durable_intent_failure_keeps_payload(self):
        def fail(_):raise OSError('synthetic fsync failure')
        with self.assertRaises(OSError):c.unlink_record(self.row,set(),fail)
        self.assertTrue(self.p.exists())
    def test_replacement_during_intent_never_unlinked(self):
        def replace(_):
            q=self.root/'other';q.write_bytes(b'new protected bytes');q.replace(self.p)
        with self.assertRaises(ValueError):c.unlink_record(self.row,set(),replace)
        self.assertEqual(self.p.read_bytes(),b'new protected bytes')
    def test_signature_drift_refused_before_intent(self):
        for key in ['dev','ino','mtime_ns','ctime_ns','mode','uid','allocated_bytes']:
            row=copy.deepcopy(self.row);row['signature'][key]+=1;events=[]
            with self.subTest(key=key),self.assertRaises(ValueError):c.unlink_record(row,set(),events.append)
            self.assertEqual(events,[]);self.assertTrue(self.p.exists())
    def test_allowlist_is_only_fifteen_named_payloads(self):
        paths=c.expected_paths(Path('/synthetic'));self.assertEqual(len(paths),15)
        self.assertEqual(sum(p.suffix=='.gguf' for p in paths),12);self.assertEqual(sum(p.suffix=='.safetensors' for p in paths),2)
        self.assertTrue(all('cache' not in p.parts and 'pack-native-vision-v1' not in p.parts and 'dspark.bin'!=p.name and 'vision.bin'!=p.name for p in paths))
    def test_actual_frozen_plan_exact_path_names_and_byte_total(self):
        plan=json.loads((Path(__file__).resolve().parent/'CLEANUP_PLAN.json').read_text())
        self.assertEqual({Path(row['path']) for row in plan['rows']},c.expected_paths(Path(plan['root_scope'])))
        self.assertEqual(plan['count'],15);self.assertEqual(sum(row['signature']['size'] for row in plan['rows']),664358869199)
        protected={(row['dev'],row['ino']) for row in plan['protected_dependencies'].values()}
        self.assertTrue(all((row['signature']['dev'],row['signature']['ino']) not in protected for row in plan['rows']))
    def test_exclusive_attempt_refuses_second_owner_without_overwrite(self):
        marker=self.root/'attempt.json';first={'pid':1,'run':'first'};c.exclusive_attempt(marker,first)
        with self.assertRaises(FileExistsError):c.exclusive_attempt(marker,{'pid':2})
        self.assertEqual(json.loads(marker.read_text()),first)
    def test_exclusive_attempt_refuses_symlink_and_preserves_target(self):
        marker=self.root/'attempt.json';marker.symlink_to(self.p)
        with self.assertRaises(FileExistsError):c.exclusive_attempt(marker,{'pid':2})
        self.assertEqual(self.p.read_bytes(),b'public synthetic bytes')
    def test_postunlink_directory_fsync_fault_still_counts_actual_unlink(self):
        observed=[]
        with patch.object(c.os,'fsync',side_effect=OSError('synthetic post-unlink durability fault')):
            with self.assertRaises(OSError):c.unlink_record(self.row,set(),lambda x:None,observed.append)
        self.assertFalse(self.p.exists());self.assertEqual(len(observed),1)
        self.assertTrue(observed[0]['unlink_returned_success']);self.assertFalse(observed[0]['parent_fsync_passed']);self.assertFalse(observed[0]['postcheck_passed'])
    def test_postunlink_log_failure_still_counts_actual_unlink(self):
        observed=[]
        def fail(value):observed.append(value);raise OSError('synthetic postunlink progress fault')
        with self.assertRaises(OSError):c.unlink_record(self.row,set(),lambda x:None,fail)
        self.assertFalse(self.p.exists());self.assertEqual(len(observed),1);self.assertTrue(observed[0]['unlink_returned_success'])
    def test_postunlink_replacement_is_preserved_and_original_unlink_counted(self):
        observed=[]
        def replace(value):observed.append(value);self.p.write_bytes(b'new foreign replacement')
        with self.assertRaises(ValueError):c.unlink_record(self.row,set(),lambda x:None,replace)
        self.assertEqual(self.p.read_bytes(),b'new foreign replacement');self.assertEqual(len(observed),1)
        self.assertTrue(observed[0]['unlink_returned_success']);self.assertFalse(observed[0]['postcheck_passed'])
    def test_exact_claim_rejects_foreign_owner_binding_or_other_phase(self):
        import types
        e=self.root/'state';e.mkdir();claim={'pid':31,'plan':'fixed'};binding={'native_pid':72}
        state={'active_cpu_build':claim,'binding':binding}
        r=types.SimpleNamespace(PHASE_KEYS=('active_cpu_build','active_private_phase'),selected_binding=lambda d:d['binding'])
        with patch.object(c,'E',e):
            (e/'STATE.json').write_text(json.dumps(state));self.assertEqual(c.owned_claim_guard(r,binding,claim),state)
            for change in [{'active_cpu_build':{'pid':32}},{'binding':{'native_pid':73}},{'active_private_phase':'foreign'}]:
                bad={**state,**change};(e/'STATE.json').write_text(json.dumps(bad))
                with self.subTest(change=change),self.assertRaises(ValueError):c.owned_claim_guard(r,binding,claim)
    def lock_sample(self):
        dev=os.makedev(252,1);return dev,1449998,1166336,'8: FLOCK ADVISORY WRITE 1166336 fc:01:1449998 0 EOF'
    def test_exact_saved_selected_host_lock_record_accepted(self):
        dev,ino,pid,raw=self.lock_sample();v=c.lock_contract(raw,dev,ino,pid)
        self.assertEqual(v['holder_pid'],pid);self.assertTrue(v['whole_file_exclusive_flock'])
    def test_foreign_or_untyped_lock_owner_refused(self):
        dev,ino,pid,raw=self.lock_sample()
        for wrong in [pid+1,True,0,-1]:
            with self.subTest(wrong=wrong),self.assertRaises(ValueError):c.lock_contract(raw,dev,ino,wrong)
    def test_missing_or_different_device_inode_lock_refused(self):
        dev,ino,pid,raw=self.lock_sample()
        for value in ['',raw.replace('fc:01','fb:01'),raw.replace(':1449998',':1449999')]:
            with self.subTest(raw=value),self.assertRaises(ValueError):c.lock_contract(value,dev,ino,pid)
    def test_shared_POSIX_OFD_or_partial_lock_refused(self):
        dev,ino,pid,raw=self.lock_sample()
        for value in [raw.replace('WRITE','READ'),raw.replace('FLOCK','POSIX'),raw.replace('FLOCK ADVISORY WRITE 1166336','OFDLCK ADVISORY WRITE -1'),raw.replace('0 EOF','1 EOF'),raw.replace('0 EOF','0 99')]:
            with self.subTest(raw=value),self.assertRaises(ValueError):c.lock_contract(value,dev,ino,pid)
    def test_duplicate_or_blocked_waiter_lock_refused(self):
        dev,ino,pid,raw=self.lock_sample()
        for value in [raw+'\n'+raw,raw.replace('8: FLOCK','8: -> FLOCK')]:
            with self.subTest(raw=value),self.assertRaises(ValueError):c.lock_contract(value,dev,ino,pid)
    def test_exact_fdinfo_lock_witness_required(self):
        dev,ino,pid,raw=self.lock_sample();fdinfo='pos: 0\nflags: 0100000\nino: 1449998\nlock: '+raw+'\n'
        self.assertEqual(c.fdinfo_contract(fdinfo,dev,ino,pid)['holder_pid'],pid)
        for value in [fdinfo.replace('ino: 1449998','ino: 1449999'),fdinfo.split('lock:')[0],fdinfo.replace('1166336','1166337')]:
            with self.subTest(raw=value),self.assertRaises(ValueError):c.fdinfo_contract(value,dev,ino,pid)
    def test_closing_unlocked_fd_never_releases_existing_holder_flock(self):
        import fcntl
        with self.p.open('r') as holder:
            fcntl.flock(holder,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.p.open('r') as second:
                with self.assertRaises(BlockingIOError):fcntl.flock(second,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.p.open('r') as third:
                with self.assertRaises(BlockingIOError):fcntl.flock(third,fcntl.LOCK_EX|fcntl.LOCK_NB)
                fcntl.flock(holder,fcntl.LOCK_UN);fcntl.flock(third,fcntl.LOCK_EX|fcntl.LOCK_NB)
    def test_bound_observer_sets_real_receipt_sink_before_identity_call(self):
        import types
        class Host:
            def target_identity(self):
                (self.audit_dir/'target-placement.json').open('x').write(json.dumps({'binding':self.start_binding}))
                return {'start_binding':dict(self.start_binding)}
        binding={'invocation':'a'*32,'main_pid':71,'native_pid':72,'native_start_ticks':73}
        h=c.bound_observer(types.SimpleNamespace(ChunkProductionHost=Host),binding,self.root)
        self.assertEqual(h.target_identity()['start_binding'],binding);self.assertTrue((self.root/'target-placement.json').is_file())
    def test_bound_observer_refuses_missing_or_aliased_receipt_sink(self):
        import types
        from unittest.mock import Mock
        alias=self.root/'alias';alias.symlink_to(self.root,target_is_directory=True);factory=Mock()
        for path in [self.root/'absent',alias]:
            with self.subTest(path=path),self.assertRaises(ValueError):c.bound_observer(types.SimpleNamespace(ChunkProductionHost=factory),{'native_pid':72},path)
        factory.assert_not_called()
    def test_bound_observer_freezes_binding_copy(self):
        import types
        binding={'native_pid':72};h=c.bound_observer(types.SimpleNamespace(ChunkProductionHost=types.SimpleNamespace),binding,self.root)
        binding['native_pid']=73;self.assertEqual(h.start_binding,{'native_pid':72});self.assertEqual(h.audit_dir,self.root)
if __name__=='__main__':unittest.main()
