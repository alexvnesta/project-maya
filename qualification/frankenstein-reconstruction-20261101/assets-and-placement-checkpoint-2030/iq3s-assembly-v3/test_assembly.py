"""Nine small new assembly controls, never original parts/model or old tests."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock,patch
import assembly as a


class Assembly(unittest.TestCase):
    def fixture(self,root):
        records=[{'target_offset':i*64,'target_bytes':64,'layer':24,'expert':i,'role':'w1'} for i in range(3)]
        values=[bytes([i+1])*64 for i in range(3)]
        for i,data in enumerate(values):(root/('%04d.iq3s'%i)).write_bytes(data)
        def proof(i):return ({'record':records[i],'bytes':64,'codec_returncode':0,'encoder_returncode':0,
            'sha256':hashlib.sha256(values[i]).hexdigest()}, {'returncode':0,'error':None,'timed_out':False,
            'cleanup_errors':[],'descendants_remaining':False},{'index':i,'complete':True})
        return records,values,proof

    def test_partition_geometry_covers_all3840_without_overlap_or_holes(self):
        groups=a.ranges();self.assertEqual(len(groups),30)
        self.assertEqual([n for begin,end in groups for n in range(begin,end)],list(range(3840)))
        self.assertEqual(a.ranges(5,2),[(0,2),(2,4),(4,5)])
        records=[{'target_offset':i*7,'target_bytes':7} for i in range(5)];a.records_contract(records,5,7)
        records[2]['target_offset']+=1
        with self.assertRaises(ValueError):a.records_contract(records,5,7)

    def test_tiny_actual_part_SHA_copy_disjoint_readback_and_shared_cursor(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();records,values,proof=self.fixture(root)
            with tempfile.TemporaryFile() as out:
                out.truncate(192);out.seek(17);s=os.fstat(out.fileno());identity=[s.st_dev,s.st_ino,s.st_size]
                rows=a.copy_partition(records,0,2,root,out.fileno(),identity,proof,matrix_bytes=64)
                self.assertEqual([r['index'] for r in rows],[0,1]);self.assertEqual(out.tell(),17)
                self.assertEqual(os.pread(out.fileno(),192,0),values[0]+values[1]+bytes(64))
                a.copy_partition(records,2,3,root,out.fileno(),identity,proof,matrix_bytes=64)
                self.assertEqual(os.pread(out.fileno(),192,0),b''.join(values))

    def test_short_pwrite_completes_or_refuses_zero_without_cursor_mutation(self):
        with tempfile.TemporaryFile() as out:
            out.truncate(20);out.seek(13)
            a.pwrite_all(out.fileno(),b'abcdef',3,write=lambda fd,data,offset:os.pwrite(fd,data[:2],offset))
            self.assertEqual(out.tell(),13);self.assertEqual(os.pread(out.fileno(),6,3),b'abcdef')
            with self.assertRaises(ValueError):a.pwrite_all(out.fileno(),b'x',0,write=lambda *args:0)

    def test_bad_part_hash_child_or_DONE_stops_before_any_later_interval(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();records,values,proof=self.fixture(root)
            for mode in ('hash','child','done'):
                seen=[]
                def wrong(i):
                    seen.append(i);p,c,d=proof(i)
                    if mode=='hash':p['sha256']='0'*64
                    elif mode=='child':c['returncode']=1
                    else:d['complete']=False
                    return p,c,d
                with tempfile.TemporaryFile() as out:
                    out.truncate(192);s=os.fstat(out.fileno())
                    with self.assertRaises(ValueError):a.copy_partition(records,0,3,root,out.fileno(),[s.st_dev,s.st_ino,192],wrong,matrix_bytes=64)
                    self.assertEqual(seen,[0]);self.assertEqual(os.pread(out.fileno(),128,64),bytes(128))

    def test_single_final_hash_is_exact_and_size_guarded(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t).resolve()/'new.partial';path.write_bytes(b'complete-new-output')
            h,fp=a.full_hash(path,19);self.assertEqual(h,hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(fp,a.regular(path))
            with self.assertRaises(ValueError):a.full_hash(path,18)

    def test_actual_wait4_usage_preserved_on_killed_child_no_retry(self):
        with tempfile.TemporaryDirectory() as t:
            folder=Path(t).resolve();p=types.SimpleNamespace(pid=123,returncode=None)
            p.poll=lambda:p.returncode
            children=types.SimpleNamespace(popen=Mock(return_value=p),owner=types.SimpleNamespace(cleanup_failed=Mock()))
            owner=types.SimpleNamespace(cleanup=Mock())
            usage=types.SimpleNamespace(ru_utime=29.,ru_stime=1.,ru_maxrss=1234)
            with patch.object(a,'OUT',folder),patch.object(a.os,'wait4',return_value=(123,9,usage)):
                with self.assertRaises(ValueError):a.run_child('finalize','pin',children,owner,lambda:None,a.time.monotonic()+90)
            row=json.loads((folder/'finalize.child.json').read_text())
            self.assertEqual(row['returncode'],-9);self.assertEqual(row['wait4_usage']['user_seconds'],29.)
            self.assertEqual(row['wait4_usage']['system_seconds'],1.);self.assertEqual(children.popen.call_count,1)
            self.assertEqual(owner.cleanup.call_count,1)

    def test_reused_qualified_queue_fault_stops_new_admission(self):
        bulk=a.exact('assembly_test_bulk_queue',a.BULK,a.BULK_SHA);queue=bulk.conversion();seen=[]
        def task(i):seen.append(i);raise ValueError('intentional assembly fault')
        with self.assertRaises(ValueError):queue.convert_queue(list(range(30)),task,lambda:None,workers=1)
        self.assertEqual(seen,[0])

    def test_storage_keeps_original_evidence_root132_and_future_native(self):
        need=a.RESERVE+a.BYTES+a.NATIVE_RESERVE
        self.assertEqual(a.disk_admission(need),need)
        with self.assertRaises(ValueError):a.disk_admission(need-1)


    def test_new_logical_artifact_publication_preserves_original_failed_bytes_and_receipts(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();old=root/'old';old.mkdir();out=root/'new';out.mkdir()
            failed=old/'overlay.partial';failed.write_bytes(b'original failed bytes')
            receipt=old/'supervision.json';receipt.write_text('{"passed":false}')
            before=a.regular(failed);working=out/'overlay.partial';working.write_bytes(b'new qualified artifact')
            identity=a.regular(working)[:3];artifact=old/'overlay.iq3s'
            with patch.object(a,'OUT',out),patch.object(a,'ORIGINAL',old),patch.object(a,'ARTIFACT',artifact):
                published=a.publish_new_artifact(working,artifact,identity)
                self.assertEqual(published[:3],identity);self.assertFalse(working.exists())
                self.assertEqual(artifact.read_bytes(),b'new qualified artifact')
                self.assertEqual(a.regular(failed),before);self.assertEqual(receipt.read_text(),'{"passed":false}')
                self.assertFalse((old/'result.json').exists())
                another=out/'overlay.partial';another.write_bytes(b'other')
                with self.assertRaises(ValueError):a.publish_new_artifact(another,artifact,a.regular(another)[:3])
                self.assertEqual(another.read_bytes(),b'other')

    def test_original40_must_be_terminal_and_writer_free_before_CPU_admission(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();legacy=root/'iq3s-source-acquisition-v1';legacy.mkdir();(legacy/'acquisition.lock').write_bytes(b'')
            specs=[{'path':'original/part%d'%i,'size':1,'sha256':'%064x'%i} for i in range(40)]
            manifest={'files':specs};terminal={'status':'ALL_FORTY_TRUNK_EXPERT_SHARDS_VERIFIED_NO_MODEL_RUN','returncode':0,
                'files':[dict(path=s['path'],bytes=s['size'],sha256=s['sha256'],status='DOWNLOADED_VERIFIED') for s in specs],
                'manifest_sha256':'68503758fd9ca619be1a165ce506809dd45e3bc23cd754f9c1220b9e82132df4',
                'asset_root':str(legacy/'assets'),'pid':123}
            q={'files':{str(root/'original-expert-acquisition-v2/ASSET_MANIFEST.json'):terminal['manifest_sha256']}}
            def raw(q,path):return manifest if Path(path).name=='ASSET_MANIFEST.json' else terminal
            with patch.object(a,'Q',root),patch.object(a,'raw',side_effect=raw),patch.object(a,'regular',return_value=[1,2,1,3,4]), \
                 patch.object(a.os,'kill',side_effect=ProcessLookupError):
                a.source40_closed(q)
                terminal['status']='PASSIVE_TRUNK_EXPERT_DOWNLOAD_RUNNING'
                with self.assertRaises(ValueError):a.source40_closed(q)


if __name__=='__main__':unittest.main(verbosity=2)
