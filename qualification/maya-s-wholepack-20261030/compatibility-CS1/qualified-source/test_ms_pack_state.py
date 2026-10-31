"""Exact actual public metadata inputs for prospective native-only dump bounds."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

M=Path(__file__).resolve().parent
E=M.parents[2]
SOURCE=E/'decode-optimization-20261028/model-v1/imma_storage.py'
SOURCE_SHA='d03c8f6d69e198e648014b15a00a4a7c3dd986815dac4a391b747924239e0143'


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def storage():
    if digest(SOURCE)!=SOURCE_SHA:raise ValueError('Reviewed storage source changed')
    spec=importlib.util.spec_from_file_location('ms_pack_state_storage_cpu',SOURCE)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def geom(raw):
    kv={}
    for line in raw.decode().splitlines():
        key,value=line.split(' ',1)
        if key in kv:raise ValueError('Duplicate actual geometry field')
        kv[key]=value
    return {'layers':int(kv['num_hidden_layers'])+len(kv['dspark_target_layer_ids'].split(',')),
            'head_dim':int(kv['head_dim']),'index_head_dim':int(kv['index_head_dim']),
            'window':int(kv['sliding_window']),'ratios':tuple(map(int,kv['compress_ratios'].split(','))),
            'kv_sources':tuple(map(int,kv['kv_source_layer_ids'].split(','))),
            'index_sources':tuple(map(int,kv['index_source_layer_ids'].split(','))),
            'experts_per_layer_profile':int(kv['n_routed_experts'])}


class PackStates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=storage()
        cls.states={which:json.loads((M/('pack-state-'+which+'.json')).read_text()) for which in ('A','B')}

    def state_geom(self,which):
        g=copy.deepcopy(self.states[which]['storage_geometry'])
        for k in ('ratios','kv_sources','index_sources'):g[k]=tuple(g[k])
        return g

    def test_baseline_actual_selected_geometry_and_complete_files(self):
        source=E/'decode-optimization-20261028/model-v1/pack-geometry.ds4.txt'
        files=json.loads((E/'decode-optimization-20261028/model-v1/pack-files.json').read_text())
        self.assertEqual(self.s.geometry(source.read_bytes()),self.state_geom('A'))
        self.assertEqual(self.states['A']['ds4_txt_sha256'],digest(source))
        self.assertEqual(self.states['A']['pack_files'],[x['name'] for x in files['pk_files']])
        self.assertEqual(len(self.states['A']['pack_files']),7)

    def test_candidate_actual_constructed_geometry_and_all_eight_file_rows(self):
        pack=M.parent/'pack-v1/pack-FIRST'
        self.assertEqual(digest(pack/'ds4.txt'),self.states['B']['ds4_txt_sha256'])
        self.assertEqual(digest(pack/'tensors.txt'),self.states['B']['tensors_txt_sha256'])
        self.assertEqual(geom((pack/'ds4.txt').read_bytes()),self.state_geom('B'))
        rows=[line.split(' ',2) for line in (pack/'tensors.txt').read_text().splitlines() if line.startswith('file ')]
        self.assertEqual([int(row[1]) for row in rows],list(range(8)))
        self.assertEqual([row[2] for row in rows],self.states['B']['pack_files'])

    def test_actual_constructor_result_binds_candidate_metadata(self):
        result=json.loads((M.parent/'pack-v3/construct-CPU-FIRST/pack-result.json').read_text())
        self.assertEqual(result['status'],'PACK_METADATA_VERIFIED_NO_MODEL_ADMISSION')
        for name in ('ds4.txt','tensors.txt'):
            key=name.replace('.','_')+'_sha256'
            self.assertEqual(self.states['B'][key],result['output_sha256'][name])

    def test_both_exact_geometries_and_prospective_write_bounds(self):
        for which,m in self.states.items():
            with self.subTest(which=which):
                g=self.state_geom(which);self.s.selected_geometry(g)
                b=self.s.storage_bound(g,m['engine_version'],m['pack_files'])
                self.assertEqual(b['hard_per_file'],536870912)
                self.assertEqual(b['max_dump_files'],4)
                self.assertTrue(all(x<536870912 for x in b['native_owned_file_bounds'].values()))
                self.assertEqual(m['engine_version'],'0.1.27')
                self.assertFalse(m['model_executed']);self.assertFalse(m['near_full_context_or_output_executed'])

    def test_different_geometry_never_inherits_selected_storage_bounds(self):
        for key in ('layers','head_dim','index_head_dim','window','experts_per_layer_profile'):
            g=self.state_geom('B');g[key]+=1
            with self.subTest(key=key),self.assertRaises(ValueError):self.s.selected_geometry(g)

    def test_native_bound_factory_is_excluded_from_timed_modes(self):
        for which,m in self.states.items():
            with self.subTest(which=which):
                self.assertEqual(len(set(m['pack_files'])),len(m['pack_files']))
                bound=self.s.identity_upper_bound(m['engine_version'],m['pack_files'])
                self.assertGreater(bound,0);self.assertLess(bound,2**20)
                self.assertTrue(callable(self.s.native_fsize_preexec(self.state_geom(which),m['engine_version'],m['pack_files'],process_kind='UNMEASURED_NUMERICAL_NATIVE')))
                with self.assertRaises(ValueError):self.s.native_fsize_preexec(self.state_geom(which),m['engine_version'],m['pack_files'],process_kind='TIMED_NATIVE')


if __name__=='__main__':unittest.main()
