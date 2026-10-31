"""Synthetic new-scope acquisition checks; no real download, model or service."""
import copy
import ast
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock,patch
import acquire_native as n

def original():
    spec=importlib.util.spec_from_file_location('_hybrid_transfer_cpu_only',n.TRANSPORT/'acquire.py')
    a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a);return a

class Pure(unittest.TestCase):
    def test_exact_two_source_shards_and_scope(self):
        m=n.manifest();self.assertEqual(len(m['files']),2);self.assertEqual(sum(r['size'] for r in m['files']),n.TOTAL);self.assertFalse(m['exact_private_S2']);self.assertEqual(m['selected_layers'],[25,26])
    def test_floor_both_downloads_and_overlay_reserved(self):
        wanted=n.FLOOR+n.CUSHION+n.OVERLAY_BYTES+n.TOTAL+n.OTHER_TOTAL
        self.assertEqual(n.budget(wanted,0,0)['required'],wanted)
        with self.assertRaises(ValueError):n.budget(wanted-1,0,0)
    def test_progress_preserves_combined_headroom(self):
        free=10**15;a=n.budget(free,0,0);b=n.budget(free-300,100,200);self.assertEqual(a['free']-a['required'],b['free']-b['required'])
    def test_completed_downloads_still_reserve_future_overlay(self):
        wanted=n.FLOOR+n.CUSHION+n.OVERLAY_BYTES;self.assertEqual(n.budget(wanted,n.TOTAL,n.OTHER_TOTAL)['required'],wanted)
    def test_typed_counters_refuse_bool_negative_and_overflow(self):
        for args in [(True,0,0),(10**15,-1,0),(10**15,n.TOTAL+1,0),(10**15,0,n.OTHER_TOTAL+1)]:
            with self.assertRaises(ValueError):n.budget(*args)
    def test_changed_manifest_or_transport_refused_before_import(self):
        with patch.object(n,'sha',return_value='bad'),patch.object(n.importlib.util,'spec_from_file_location') as load:
            with self.assertRaises(ValueError):n.manifest()
            with self.assertRaises(ValueError):n.transport()
        load.assert_not_called()
    def test_explicit_qualification_pin_before_parse(self):
        with patch.object(n,'sha',return_value='bad'):
            with self.assertRaises(ValueError):n.qualified('expected')

