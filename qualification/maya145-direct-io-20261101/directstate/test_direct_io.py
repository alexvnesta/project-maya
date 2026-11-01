"""Pure synthetic direct-copy observation negatives; no real process/model."""
import copy
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import direct_io as d
import current_runtime as r
NATIVE_SOURCE_ROOT=None

class Direct(unittest.TestCase):
    def test_actual_frozen_native_copy_path_and_profile_flag(self):
        import current_config as c
        import json
        model=(NATIVE_SOURCE_ROOT/'src/ds4/ds4_model.cu').read_text()
        header=(NATIVE_SOURCE_ROOT/'src/ds4/ds4_os.hpp').read_text()
        self.assertIn('direct_copy && os::copy_direct(dfd, off, nb, dst, direct_staging)',model)
        self.assertIn('if (!pk.read_at(l.mx_file[r], off, nb, dst)) bad.store(true);',model)
        self.assertIn('::open(path.c_str(), O_RDONLY | O_DIRECT)',header)
        base=json.loads((Path(__file__).parent/'profile-base-config.json').read_text())
        directory=c.E/'results/maya145-directio-mayas-TP2-20261101T020000Z/native'
        value=c.make_config(base,directory,'directstate','ITP2')
        self.assertEqual(value['env']['DS4_COPY_DIRECT'],'1')
        changed=copy.deepcopy(value);del changed['env']['DS4_COPY_DIRECT']
        with self.assertRaises(ValueError):c.check_config(base,changed,directory,'directstate','ITP2')
    def sample(self):
        expected={'/source/%d'%i:[1,10+i,10000,30,40] for i in range(8)}
        rows=[{'fd':10+2*i+j,'path':p,'flags':d.DIRECT_FLAG if j else 0,'signature':v[:]} for i,(p,v) in enumerate(expected.items()) for j in (0,1)]
        return rows,expected
    def test_exact_both_descriptor_types_all_files(self):
        rows,e=self.sample();before=copy.deepcopy(rows);self.assertTrue(d.rows_contract(rows,e));self.assertEqual(rows,before)
    def test_missing_direct_or_original_refused(self):
        for j in (0,1):
            rows,e=self.sample()
            with self.assertRaises(ValueError):d.rows_contract([r for r in rows if bool(r['flags']&d.DIRECT_FLAG)==bool(j)],e)
    def test_inode_size_time_and_path_differences_refused(self):
        for i in range(5):
            rows,e=self.sample();rows[0]['signature'][i]+=1
            with self.assertRaises(ValueError):d.rows_contract(rows,e)
        rows,e=self.sample();rows[0]['path']='/foreign'
        with self.assertRaises(ValueError):d.rows_contract(rows,e)
    def test_duplicate_writable_bool_fd_and_fields_refused(self):
        rows,e=self.sample()
        for key,v in [('fd',True),('fd',10000),('flags',1),('flags',True),('extra',1)]:
            changed=copy.deepcopy(rows);changed[0][key]=v
            with self.assertRaises(ValueError):d.rows_contract(changed,e)
        with self.assertRaises(ValueError):d.rows_contract(rows+[rows[0]],e)
    def test_direct_counters_actual_once_positive_no_fallback(self):
        log='ds4: expert copy I/O: 71.818 GB direct, 0.000 GB buffered fallback\n'
        self.assertEqual(d.counters(log)['direct_GB_rounded'],71.818)
        for bad in ['',log+log,log.replace('71.818','0.000'),log.replace('0.000 GB buffered','0.001 GB buffered'),log.replace('71.818','nan')]:
            with self.assertRaises(ValueError):d.counters(bad)
    def test_saved_source_snapshot_and_native_pid_rechecked(self):
        rows,e=self.sample();log='ds4: expert copy I/O: 71.818 GB direct, 0.000 GB buffered fallback\n'
        value={'native_pid':71,'start_ticks':123,'sources':e,'descriptors':rows,'counters':d.counters(log),'actual_linux_O_DIRECT_descriptors':True,'source_paths_not_modified':True,'model_math_equivalence_claim':False}
        with patch.object(d,'asset_paths',return_value=list(e)),patch.object(d,'signature',side_effect=lambda p:e[p]):
            self.assertTrue(d.saved_contract(value,log,71,'unused',123))
            with self.assertRaises(ValueError):d.saved_contract(value,log,71,'unused',124)
            for key,v in [('native_pid',72),('start_ticks',False),('actual_linux_O_DIRECT_descriptors',False),('sources',{})]:
                bad=copy.deepcopy(value);bad[key]=v
                with self.assertRaises(ValueError):d.saved_contract(bad,log,71,'unused',123)
    def test_original_source_file_table_contiguous_unique_exact_eight(self):
        with tempfile.TemporaryDirectory() as x:
            p=Path(x).resolve();(p/'ds4.txt').write_text('model_dir '+str(p)+'\n')
            for i in range(8):(p/('x%d'%i)).write_text('fixture')
            table=''.join('file %d x%d\n'%(i,i) for i in range(8));(p/'tensors.txt').write_text(table+'t ignored tensor\n')
            self.assertEqual(d.asset_paths(p),[str(p/('x%d'%i)) for i in range(8)])
            for bad in [table.replace('file 3','file 4'),table.replace('7 x7','7 x6'),table.splitlines()[0]+'\n']:
                (p/'tensors.txt').write_text(bad)
                with self.assertRaises(ValueError):d.asset_paths(p)

class HelperProof(unittest.TestCase):
    def qualification(self):
        root=r.P.parent/'direct-copy-io-v1';native=r.P.parent/'maya145-mayas-v1/source-r2/src/ds4'
        review=json.loads((root/'ROOT_SOURCE_REVIEW.json').read_text())
        group={k:copy.deepcopy(review[k]) for k in ('source_sha256','input_sha256','test_ids')}
        group['proofs']={}
        files={str(root/'ROOT_SOURCE_REVIEW.json'):r.sha(root/'ROOT_SOURCE_REVIEW.json')}
        for n,pin in group['source_sha256'].items():files[str(root/n)]=pin
        for n,pin in group['input_sha256'].items():files[str(native/n)]=pin
        for platform in ('darwin','linux'):
            folder=root/('CPU-FIRST-'+platform)
            paths={k:str(folder/n) for k,n in [('receipt','receipt.json'),('child','child.json'),('log','child.log')]}
            group['proofs'][platform]=paths
            files.update({v:r.sha(v) for v in paths.values()})
        return {'files':files,'direct_helper_CPU':group}
    def test_actual_first15_both_platforms_required(self):
        self.assertTrue(r.direct_helper_proof(self.qualification()))
    def test_missing_map_platform_source_or_failed_membership_blocks(self):
        for key,value in [('test_ids',[]),('proofs',{}),('source_sha256',{}),('input_sha256',{})]:
            q=self.qualification();q['direct_helper_CPU'][key]=value
            with self.assertRaises(ValueError):r.direct_helper_proof(q)
        q=self.qualification();q['files']={}
        with self.assertRaises(ValueError):r.direct_helper_proof(q)
