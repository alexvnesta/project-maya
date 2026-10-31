"""Offline construction seams, byte custody, partial preservation and owned cleanup."""
import hashlib
import io
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import construct_native_r2 as c

class NoPace:
    def __init__(self):self.bytes=0
    def tick(self,n):self.bytes+=n

class Files(unittest.TestCase):
    def test_regular_open_identity_and_signature(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve()/'x';p.write_bytes(b'original');f,s=c.open_source(p)
            with f:self.assertEqual(f.read(),b'original');self.assertEqual(c.signature(p),s)
    def test_symlink_hardlink_directory_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();p=root/'x';p.write_bytes(b'x');s=root/'s';s.symlink_to(p)
            with self.assertRaises(ValueError):c.open_source(s)
            os.link(p,root/'hard')
            with self.assertRaises(ValueError):c.signature(p)
            with self.assertRaises(ValueError):c.signature(root)
    def test_hash_stream_reads_all_bytes_and_paces(self):
        b=b'a'*(5*2**20)+b'last';pace=NoPace();f=io.BytesIO(b);f.seek(20)
        self.assertEqual(c.hash_stream(f,pace),(len(b),hashlib.sha256(b).hexdigest()));self.assertEqual(pace.bytes,len(b))
    def test_exact_range_and_truncation_bounds(self):
        self.assertEqual(c.exact_range(io.BytesIO(b'abcdef'),[2,5]),b'cde')
        for span in ([2,9],[-1,3],[True,3],[4,2],[0,c.h.WEIGHT_BYTES+1]):
            with self.assertRaises(ValueError):c.exact_range(io.BytesIO(b'abcdef'),span)
    def test_exclusive_publish_retains_collision_partial(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve()/'partial';f=Path(d).resolve()/'final';p.write_bytes(b'new');f.write_bytes(b'old')
            with self.assertRaises(ValueError):c.publish(p,f)
            self.assertEqual(p.read_bytes(),b'new');self.assertEqual(f.read_bytes(),b'old')
    def test_publish_new_final_exact_bytes_and_nlink1(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve()/'partial';f=Path(d).resolve()/'final';p.write_bytes(b'new');c.publish(p,f)
            self.assertFalse(p.exists());self.assertEqual(f.read_bytes(),b'new');self.assertEqual(f.stat().st_nlink,1)
    def test_publish_refuses_empty_alias_or_foreign_parent(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve()/'x';p.write_bytes(b'')
            with self.assertRaises(ValueError):c.publish(p,Path(d).resolve()/'y')
            p.write_bytes(b'x')
            with self.assertRaises(ValueError):c.publish(p,Path(d).resolve()/'other/y')

class Codec(unittest.TestCase):
    def script(self,root,body):
        p=root/'codec';p.write_text('#!'+sys.executable+'\n'+body+'\n');p.chmod(0o700);return p
    def test_actual_cpu_child_bounds_environment_and_exact_pipe_bytes(self):
        parent_cpu=resource.getrlimit(resource.RLIMIT_CPU);parent_env=dict(os.environ)
        with tempfile.TemporaryDirectory() as d:
            exe=self.script(Path(d).resolve(),'''import os,resource,sys
assert resource.getrlimit(resource.RLIMIT_CPU)==(30,30)
if sys.platform=='linux':assert resource.getrlimit(resource.RLIMIT_AS)==(512*2**20,512*2**20)
assert os.getpriority(os.PRIO_PROCESS,0)==15
assert os.getpgrp()==os.getpgid(os.getppid()) and os.getpgrp()!=os.getpid()
assert os.environ['CUDA_VISIBLE_DEVICES']=='' and os.environ['OMP_NUM_THREADS']=='1'
assert sys.stdin.buffer.read()==b'w'*16+b'\\x7f'
sys.stdout.buffer.write(b'\\x7f'+b'w'*16)''')
            out,receipt=c.convert(b'w'*16+b'\x7f',exe,1,32)
            self.assertEqual(out,b'\x7f'+b'w'*16);self.assertEqual(receipt['returncode'],0);self.assertEqual(receipt['input_sha256'],hashlib.sha256(b'w'*16+b'\x7f').hexdigest())
        self.assertEqual(resource.getrlimit(resource.RLIMIT_CPU),parent_cpu);self.assertEqual(dict(os.environ),parent_env)
    def test_actual_nonzero_stderr_short_and_long_output_fail(self):
        for body in ["raise SystemExit(4)","import sys;sys.stderr.write('bad');sys.stdout.buffer.write(b'x'*17)","import sys;sys.stdout.buffer.write(b'x'*16)","import sys;sys.stdout.buffer.write(b'x'*18)"]:
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaises(ValueError):c.convert(bytes(17),self.script(Path(d).resolve(),body),1,32)
    def test_invalid_payload_and_shape_refuse_before_spawn(self):
        with patch.object(c.subprocess,'Popen') as p:
            for payload,rows,k in [(bytes(16),1,32),(bytes(17),True,32),(bytes(17),1,31)]:
                with self.assertRaises(ValueError):c.convert(payload,'unused',rows,k)
            p.assert_not_called()
    def test_actual_timeout_closes_captured_pid_in_inherited_owner_group(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();exe=self.script(root,"import time;time.sleep(5)")
            real_spawn=subprocess.Popen;owned=[]
            def spawn(*args,**kwargs):
                proc=real_spawn(*args,**kwargs);owned.append(proc);return proc
            with patch.object(c.subprocess,'Popen',side_effect=spawn):
                with self.assertRaises(subprocess.TimeoutExpired):c.convert(bytes(17),exe,1,32,run_seconds=.1)
            self.assertEqual(len(owned),1);self.assertIsNotNone(owned[0].returncode)
            with self.assertRaises(ProcessLookupError):os.kill(owned[0].pid,0)
    def test_timeout_cleans_only_captured_pid_never_owner_group(self):
        class Child:
            pid=987654
            returncode=None
            stdin=stdout=stderr=None
            def communicate(self,payload,timeout):
                if timeout!=85:raise AssertionError('Original85s bound')
                raise subprocess.TimeoutExpired('codec',timeout)
            def poll(self):return self.returncode
            def terminate(self):calls.append('TERM')
            def kill(self):calls.append('KILL');self.returncode=-9
            def wait(self,timeout):
                if self.returncode is None:raise subprocess.TimeoutExpired('codec',timeout)
                return self.returncode
        child=Child();calls=[]
        with patch.object(c.subprocess,'Popen',return_value=child),patch.object(c.os,'getpgid',return_value=os.getpgrp()),patch.object(c.os,'killpg') as groupkill:
            with self.assertRaises(subprocess.TimeoutExpired):c.convert(bytes(17),'unused',1,32)
            groupkill.assert_not_called()
        self.assertEqual(calls,['TERM','KILL'])
    def test_no_separate_group_or_unbounded_timeout_can_be_requested(self):
        with patch.object(c.subprocess,'Popen') as spawn:
            for value in (0,-1,86,float('inf'),True):
                with self.assertRaises(ValueError):c.convert(bytes(17),'unused',1,32,run_seconds=value)
            spawn.assert_not_called()

class Construction(unittest.TestCase):
    def setup_plan(self):
        return [{'name':'expert'+str(i),'source':'shard','weight_range':[0,16],'scale_range':[16,17],'output_offset':i*17,'output_bytes':17} for i in range(1536)]
    def codec(self,payload):
        b=payload[16:]+payload[:16]
        return b,{'returncode':0,'input_sha256':hashlib.sha256(payload).hexdigest(),'output_sha256':hashlib.sha256(b).hexdigest()}
    def test_complete_order_byte_custody_and_independent_readback(self):
        with tempfile.TemporaryDirectory() as d,patch.object(c.h,'MATRIX_BYTES',17),patch.object(c.h,'TOTAL_BYTES',1536*17):
            p=Path(d).resolve()/'partial';log=Path(d).resolve()/'log';payload=bytes(range(17));result=c.construct(self.setup_plan(),{'shard':io.BytesIO(payload)},p,log,self.codec,NoPace())
            expected=(bytes([16])+bytes(range(16)))*1536
            self.assertEqual(p.read_bytes(),expected);self.assertEqual(result,{'bytes':len(expected),'sha256':hashlib.sha256(expected).hexdigest(),'matrices':1536})
            rows=[json.loads(x) for x in log.read_text().splitlines()];self.assertEqual(len(rows),1536);self.assertEqual(rows[1535]['name'],'expert1535');self.assertEqual(rows[10]['output_offset'],170)
    def test_wrong_codec_status_bytes_or_hash_retains_partial_and_stops(self):
        for fault in ('status','short','inputhash','outputhash'):
            calls=[]
            def codec(payload):
                calls.append(1);b,r=self.codec(payload)
                if fault=='status':r['returncode']=1
                if fault=='short':b=b[:-1]
                if fault=='inputhash':r['input_sha256']='0'*64
                if fault=='outputhash':r['output_sha256']='0'*64
                return b,r
            with tempfile.TemporaryDirectory() as d,patch.object(c.h,'MATRIX_BYTES',17),patch.object(c.h,'TOTAL_BYTES',1536*17):
                p=Path(d).resolve()/'partial'
                with self.assertRaises(ValueError):c.construct(self.setup_plan(),{'shard':io.BytesIO(bytes(17))},p,Path(d).resolve()/'log',codec,NoPace())
                self.assertTrue(p.exists());self.assertEqual(p.stat().st_size,0);self.assertEqual(len(calls),1)
    def test_incomplete_plan_never_publishes(self):
        with tempfile.TemporaryDirectory() as d,patch.object(c.h,'MATRIX_BYTES',17),patch.object(c.h,'TOTAL_BYTES',1536*17):
            p=Path(d).resolve()/'partial'
            with self.assertRaises(ValueError):c.construct(self.setup_plan()[:1],{'shard':io.BytesIO(bytes(17))},p,Path(d).resolve()/'log',self.codec,NoPace())
            self.assertEqual(p.stat().st_size,17);self.assertFalse((Path(d).resolve()/'final').exists())
    def test_overlap_refuses_before_second_codec_and_preserves_first(self):
        plan=self.setup_plan();plan[1]['output_offset']=0;calls=[]
        def codec(payload):calls.append(1);return self.codec(payload)
        with tempfile.TemporaryDirectory() as d,patch.object(c.h,'MATRIX_BYTES',17),patch.object(c.h,'TOTAL_BYTES',1536*17):
            p=Path(d).resolve()/'partial'
            with self.assertRaises(ValueError):c.construct(plan,{'shard':io.BytesIO(bytes(17))},p,Path(d).resolve()/'log',codec,NoPace())
            self.assertEqual(p.stat().st_size,17);self.assertEqual(len(calls),1)
    def test_existing_partial_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve()/'partial';p.write_bytes(b'prior')
            with self.assertRaises(FileExistsError):c.construct([],{},p,Path(d).resolve()/'log',self.codec,NoPace())
            self.assertEqual(p.read_bytes(),b'prior')
    def test_pause_or_deadline_stops_before_read_or_codec(self):
        def paused():raise ValueError('Paused')
        for pace in (c.Pace(paused,c.time.monotonic()+10),c.Pace(lambda:None,c.time.monotonic()-1)):
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaises(ValueError):c.construct(self.setup_plan(),{},Path(d).resolve()/'p',Path(d).resolve()/'log',lambda _:self.fail('Codec executed'),pace)
    def test_actual_source_and_codec_drift_signatures_detectable(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve()/'x';p.write_bytes(b'a');first=c.signature(p);p.write_bytes(b'b');self.assertNotEqual(c.signature(p),first)

class Qualification(unittest.TestCase):
    def fixture(self,host='linux'):
        source={'source':'a'*64};inputs={'fixture':'b'*64};ids=['test.original']
        child={'pid':12345,'returncode':0,'error':None,'cleanup':[],'elapsed_seconds':1.0}
        receipt={'passed':True,'source_sha256':source,'input_sha256':inputs,'test_ids':ids,'controls':1,'observed':{'pid':12345,'pgid':12345,'platform':host,'cpu':[30,30],'as':[512*2**20]*2 if host=='linux' else None,'nice':15,'environment':dict(c.ENV),'dont_write_bytecode':True}}
        return receipt,child,host,source,inputs,ids
    def test_both_actual_platform_resource_contracts_accepted(self):
        for host in ('darwin','linux'):c.validate_receipt(*self.fixture(host))
    def test_wrong_partial_or_source_cpu_proof_refused(self):
        for key,value in [('passed',False),('controls',True),('test_ids',[]),('source_sha256',{}),('input_sha256',{})]:
            args=self.fixture();args[0][key]=value
            with self.assertRaises(ValueError):c.validate_receipt(*args)
    def test_failed_or_unclean_cpu_child_refused(self):
        for key,value in [('returncode',True),('returncode',1),('error','failure'),('cleanup',['survivor']),('elapsed_seconds',91)]:
            args=self.fixture();args[1][key]=value
            with self.assertRaises(ValueError):c.validate_receipt(*args)
    def test_unbounded_or_foreign_child_refused(self):
        for key,value in [('cpu',[60,60]),('as',None),('platform','darwin'),('nice',0),('pgid',222),('environment',{}),('dont_write_bytecode',False)]:
            args=self.fixture();args[0]['observed'][key]=value
            with self.assertRaises(ValueError):c.validate_receipt(*args)

if __name__=='__main__':unittest.main()
