import copy
import unittest
from unittest.mock import patch
import io
import hashlib
import build_artifact as a

class Audit(unittest.TestCase):
    def sample(self):
        return {'qualification_sha256':a.Q,'pins':5768,'verified_unchanged':5767,
            'differences':[{'path':a.MUTABLE,'before':'90d7ec0f0acef104d8b6252794295f661a0149634868d02a1ae0c358099638f5','after':None}],
            'child':{'argv':['/usr/bin/cmake','--build',a.P+'native-build-r2-FIRST','--target','maya-ds4','--','-j1'],
                     'returncode':0,'error':None,'cleanup':[],'elapsed_seconds':673.7},
            'supervision':{'passed':False,'owned_claim_released':True,'error':a.ERROR},
            'active_cpu_build':False,'owned_group_members':[],
            'cmake_terminal_progress_command':'\t$(CMAKE_COMMAND) -E cmake_progress_start '+a.P+'native-build-r2-FIRST/CMakeFiles 0',
            'outputs':{'maya-ds4':{'sha256':a.NATIVE,'bytes':44669336,'magic':'7f454c46'},
                'libstrata_kernels_cpu.a':{'sha256':a.CPU,'bytes':4206302,'magic':'213c617263683e0a'}}}
    def test_complete_independent_scope(self):
        s=self.sample(); before=copy.deepcopy(s);r=a.validate(s)
        self.assertEqual(s,before);self.assertTrue(r['passed']);self.assertFalse(r['original_supervision_regraded']);self.assertFalse(r['GPU_or_model_qualified'])
    def test_source_change_refused(self):
        s=self.sample();s['differences'].append({'path':a.P+'source-r2/src/ds4/ds4_model.cu','before':'x','after':'y'})
        with self.assertRaises(ValueError):a.validate(s)
    def test_progress_modified_instead_of_absent_refused(self):
        s=self.sample();s['differences'][0]['after']='x'
        with self.assertRaises(ValueError):a.validate(s)
    def test_input_omission_refused(self):
        for key in ('pins','verified_unchanged'):
            s=self.sample();s[key]-=1
            with self.assertRaises(ValueError):a.validate(s)
    def test_failed_child_refused(self):
        for key,value in [('returncode',1),('returncode',False),('error','fault'),('cleanup',['fault']),('elapsed_seconds',900)]:
            s=self.sample();s['child'][key]=value
            with self.assertRaises(ValueError):a.validate(s)
    def test_wrong_build_command_refused(self):
        s=self.sample();s['child']['argv'][-1]='-j8'
        with self.assertRaises(ValueError):a.validate(s)
    def test_regraded_original_refused(self):
        s=self.sample();s['supervision']['passed']=True
        with self.assertRaises(ValueError):a.validate(s)
    def test_different_error_refused(self):
        s=self.sample();s['supervision']['error']='compiler failed'
        with self.assertRaises(ValueError):a.validate(s)
    def test_claim_or_surviving_group_refused(self):
        for key,value in [('active_cpu_build',True),('owned_group_members',[123])]:
            s=self.sample();s[key]=value
            with self.assertRaises(ValueError):a.validate(s)
    def test_wrong_artifact_or_format_refused(self):
        for name in ('maya-ds4','libstrata_kernels_cpu.a'):
            for key,value in [('sha256','x'),('magic','x'),('bytes',0)]:
                s=self.sample();s['outputs'][name][key]=value
                with self.assertRaises(ValueError):a.validate(s)
    def test_progress_cleanup_command_required(self):
        s=self.sample();s['cmake_terminal_progress_command']='unrelated'
        with self.assertRaises(ValueError):a.validate(s)
    def test_large_input_hash_streams_with_fixed_read_size(self):
        class Stream(io.BytesIO):
            def read(self, n=-1):
                if not 0 < n <= 65536: raise AssertionError('Unbounded input read')
                return super().read(n)
        data=b'0123456789'*100000
        with patch('pathlib.Path.open', return_value=Stream(data)):
            self.assertEqual(a.digest('/synthetic'),hashlib.sha256(data).hexdigest())

    def test_wrong_qualification_refused(self):
        s=self.sample();s['qualification_sha256']='x'
        with self.assertRaises(ValueError):a.validate(s)

if __name__=='__main__':unittest.main()
