"""Saved constructor/metadata and injected-stat negatives; no tensor/model access."""
import copy
import json
from pathlib import Path
import unittest
import candidate_assets as a

class Assets(unittest.TestCase):
    def proofs(self,name):
        base=a.E/'decode-optimization-20261028'
        if name=='HGU':
            root=base/'s2-public-hybrid-v1/native-gu-FIRST';old=base/'maya-s-comparison-v1/pack-v3/construct-CPU-FIRST'
            return a.read(root/'state.json'),{'original':a.read(old/'pack-result.json'),'child':a.read(old/'child.json'),
                'ledger':[json.loads(x) for x in (root/'matrices.jsonl').read_text().splitlines()]}
        return a.read(base/'unsloth-pack-v1/CONSTRUCTION_RESULT_R2_FIRST.json'),{'download':a.read(base/'unsloth-v31-iq2xxs-download-v1/STATE64.json')}
    def qualification(self):
        files={};doc=a.dossier()
        for p in (a.DATA/'PACK_CUSTODY_FROZEN.json',a.DATA/'ASSET_STAT_ATTESTATION_FIRST.json'):files[str(p)]=a.sha(p)
        for row in doc['candidates'].values():
            pack=a.E/row['pack_relative_to_E']
            for n in row['proof_relative_to_E']:files[str(a.E/n)]=a.sha(a.E/n)
            for n in row['metadata_sha256']:files[str(pack/n)]=a.sha(pack/n)
            for n in row['tokenizer_sha256']:files[str(pack/'tokenizer'/n)]=a.sha(pack/'tokenizer'/n)
        return {'files':files}
    def test_actual_completed_constructors_and_matrix_coverage(self):
        doc=a.dossier();self.assertTrue(a.contract(doc))
        for name,row in doc['candidates'].items():
            closed,extra=self.proofs(name);self.assertTrue(a.closed_contract(name,row,closed,**extra))
    def test_actual_small_metadata_guard_with_injected_exact_asset_stats(self):
        q=self.qualification();expected={k:v for name in ('HGU','UNSLOTH') for k,v in a.assets(name).items()};calls=[]
        def observe(p):calls.append(p);return expected[p]
        self.assertTrue(a.guard(q,stat_reader=observe));self.assertEqual(set(calls),set(expected));self.assertEqual(len(calls),17)
    def test_changed_tensor_identity_or_proof_pin_refused(self):
        q=self.qualification();expected={k:v for name in ('HGU','UNSLOTH') for k,v in a.assets(name).items()}
        def wrong(p):v=expected[p][:];v[1]+=1;return v
        with self.assertRaises(ValueError):a.guard(q,stat_reader=wrong)
        q['files']={}
        with self.assertRaises(ValueError):a.guard(q,stat_reader=lambda p:expected[p])
    def test_missing_original_P3_result_or_child_pin_blocks_before_asset_reads(self):
        for leaf in ('pack-result.json','child.json'):
            q=self.qualification();path=a.E/'decode-optimization-20261028/maya-s-comparison-v1/pack-v3/construct-CPU-FIRST'/leaf
            del q['files'][str(path)];calls=[]
            with self.assertRaises(ValueError):a.guard(q,stat_reader=lambda p:calls.append(p))
            self.assertEqual(calls,[])
    def test_missing_overlay_and_boolean_stat_refused(self):
        for change in ('overlay','bool'):
            doc=a.dossier()
            if change=='overlay':doc['candidates']['HGU']['assets'].pop()
            else:doc['candidates']['HGU']['assets'][0]['signature'][1]=True
            with self.assertRaises(ValueError):a.contract(doc)
    def test_HGU_failed_partial_duplicate_or_gapped_codec_ledger_refused(self):
        row=a.dossier()['candidates']['HGU'];closed,extra=self.proofs('HGU')
        for kind in ('missing','duplicate','gap','failed'):
            e=copy.deepcopy(extra)
            if kind=='missing':e['ledger'].pop()
            elif kind=='duplicate':e['ledger'][1]['name']=e['ledger'][0]['name']
            elif kind=='gap':e['ledger'][1]['output_offset']+=1
            else:e['ledger'][0]['codec']['returncode']=1
            with self.assertRaises(ValueError):a.closed_contract('HGU',row,closed,**e)
    def test_constructor_failure_source_drift_and_late_overlay_refused(self):
        row=a.dossier()['candidates']['HGU'];closed,extra=self.proofs('HGU')
        bad=copy.deepcopy(closed);bad['returncode']=1
        with self.assertRaises(ValueError):a.closed_contract('HGU',row,bad,**extra)
        bad=copy.deepcopy(row);bad['assets'][0]['signature'][1]+=1
        with self.assertRaises(ValueError):a.closed_contract('HGU',bad,closed,**extra)
        bad=copy.deepcopy(row);bad['assets'][8]['signature'][4]=2**63-1
        with self.assertRaises(ValueError):a.closed_contract('HGU',bad,closed,**extra)
    def test_Unsloth_incomplete_download_bad_bounds_or_tokenizer_refused(self):
        row=a.dossier()['candidates']['UNSLOTH'];closed,extra=self.proofs('UNSLOTH')
        for key,value in [('returncode',1),('all_incoming_tokenizer_payloads_preserved',False),('pack_sha256',{})]:
            bad=copy.deepcopy(closed);bad[key]=value
            with self.assertRaises(ValueError):a.closed_contract('UNSLOTH',row,bad,**extra)
        bad=copy.deepcopy(closed);bad['actual_bounds']['as']=None
        with self.assertRaises(ValueError):a.closed_contract('UNSLOTH',row,bad,**extra)
        e=copy.deepcopy(extra);e['download']['status']='PARTIAL'
        with self.assertRaises(ValueError):a.closed_contract('UNSLOTH',row,closed,**e)
    def test_each_pack_actual_header_and_session_file_count(self):
        for name,count in [('HGU',9),('UNSLOTH',8)]:
            m=a.storage_meta(name);self.assertEqual(len(m['pack_files']),count);self.assertEqual(m['storage_geometry']['layers'],43)
    def test_each_pack_actual_CPU_literal_manifest_and_policy(self):
        for arm,name in [('FHGU','HGU'),('FUNSLOTH','UNSLOTH')]:
            m=a.manifest(arm);self.assertEqual(m['candidate'],name);self.assertEqual(m['actual_prompt_tokens'],44)
            self.assertEqual([x['id'] for x in m['cases']],['state44-cold','state44-warm'])
            self.assertEqual(m['cases'][0]['prompt_ids'],m['cases'][1]['prompt_ids']);self.assertFalse(m['quality_or_performance_pass'])
            self.assertFalse(m['automatic_next_arm'])