class Inventory(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.a=original();self.spec=[{'path':'a.safetensors','size':10}]
    def test_missing_and_partial_and_final(self):
        absent=self.root/'absent';self.assertEqual(n.retained_flat(absent,self.spec,self.a),0)
        p=self.root/'a.safetensors.partial';p.write_bytes(b'1234');self.assertEqual(n.retained_flat(self.root,self.spec,self.a),4);p.rename(self.root/'a.safetensors');self.assertEqual(n.retained_flat(self.root,self.spec,self.a),4)
    def test_foreign_or_oversized_leaf_refused(self):
        p=self.root/'other';p.write_bytes(b'x')
        with self.assertRaises(ValueError):n.retained_flat(self.root,self.spec,self.a)
        p.rename(self.root/'a.safetensors');(self.root/'a.safetensors').write_bytes(b'x'*11)
        with self.assertRaises(ValueError):n.retained_flat(self.root,self.spec,self.a)
    def test_own_alias_and_ambiguous_publish_refused(self):
        p=self.root/'a.safetensors';p.symlink_to('/nonexistent')
        with self.assertRaises(ValueError):n.retained_flat(self.root,self.spec,self.a)
        p.unlink();p.write_bytes(b'1234');(self.root/'a.safetensors.partial').write_bytes(b'1234')
        with self.assertRaises(ValueError):n.retained_flat(self.root,self.spec,self.a)
    def test_concurrent_other_link_publish_counted_once(self):
        p=self.root/'b';p.mkdir();partial=p/'x.partial';partial.write_bytes(b'1234');(p/'x').hardlink_to(partial)
        self.assertEqual(n.concurrent_other(self.root,[{'path':'b/x','size':10}]),4)
    def test_other_ambiguous_or_parent_alias_refused(self):
        p=self.root/'b';p.mkdir();(p/'x').write_bytes(b'1');(p/'x.partial').write_bytes(b'2')
        with self.assertRaises(ValueError):n.concurrent_other(self.root,[{'path':'b/x','size':10}])
        (self.root/'alias').symlink_to(p,target_is_directory=True)
        with self.assertRaises(ValueError):n.concurrent_other(self.root,[{'path':'alias/x','size':10}])

class Transfer(unittest.TestCase):
    def setUp(self):
        self.a=original();self.a.REPO=n.REPO;self.a.REVISION=n.REVISION;self.a.RATE=n.RATE;self.a.RESERVE=n.FLOOR
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.body=b'original native codes and scales';self.asset={'path':'model-00028-of-00048.safetensors','size':len(self.body),'sha256':hashlib.sha256(self.body).hexdigest()};self.calls=[]
    def open(self,request,timeout):
        self.calls.append((request.full_url,timeout))
        class Response(io.BytesIO):status=206
        r=Response(self.body);r.headers={'Content-Length':str(len(self.body)),'Content-Range':'bytes 0-%d/%d'%(len(self.body)-1,len(self.body))};return r
    def test_complete_official_url_exact_bytes_hash_and_publication(self):
        r=self.a.acquire_file(self.asset,self.root,lambda:None,opener=self.open,free=lambda:10**15)
        self.assertEqual(r['status'],'DOWNLOADED_VERIFIED');self.assertEqual((self.root/self.asset['path']).read_bytes(),self.body);self.assertIn('/'+n.REPO+'/resolve/'+n.REVISION+'/',self.calls[0][0]);self.assertEqual(self.calls[0][1],5)
    def test_corrupt_bytes_not_published(self):
        asset={**self.asset,'sha256':'0'*64}
        with self.assertRaises(ValueError):self.a.acquire_file(asset,self.root,lambda:None,opener=self.open,free=lambda:10**15)
        self.assertFalse((self.root/asset['path']).exists());self.assertTrue((self.root/(asset['path']+'.partial')).exists());self.assertEqual(len(self.calls),1)
    def test_transport_fault_no_automatic_retry(self):
        opener=Mock(side_effect=TimeoutError('synthetic'))
        with self.assertRaises(TimeoutError):self.a.acquire_file(self.asset,self.root,lambda:None,opener=opener,free=lambda:10**15)
        self.assertEqual(opener.call_count,1)

class Gate(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.other=self.root/'other';self.other.mkdir()
        (self.other/'ASSET_MANIFEST.json').write_bytes((n.UNSLOTH/'ASSET_MANIFEST.json').read_bytes())
        self.a=original();self.a.SelectedGate=Mock(return_value=Mock())
        for p in [patch.object(n,'HERE',self.root),patch.object(n,'UNSLOTH',self.other),patch.object(n.shutil,'disk_usage',return_value=types.SimpleNamespace(free=10**15))]:p.start();self.addCleanup(p.stop)
    def test_selected_rechecked_and_no_assets_created_by_guard(self):
        g=n.Gate(self.a,{'files':[]});g();self.assertEqual(g.selected.call_count,2);self.assertFalse((self.root/'assets').exists())
    def test_owned_pause_defers(self):
        g=n.Gate(self.a,{'files':[]});(self.root/'pause-for-comparison.json').write_text(json.dumps({'manifest_sha256':n.MANIFEST_SHA,'pause_before_private_phase':True}))
        with self.assertRaises(self.a.Deferred):g()
    def test_foreign_pause_or_insufficient_budget_refused(self):
        g=n.Gate(self.a,{'files':[]});p=self.root/'pause-for-comparison.json';p.write_text('{}')
        with self.assertRaises(ValueError):g()
        p.unlink()
        with patch.object(n.shutil,'disk_usage',return_value=types.SimpleNamespace(free=n.FLOOR)):
            with self.assertRaises(ValueError):g()

class Main(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.a=original();self.a.acquire_file=Mock(return_value={'status':'DOWNLOADED_VERIFIED','bytes':1,'sha256':'0'*64});self.binding={'native_pid':7};self.g=Mock();self.g.selected.host.start_binding=self.binding;self.g.last_budget={}
        self.m={'files':[{'path':str(i),'size':1,'sha256':'0'*64} for i in range(2)]}
        for p in [patch.object(n,'HERE',self.root),patch.object(n,'qualified',return_value={'selected_binding':self.binding}),patch.object(n,'manifest',return_value=self.m),patch.object(n,'transport',return_value=self.a),patch.object(n,'Gate',return_value=self.g),patch.object(n,'physical_namespace',return_value=True)]:p.start();self.addCleanup(p.stop)
    def test_two_source_files_complete_no_model_action(self):
        self.assertEqual(n.main('test-only'),0);d=json.loads((self.root/'ACQUIRE_STATE.json').read_text());self.assertEqual(d['status'],'BOTH_COMPLETE_OFFICIAL_SHARDS_SHA256_VERIFIED_NO_MODEL_RUN');self.assertEqual(d['model_service_GPU_actions'],0);self.assertEqual(self.a.acquire_file.call_count,2)
    def test_fault_stops_before_second_file(self):
        self.a.acquire_file.side_effect=TimeoutError('synthetic');self.assertEqual(n.main('test-only'),1);self.assertEqual(self.a.acquire_file.call_count,1);self.assertEqual(json.loads((self.root/'ACQUIRE_STATE.json').read_text())['status'],'ACQUISITION_HOLD')
    def test_changed_binding_or_namespace_before_lock_mutation(self):
        self.g.selected.host.start_binding={'native_pid':8}
        with self.assertRaises(ValueError):n.main('test-only')
        self.assertFalse((self.root/'download.lock').exists());self.a.acquire_file.assert_not_called()
    def test_lock_alias_refused(self):
        (self.root/'download.lock').symlink_to(self.root/'foreign')
        with self.assertRaises(ValueError):n.main('test-only')
        self.assertFalse((self.root/'foreign').exists());self.a.acquire_file.assert_not_called()
    def test_nonphysical_namespace_before_lock_mutation(self):
        with patch.object(n,'physical_namespace',return_value=False):
            with self.assertRaises(ValueError):n.main('test-only')
        self.assertFalse((self.root/'download.lock').exists());self.a.acquire_file.assert_not_called()

class Qualification(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();original_here=n.HERE
        for name in n.SOURCES:(self.root/name).write_bytes((original_here/name).read_bytes())
        (self.root/'input').write_bytes(b'synthetic input');self.inputs={'synthetic':self.root/'input'}
        tree=ast.parse((self.root/'test_acquire_native.py').read_text());self.ids=sorted('test_acquire_native.'+c.name+'.'+f.name for c in tree.body if isinstance(c,ast.ClassDef) for f in c.body if isinstance(f,ast.FunctionDef) and f.name.startswith('test_'))
        sm={name:n.sha(self.root/name) for name in n.SOURCES};im={k:n.sha(p) for k,p in self.inputs.items()}
        self.q={'root_source_read':True,'sol_source_read':True,'source_sha256':sm,'input_sha256':im,'test_ids':self.ids,'files':{str(self.root/name):pin for name,pin in sm.items()}}
        self.q['files'][str(self.root/'input')]=im['synthetic']
        review=self.root/'ACQUIRE_SOURCE_ROOT_REVIEW.json';review.write_text(json.dumps({k:self.q[k] for k in ['root_source_read','sol_source_read','source_sha256','input_sha256','test_ids']}));self.q['files'][str(review)]=n.sha(review)
        for host,pid in [('darwin',1001),('linux',1002)]:
            d=self.root/('ACQUIRE-CPU-FIRST-'+host);d.mkdir()
            v={'platform':host,'cpu':[30,30],'as':[512*2**20]*2 if host=='linux' else None,'nice':15,'pgid':pid,'pid':pid,'dont_write_bytecode':True,'environment':{'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1'}}
            (d/'receipt.json').write_text(json.dumps({'passed':True,'source_sha256':sm,'input_sha256':im,'test_ids':self.ids,'controls':len(self.ids),'observed':v}))
            (d/'child.json').write_text(json.dumps({'returncode':0,'error':None,'cleanup':[],'elapsed_seconds':1.,'pid':pid}));(d/'child.log').write_text('synthetic test-only evidence')
            for name in ['receipt.json','child.json','child.log']:self.q['files'][str(d/name)]=n.sha(d/name)
        for p in [patch.object(n,'HERE',self.root),patch.object(n,'input_paths',return_value=self.inputs)]:p.start();self.addCleanup(p.stop)
    def check(self):
        p=self.root/'acquire-qualification.json';p.write_text(json.dumps(self.q));return n.qualified(n.sha(p))
    def test_source_exact_matching_cpu_positive(self):self.assertEqual(self.check()['test_ids'],self.ids)
    def test_executing_source_input_and_raw_log_cannot_be_omitted(self):
        for path in [str(self.root/'acquire_native.py'),str(self.root/'input'),str(self.root/'ACQUIRE-CPU-FIRST-linux/child.log')]:
            old=self.q['files'].pop(path)
            with self.assertRaises(ValueError):self.check()
            self.q['files'][path]=old
    def test_failed_or_unbounded_child_refused(self):
        p=self.root/'ACQUIRE-CPU-FIRST-linux/child.json';old=p.read_text();d=json.loads(old);d['returncode']=1;p.write_text(json.dumps(d));self.q['files'][str(p)]=n.sha(p)
        with self.assertRaises(ValueError):self.check()
    def test_false_manual_review_or_empty_ids_refused(self):
        self.q['sol_source_read']=False
        with self.assertRaises(ValueError):self.check()
        self.q['sol_source_read']=True;self.q['test_ids']=[]
        with self.assertRaises(ValueError):self.check()

if __name__=='__main__':unittest.main()
