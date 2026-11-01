"""Focused new CPU custody/source receipt gates; no actual model or payload."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock
import owner as o


class Owner(unittest.TestCase):
    def values(self):
        plan={'source_map_sha256':'map','official_revision':'revision',
              'source_headers':{'a':{'source_file_sha256':'sha-a'},'b':{'source_file_sha256':'sha-b'}}}
        parts=[{'root':str(o.ROOT),'plan_sha256':'map','files':{n:{'full_sha_verified':True,
                 'sha256':'sha-'+n,'fingerprint':[1,2,3,4,5]}}} for n in ('a','b')]
        return plan,parts

    def test_complete_original_sources_are_bound_to_map_revision_and_root(self):
        plan,parts=self.values();out=o.merge_sources(plan,parts)
        self.assertEqual(set(out['files']),{'a','b'});self.assertEqual(out['official_revision'],'revision')
        self.assertEqual(out['source_map_sha256'],'map');self.assertEqual(out['root'],str(o.ROOT))

    def test_missing_duplicate_wrong_sha_or_unverified_source_blocks_materialization(self):
        plan,parts=self.values()
        for mode in ('missing','duplicate','wrong','unverified','map','root'):
            changed=copy.deepcopy(parts)
            if mode=='missing':changed.pop()
            elif mode=='duplicate':changed.append(copy.deepcopy(parts[0]))
            elif mode=='wrong':changed[0]['files']['a']['sha256']='wrong'
            elif mode=='unverified':changed[0]['files']['a']['full_sha_verified']=False
            elif mode=='map':changed[0]['plan_sha256']='foreign'
            else:changed[0]['root']='/foreign'
            with self.subTest(mode=mode),self.assertRaises(ValueError):o.merge_sources(plan,changed)

    def test_exact_cpu_claim_release_preserves_unrelated_state(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'state.json';record={'mode':'ours','nonce':'frozen'}
            state={'active_cpu_build':record,'unrelated':{'preserve':7}};path.write_text(json.dumps(state))
            calls=[]
            def cas(p,raw,new):
                self.assertEqual(p,path);self.assertEqual(json.loads(raw),state);calls.append(new)
            o.release(types.SimpleNamespace(cas_state=cas),path,record,{'passed':True})
            self.assertEqual(calls,[dict(state,active_cpu_build=False)])

    def test_foreign_claim_or_unclosed_children_never_release_cpu_custody(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'state.json';path.write_text(json.dumps({'active_cpu_build':{'mode':'other'}}))
            cas=types.SimpleNamespace(cas_state=Mock())
            for absence in ({'passed':True},{'passed':False}):
                with self.assertRaises(ValueError):o.release(cas,path,{'mode':'ours'},absence)
            cas.cas_state.assert_not_called()

    def test_source_and_metadata_hashing_is_streaming_and_exclusive_evidence_is_preserved(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();source=root/'bytes';source.write_bytes(b'original')
            import hashlib
            self.assertEqual(o.sha(source),hashlib.sha256(b'original').hexdigest())
            self.assertEqual(o.bounded_hash(source)['sha256'],hashlib.sha256(b'original').hexdigest())
            out=root/'receipt';o.emit(out,{'passed':False})
            with self.assertRaises(FileExistsError):o.emit(out,{'passed':True})
            self.assertFalse(json.loads(out.read_text())['passed'])

    def test_import_refuses_wrong_source_hash_and_alias(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();source=root/'source.py';source.write_text('VALUE=1\n')
            self.assertEqual(o.exact('native_owner_test_exact',source,o.sha(source)).VALUE,1)
            with self.assertRaises(ValueError):o.exact('bad',source,'0'*64)
            alias=root/'alias.py';alias.symlink_to(source)
            with self.assertRaises(ValueError):o.exact('alias',alias,o.sha(source))

    def test_cpu_qualification_needs_matching_physical_source_inputs_and_all_controls(self):
        source={'owner.py':'pin'};ids=['one'];proofs={}
        for platform in ('darwin','linux'):
            proofs[platform]={'passed':True,'returncode':0,'controls':1,'test_ids':ids,'source_sha256':source,
                'input_sha256':{'payload':'pin'},'failures':0,'errors':0,
                'observed':{'platform':platform,'cpu':[30,30],'nice':15,
                    'as':[512*2**20]*2 if platform=='linux' else None,'pid':123,'pgid':123,
                    'dont_write_bytecode':True,'environment':o.ENV}}
        o.cpu_contract(proofs,source,ids)
        for key,bad in [('controls',0),('returncode',1),('source_sha256',{}),('input_sha256',{}),('test_ids',['other'])]:
            wrong=copy.deepcopy(proofs);wrong['linux'][key]=bad
            with self.assertRaises(ValueError):o.cpu_contract(wrong,source,ids)
        wrong=copy.deepcopy(proofs);wrong['linux']['observed']['as']=None
        with self.assertRaises(ValueError):o.cpu_contract(wrong,source,ids)


if __name__=='__main__':unittest.main(verbosity=2)
