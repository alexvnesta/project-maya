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
if __name__=='__main__':unittest.main()
