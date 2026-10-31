"""Actual frozen public headers/index and pack metadata, with malformed negatives."""
import copy
import json
from pathlib import Path
import posixpath
import unittest
import hybrid_plan as h

HERE=Path(__file__).resolve().parent
PACK=HERE.parent/'maya-s-comparison-v1/pack-v1/pack-FIRST'

def sample():
    manifest=json.loads((HERE/'NATIVE_GU_SOURCE_MANIFEST.json').read_text())
    index=json.loads((HERE/'official-1017-safetensors-index-FIRST.json').read_text())
    headers={r['path']:h.header((HERE/('official-header-'+r['path']+'.json')).read_bytes(),r['size']) for r in manifest['files']}
    return manifest,index,headers

class SourcePlan(unittest.TestCase):
    def test_actual_complete_role_coverage_and_source_ranges(self):
        m,index,headers=sample();plan=h.make_plan(index,headers)
        self.assertEqual(len(plan),1536);self.assertEqual(plan[-1]['output_offset']+plan[-1]['output_bytes'],m['output_overlay_bytes']);self.assertEqual(plan[0]['name'],'layers.25.ffn.experts.0.w1.weight');self.assertEqual(plan[-1]['name'],'layers.26.ffn.experts.383.w3.weight')
        for r in plan:
            self.assertEqual(r['weight_range'][1]-r['weight_range'][0],5898240);self.assertEqual(r['scale_range'][1]-r['scale_range'][0],368640)
    def test_missing_or_different_shard_mapping_refused(self):
        m,index,headers=sample();key='layers.25.ffn.experts.0.w1.weight';del index['weight_map'][key]
        with self.assertRaises(KeyError):h.make_plan(index,headers)
        m,index,headers=sample();index['weight_map'][key]='other.safetensors'
        with self.assertRaises(ValueError):h.make_plan(index,headers)
    def test_wrong_native_dtype_shape_or_boolean_dimension_refused(self):
        for field,value in [('dtype','F16'),('shape',[2304,5120]),('shape',[True,2560])]:
            m,index,headers=sample();d=headers[index['weight_map']['layers.25.ffn.experts.0.w1.weight']]['tensors']['layers.25.ffn.experts.0.w1.weight'];d[field]=value
            with self.assertRaises(ValueError):h.make_plan(index,headers)
    def test_short_negative_and_outside_file_ranges_refused(self):
        for change in ('short','negative','outside'):
            m,index,headers=sample();key='layers.25.ffn.experts.0.w1.weight';head=headers[index['weight_map'][key]];d=head['tensors'][key];a,b=d['data_offsets']
            d['data_offsets']={'short':[a,b-1],'negative':[-1,h.WEIGHT_BYTES-1],'outside':[head['file_bytes'],head['file_bytes']+h.WEIGHT_BYTES]}[change]
            with self.assertRaises(ValueError):h.make_plan(index,headers)
    def test_overlapping_source_planes_refused(self):
        m,index,headers=sample();key='layers.25.ffn.experts.0.w1.weight';head=headers[index['weight_map'][key]];head['tensors']['layers.25.ffn.experts.1.w1.weight']['data_offsets']=head['tensors'][key]['data_offsets']
        with self.assertRaises(ValueError):h.make_plan(index,headers)
    def test_duplicate_nonfinite_or_unbounded_header_refused(self):
        for raw,size in [(b'{"x":1,"x":2}',1000),(b'{"x":NaN}',1000),(b'',1000),(b'{}',True),(b'{}',9)]:
            with self.assertRaises(ValueError):h.header(raw,size)

class Pack(unittest.TestCase):
    def setUp(self):
        m,index,headers=sample();self.plan=h.make_plan(index,headers);self.ds4=(PACK/'ds4.txt').read_text();self.tensors=(PACK/'tensors.txt').read_text();self.root='/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028';self.overlay=self.root+'/s2-public-hybrid-v1/native-gu-FIRST/native-gu.bin'
    def test_only_declared_role_rows_and_file_addresses_change(self):
        d,t=h.pack_metadata(self.ds4,self.tensors,self.plan,self.root,self.overlay)
        self.assertEqual([x for x in d.splitlines() if not x.startswith('model_dir ')],[x for x in self.ds4.splitlines() if not x.startswith('model_dir ')])
        old={x.split()[1]:x for x in self.tensors.splitlines() if x.startswith('t ')};new={x.split()[1]:x for x in t.splitlines() if x.startswith('t ')};targets={r['name']:r for r in self.plan};self.assertEqual(set(old),set(new))
        for name,row in old.items():
            if name not in targets:self.assertEqual(new[name],row)
            else:self.assertEqual(new[name].split()[2:],['MXFP4','8',str(targets[name]['output_offset']),'6266880','2304','5120'])
        old_dir=next(x[10:] for x in self.ds4.splitlines() if x.startswith('model_dir '));old_files={int(x.split()[1]):x.split()[2] for x in self.tensors.splitlines() if x.startswith('file ')};new_files={int(x.split()[1]):x.split()[2] for x in t.splitlines() if x.startswith('file ')}
        self.assertEqual(len(new_files),9)
        for i,name in old_files.items():self.assertEqual(posixpath.normpath(old_dir+'/'+name),posixpath.normpath(self.root+'/'+new_files[i]))
        self.assertEqual(posixpath.normpath(self.root+'/'+new_files[8]),self.overlay)
    def test_missing_duplicate_or_different_original_role_refused(self):
        line=next(x for x in self.tensors.splitlines() if x.startswith('t '+self.plan[0]['name']+' '))
        for text in [self.tensors.replace(line+'\n',''),self.tensors+line+'\n',self.tensors.replace(line,line.replace(' IQ2_XXS ',' IQ3_XXS '))]:
            with self.assertRaises(ValueError):h.pack_metadata(self.ds4,text,self.plan,self.root,self.overlay)
    def test_unknown_target_or_output_overlap_refused(self):
        for field,value in [('name','layers.0.ffn.experts.0.w2.weight'),('output_offset',1),('output_bytes',1),('shape',[2304,5119])]:
            p=copy.deepcopy(self.plan);p[0][field]=value
            with self.assertRaises(ValueError):h.pack_metadata(self.ds4,self.tensors,p,self.root,self.overlay)
    def test_foreign_overlay_and_duplicate_original_files_refused(self):
        for overlay in ['/tmp/other.bin',self.root+'/../other.bin']:
            with self.assertRaises(ValueError):h.pack_metadata(self.ds4,self.tensors,self.plan,self.root,overlay)
        with self.assertRaises(ValueError):h.pack_metadata(self.ds4,self.tensors+'file 0 duplicate\n',self.plan,self.root,self.overlay)

if __name__=='__main__':unittest.main()
