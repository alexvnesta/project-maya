"""Synthetic and public-metadata CPU controls. No downloaded weights or APIs."""
import copy
import ast
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch,Mock
from types import SimpleNamespace
import pack_guard as g


def s(x):
    b=x.encode();return struct.pack('<Q',len(b))+b


def val(x):
    if type(x)is int:return 10,struct.pack('<Q',x)
    if type(x)is str:return 8,s(x)
    if isinstance(x,list):
        t=val(x[0])[0] if x else 10
        return 9,struct.pack('<IQ',t,len(x))+b''.join(val(v)[1] for v in x)
    raise ValueError(x)


def gguf(kvs=None,tensors=None,payload=64):
    kvs=kvs or [('general.architecture','deepseek41'),('general.alignment',32)]
    tensors=tensors or [('output_norm.weight',0,[16],0)]
    b=b'GGUF'+struct.pack('<IQQ',3,len(tensors),len(kvs))
    for k,v in kvs:
        t,vb=val(v);b+=s(k)+struct.pack('<I',t)+vb
    for n,t,d,o in tensors:b+=s(n)+struct.pack('<I',len(d))+struct.pack('<'+'Q'*len(d),*d)+struct.pack('<IQ',t,o)
    b+=b'\0'*((-len(b))%32);return b+b'\0'*payload


def synthetic_headers(root):
    """Full logical40x384x3 map, no weight allocations or sparse large files."""
    kv={'general.architecture':'deepseek41','split.count':6,'tokenizer.ggml.tokens':['tok%d'%i for i in range(129280)],'tokenizer.ggml.token_type':[1]*129280,'tokenizer.ggml.merges':['a b'],'tokenizer.ggml.pre':'deepseek3','tokenizer.chat_template':'{{ messages }}','tokenizer.ggml.bos_token_id':0,'tokenizer.ggml.eos_token_id':1,'tokenizer.ggml.padding_token_id':2}
    fields={'block_count':40,'embedding_length':5120,'attention.head_count':64,'attention.key_length':512,'rope.dimension_count':64,'attention.q_lora_rank':1280,'attention.output_lora_rank':1024,'attention.output_group_count':8,'expert_count':384,'expert_used_count':6,'expert_feed_forward_length':2304,'attention.sliding_window':128,'hyper_connection.count':4,'context_length':1048576,'dspark.block_size':5,'dspark.noise_token_id':128799,'dspark.markov_rank':256,'dspark.expert_count':128,'dspark.expert_used_count':3,'dspark.target_layers':[37,38,39],'attention.compress_ratios':[0]*40,'attention.kv_source_layers':[2,8,14,20],'attention.indexer.source_layers':[2,8,14,20,24,28,32,36],'engram.layers':[1,14],'engram.max_ngram_size':2,'engram.head_count':1,'engram.head_dim':256,'engram.pad_token_id':2,'engram.token_map':list(range(129280)),'engram.multipliers':[1,2,3,4],'engram.primes':[31,31],'engram.offsets':[0,0],'engram.num_embeddings':[32,32]}
    kv.update({'deepseek41.'+k:v for k,v in fields.items()})
    tensors=[('token_embd.weight',8,[5120,129280],0),('output.weight',13,[5120,129280],0),('output_norm.weight',0,[5120],0)]
    for il in range(40):
        for role,dims in [('gate',[5120,2304,384]),('up',[5120,2304,384]),('down',[2304,5120,384])]:tensors.append(('blk.%d.ffn_%s_exps.weight'%(il,role),16,dims,0))
    source_roles=('attn_q_a.weight','attn_q_b.weight','attn_kv.weight','attn_output_b.weight','attn_q_a_norm.weight','attn_kv_a_norm.weight','attn_sinks.weight','attn_norm.weight','ffn_norm.weight','hc_attn_fn.weight','hc_attn_scale.weight','hc_attn_base.weight','hc_ffn_fn.weight','hc_ffn_scale.weight','hc_ffn_base.weight','ffn_gate_inp.weight','exp_probs_b.bias','ffn_gate_shexp.weight','ffn_up_shexp.weight','ffn_down_shexp.weight')
    for il in range(40):
        tensors.extend(('blk.%d.%s'%(il,name),0,[1],0) for name in source_roles)
        tensors.append(('blk.%d.attn_output_a.weight'%il,0,[1,8],0))
    for il in (1,14):
        tensors.extend([('blk.%d.engram_embd.weight'%il,14,[256,32],0),('blk.%d.engram_kv.weight'%il,30,[5120,5120],0),('blk.%d.engram_gate.weight'%il,30,[5120],0)])
    gs=[]
    for i in range(6):
        ts=[];offset=0
        for name,typ,dims,_ in tensors[i::6]:
            ts.append((name,typ,dims,offset));_,per,bpb=g.TYPES[typ];offset+=((g.math.prod(dims)//per*bpb+31)//32)*32
        ks=kv.copy() if i==0 else {'general.architecture':'deepseek41','split.count':6}
        ks.update({'split.no':i,'split.tensors.count':len(tensors)})
        gs.append(SimpleNamespace(path=root/('s%d.gguf'%i),kv=ks,tensors=ts,data_start=256))
    return gs


def sparse_headers(root):
    """Exact published metadata distribution; tensor contents remain synthetic."""
    gs=synthetic_headers(root)
    for h in gs[1:]:
        h.kv={k:h.kv[k] for k in ('split.count','split.no','split.tensors.count')}
    return gs


class Base(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
    def tearDown(self):self.tmp.cleanup()
    def header(self,b):
        p=self.root/'synthetic.gguf';p.write_bytes(b);return g.Header(p)


class Headers(Base):
    def test_valid_directory_payload_not_read(self):
        h=self.header(gguf());self.assertEqual(h.tensors[0][:3],('output_norm.weight',0,[16]));self.assertEqual(h.data_start%32,0)
    def test_magic(self):
        with self.assertRaisesRegex(ValueError,'magic'):self.header(b'FAIL'+gguf()[4:])
    def test_version(self):
        with self.assertRaisesRegex(ValueError,'version'):self.header(gguf()[:4]+struct.pack('<I',2)+gguf()[8:])
    def test_truncated_directory(self):
        with self.assertRaisesRegex(ValueError,'truncated'):self.header(gguf()[:35])
    def test_duplicate_key(self):
        with self.assertRaisesRegex(ValueError,'duplicate'):self.header(gguf([('a',1),('a',2)]))
    def test_duplicate_tensor(self):
        with self.assertRaisesRegex(ValueError,'duplicate'):self.header(gguf(tensors=[('x',0,[8],0),('x',0,[8],32)]))
    def test_tensor_oob(self):
        with self.assertRaisesRegex(ValueError,'outside'):self.header(gguf(tensors=[('x',0,[100],0)]))
    def test_tensor_overlap(self):
        with self.assertRaisesRegex(ValueError,'overlap'):self.header(gguf(tensors=[('x',0,[16],0),('y',0,[8],32)]))
    def test_unknown_type(self):
        with self.assertRaisesRegex(ValueError,'unsupported'):self.header(gguf(tensors=[('x',99,[16],0)]))
    def test_arbitrary_integer_metadata(self):
        with self.assertRaisesRegex(ValueError,'role'):self.header(gguf(tensors=[('x',26,[16],0)]))
    def test_quant_row_alignment(self):
        with self.assertRaisesRegex(ValueError,'divisible'):self.header(gguf(tensors=[('x',13,[255],0)]))
    def test_offset_alignment(self):
        with self.assertRaisesRegex(ValueError,'alignment'):self.header(gguf(tensors=[('x',0,[8],1)]))
    def test_bad_general_alignment(self):
        with self.assertRaisesRegex(ValueError,'power'):self.header(gguf([('general.alignment',3)]))
    def test_huge_directory_count(self):
        with self.assertRaises(ValueError):self.header(b'GGUF'+struct.pack('<IQQ',3,100001,1))
    def test_huge_string(self):
        with self.assertRaises(ValueError):self.header(b'GGUF'+struct.pack('<IQQQ',3,1,1,2**32))
    def test_nested_array(self):
        b=b'GGUF'+struct.pack('<IQQ',3,1,1)+s('x')+struct.pack('<IIQ',9,9,1)
        with self.assertRaisesRegex(ValueError,'nested'):self.header(b)
    def test_invalid_utf8(self):
        b=b'GGUF'+struct.pack('<IQQQ',3,1,1,1)+b'\xff'
        with self.assertRaises(UnicodeDecodeError):self.header(b)
    def test_guard_period_not_per_value(self):
        p=self.root/'many.gguf';p.write_bytes(gguf([('many',list(range(100)))]));guard=Mock()
        with patch.object(g.time,'monotonic',return_value=1):g.Header(p,guard)
        self.assertEqual(guard.call_count,1)


class MapContracts(Base):
    @classmethod
    def setUpClass(cls):cls.p=g.load_packer()
    def test_exact_source_origin(self):
        self.assertEqual(g.sha(Path(self.p.__file__)),g.PACKER_SHA);self.assertEqual(self.p.TYPES,g.TYPES)
    def test_actual_pinned_vision_metadata_geometry(self):
        path=g.HERE.parent/'baseline-vision.json';self.assertEqual(g.sha(path),g.VISION_PINS['vision.json']);info=g.read_json(path)
        rows=g.supplemental(info,970536960,'vision');self.assertGreater(len(rows),200);self.assertEqual(sum(r[3] for r in rows),970536960);self.assertEqual(info['config']['image_token_id'],129264)
    def test_complete_six_shards_and_exact_geometry(self):
        gs=synthetic_headers(self.root);kv=g.header_set(gs);g.validate_geometry(self.p.geometry(kv,129280))
    def test_published_three_key_later_shards(self):
        gs=sparse_headers(self.root)
        self.assertTrue(all(set(h.kv)=={'split.count','split.no','split.tensors.count'} for h in gs[1:]))
        self.assertIs(g.header_set(gs),gs[0].kv)
        g.validate_geometry(self.p.geometry(gs[0].kv,129280))
    def test_sparse_base_architecture_absent(self):
        gs=sparse_headers(self.root);del gs[0].kv['general.architecture']
        gs[1].kv['general.architecture']='deepseek41'
        with self.assertRaisesRegex(ValueError,'base architecture'):g.header_set(gs)
    def test_sparse_base_architecture_wrong(self):
        gs=sparse_headers(self.root);gs[0].kv['general.architecture']='other'
        with self.assertRaisesRegex(ValueError,'base architecture'):g.header_set(gs)
    def test_sparse_later_explicit_null_architecture(self):
        gs=sparse_headers(self.root);gs[3].kv['general.architecture']=None
        with self.assertRaisesRegex(ValueError,'architecture'):g.header_set(gs)
    def test_sparse_later_foreign_architecture(self):
        gs=sparse_headers(self.root);gs[5].kv['general.architecture']='engram'
        with self.assertRaisesRegex(ValueError,'architecture'):g.header_set(gs)
    def test_sparse_duplicate_tensor_still_refused(self):
        gs=sparse_headers(self.root);gs[2].tensors.append(gs[0].tensors[0])
        with self.assertRaisesRegex(ValueError,'duplicate'):g.header_set(gs)
    def test_sparse_repeated_tokenizer_mismatch_refused(self):
        gs=sparse_headers(self.root);gs[1].kv['tokenizer.chat_template']='foreign'
        with self.assertRaisesRegex(ValueError,'inconsistent'):g.header_set(gs)
    def test_sparse_repeated_geometry_mismatch_refused(self):
        gs=sparse_headers(self.root);gs[1].kv['deepseek41.context_length']=32768
        with self.assertRaisesRegex(ValueError,'inconsistent'):g.header_set(gs)
    def test_sparse_split_total_mismatch_refused(self):
        gs=sparse_headers(self.root);gs[4].kv['split.tensors.count']+=1
        with self.assertRaisesRegex(ValueError,'tensor count'):g.header_set(gs)
    def test_missing_shard(self):
        with self.assertRaisesRegex(ValueError,'six'):g.header_set(synthetic_headers(self.root)[:5])
    def test_duplicate_split(self):
        gs=synthetic_headers(self.root);gs[1].kv['split.no']=0
        with self.assertRaisesRegex(ValueError,'split'):g.header_set(gs)
    def test_duplicate_cross_shard_tensor(self):
        gs=synthetic_headers(self.root);gs[1].tensors.append(gs[0].tensors[0])
        with self.assertRaisesRegex(ValueError,'duplicate'):g.header_set(gs)
    def test_inconsistent_metadata(self):
        gs=synthetic_headers(self.root);gs[1].kv['deepseek41.context_length']=32768
        with self.assertRaisesRegex(ValueError,'inconsistent'):g.header_set(gs)
    def test_no_template_fallback(self):
        gs=synthetic_headers(self.root);del gs[0].kv['tokenizer.chat_template']
        with self.assertRaisesRegex(ValueError,'template'):g.header_set(gs)
    def test_duplicate_vocab(self):
        gs=synthetic_headers(self.root);gs[0].kv['tokenizer.ggml.tokens'][2]='tok1'
        with self.assertRaisesRegex(ValueError,'vocabulary'):g.header_set(gs)
    def test_context_or_effort_changed(self):
        geo=g.GEOMETRY.copy();geo.update(dspark_target_layer_ids=[37,38,39],engram_layer_ids=[1,14],compress_ratios=[0]*40,kv_source_layer_ids=[2],index_source_layer_ids=[2]);geo['max_position_embeddings']=524288
        with self.assertRaises(ValueError):g.validate_geometry(geo)
        cfg=g.PROFILE.copy();cfg['effort']=100.0
        with self.assertRaises(ValueError):g.profile_contract(cfg)
    def test_public_drafter_roles_and_offsets(self):
        d={'tensors':[['mtp.%d.norm.weight'%i,'F32',i*256,4,[1]] for i in range(3)]};self.assertEqual(len(g.supplemental(d,516,'drafter')),3)
    def test_drafter_foreign_role(self):
        with self.assertRaisesRegex(ValueError,'foreign'):g.supplemental({'tensors':[['layers.0.weight','F32',0,4,[1]]]},4,'drafter')
    def test_drafter_oob(self):
        with self.assertRaisesRegex(ValueError,'outside'):g.supplemental({'tensors':[['mtp.0.x','F32',4,4,[1]]]},4,'drafter')
    def test_drafter_byte_shape_mismatch(self):
        with self.assertRaisesRegex(ValueError,'geometry'):g.supplemental({'tensors':[['mtp.0.x','F32',0,4,[2]]]},4,'drafter')
    def test_drafter_missing_block(self):
        with self.assertRaisesRegex(ValueError,'missing'):g.supplemental({'tensors':[['mtp.0.x','F32',0,4,[1]]]},4,'drafter')
    def test_drafter_overlap(self):
        with self.assertRaisesRegex(ValueError,'overlap'):g.supplemental({'tensors':[['mtp.%d.x'%i,'F32',0,4,[1]] for i in range(3)]},4,'drafter')
    def test_complete_tensor_map_capacity_and_expert_role(self):
        gs=synthetic_headers(self.root);kv=gs[0].kv;di=[('mtp.%d.norm.weight'%i,'F32',i*4,4,[1]) for i in range(3)];vi=[('image_start','F32',0,4,[1])]
        rows=g.expected_tensors(self.p,gs,kv,di,vi,['s']*8,[2**50]*8);cap=g.capacity_inputs(rows,self.p.geometry(kv,129280))
        self.assertEqual(len(cap['per_expert_three_role_bytes']),40*384);self.assertGreater(cap['tensor_payload_bytes']['routed'],0);self.assertIn('UNPROVEN',cap['fit_verdict'])
        
        for h in gs:h.tensors=[t for t in h.tensors if t[0]!='blk.0.ffn_gate_exps.weight']
        with self.assertRaisesRegex(ValueError,'missing expert'):g.expected_tensors(self.p,gs,kv,di,vi,['s']*8,[2**50]*8)
    def test_bad_expert_dims(self):
        gs=synthetic_headers(self.root)
        for h in gs:
            for i,(n,t,d,o) in enumerate(h.tensors):
                if 'ffn_gate_exps' in n:h.tensors[i]=(n,t,[5120,2048,384],o);break
        with self.assertRaisesRegex(ValueError,'role dimensions'):g.expected_tensors(self.p,gs,gs[0].kv,[],[],['s']*8,[2**50]*8)
    def test_missing_mandatory_dense_role(self):
        gs=synthetic_headers(self.root)
        for h in gs:h.tensors=[t for t in h.tensors if t[0]!='blk.0.attn_q_a.weight']
        with self.assertRaisesRegex(ValueError,'mandatory dense'):g.expected_tensors(self.p,gs,gs[0].kv,[],[],['s']*8,[2**50]*8)
    def test_unknown_mapped_tensor(self):
        gs=synthetic_headers(self.root);gs[0].tensors.append(('alien.weight',0,[1],0))
        with self.assertRaisesRegex(ValueError,'global'):g.expected_tensors(self.p,gs,gs[0].kv,[],[],['s']*8,[2**50]*8)
    def test_tokenizer_and_engram_bytes_match_actual_packer(self):
        kv=synthetic_headers(self.root)[0].kv;out=self.root/'tokenizer';self.p.write_tokenizer(out,kv,kv['tokenizer.chat_template']);self.p.write_engram(self.root/'engram.bin',kv,129280)
        self.assertEqual((self.root/'engram.bin').read_bytes(),g.engram_bytes(kv));self.assertEqual((out/'chat_template.jinja').read_text(),kv['tokenizer.chat_template']);self.assertEqual(json.loads((out/'vocab.json').read_text())['tok129279'],129279)
    def test_actual_packer_complete_metadata_matches_independent_map(self):
        model=self.root/'assets/Maya-S';model.mkdir(parents=True);draft=model.parent/'dspark';draft.mkdir();vision=self.root/'vision';vision.mkdir()
        gs=synthetic_headers(model)
        for h in gs:h.path.write_bytes(b'synthetic-header-substitute')
        di={'tensors':[['mtp.%d.norm.weight'%i,'F32',i*256,4,[1]] for i in range(3)]}
        vi={'config':{'image_token_id':129264},'tensors':[['image_start','F32',0,4,[1]]]}
        (draft/'dspark.json').write_text(json.dumps(di));(draft/'dspark.bin').write_bytes(b'0'*516);(vision/'vision.json').write_text(json.dumps(vi));(vision/'vision.bin').write_bytes(b'0'*4)
        expected,rows,geo=g.expected_outputs(self.p,gs,gs[0].kv,di,vi,model,vision,[2**50]*6+[516,4]);out=self.root/'pack'
        args=['pack_gguf.py','--model',str(model),'--out',str(out),'--shards',*[h.path.name for h in gs],'--drafter',str(draft/'dspark.json'),'--vision',str(vision)]
        with patch.object(self.p,'Gguf',side_effect=lambda path:copy.deepcopy(next(h for h in gs if h.path==path))),patch.object(self.p.sys,'argv',args):
            self.assertEqual(self.p.main(),0)
        self.assertEqual(set(g.validate_outputs(out,expected)),set(expected));self.assertEqual(sum('.ffn.experts.' in r[0] for r in rows),40*384*3)
    def test_engram_bad_token_map(self):
        kv=synthetic_headers(self.root)[0].kv;kv['deepseek41.engram.token_map']=[-1]
        with self.assertRaisesRegex(ValueError,'token map'):g.engram_bytes(kv)


class Custody(Base):
    def test_path_symlink_and_hardlink(self):
        p=self.root/'p';p.write_text('x');q=self.root/'q';q.symlink_to(p)
        with self.assertRaises(ValueError):g.regular(q)
        q.unlink();os.link(p,q)
        with self.assertRaises(ValueError):g.regular(p)
    def test_parent_alias(self):
        d=self.root/'d';d.mkdir();q=self.root/'q';q.symlink_to(d)
        with self.assertRaises(ValueError):g.canonical(q/'new')
    def test_duplicate_json(self):
        p=self.root/'x.json';p.write_text('{"x":1,"x":2}')
        with self.assertRaises(ValueError):g.read_json(p)
    def test_nonfinite_json(self):
        p=self.root/'x.json';p.write_text('{"x":NaN}')
        with self.assertRaises(ValueError):g.read_json(p)
    def test_foreign_auto_discovery_file(self):
        (self.root/'Maya-S').mkdir();(self.root/'dspark').mkdir();(self.root/'Maya-S/a').write_text('a');(self.root/'dspark-foreign.gguf').write_text('x')
        with self.assertRaisesRegex(ValueError,'foreign'):g.path_inventory(self.root,{'files':[{'path':'Maya-S/a'}]})
    def test_metadata_output_exact_and_tamper(self):
        out=self.root/'out';out.mkdir();(out/'ds4.txt').write_bytes(b'context 1048576\n');expected={'ds4.txt':b'context 1048576\n'};self.assertEqual(len(g.validate_outputs(out,expected)),1)
        (out/'ds4.txt').write_bytes(b'context 524288\n')
        with self.assertRaisesRegex(ValueError,'changed'):g.validate_outputs(out,expected)
    def test_foreign_output(self):
        out=self.root/'out';out.mkdir();(out/'weights.bin').write_bytes(b'x')
        with self.assertRaises(ValueError):g.validate_outputs(out,{})
    def test_no_implicit_construct(self):
        guard=Mock()
        with self.assertRaises(ValueError):g.construct({},guard)
        guard.assert_not_called()
    def test_guard_before_path_reads(self):
        guard=Mock(side_effect=RuntimeError('busy phase'))
        with self.assertRaisesRegex(RuntimeError,'busy'):g.construct({},guard,run=True)
    def test_complete_receipt_and_failed_status(self):
        m={'files':[{'path':str(i),'size':1,'sha256':'a'*64} for i in range(8)]};r={'status':'ALL_EIGHT_ASSETS_VERIFIED_NO_MODEL_RUN','manifest_sha256':g.MANIFEST_SHA,'authorization_sha256':g.AUTH_SHA,'active_inference_authorized':True,'returncode':0,'model_or_service_actions':0,'files':[{'path':str(i),'bytes':1,'sha256':'a'*64,'status':'DOWNLOADED_VERIFIED'} for i in range(8)]}
        self.assertEqual(len(g.receipt_contract(r,m,self.root)),8)
        r['status']='DEFERRED_PARTIALS_RETAINED'
        with self.assertRaises(ValueError):g.receipt_contract(r,m,self.root)
    def test_receipt_missing_asset(self):
        with self.assertRaises(ValueError):g.receipt_contract({'status':'COMPLETE','files':[]},{'files':[]},self.root)
    def test_manifest_exact_pinned(self):self.assertEqual(g.manifest()['total_bytes'],347445667721)
    def test_packer_source_changed_blocks_import(self):
        with patch.object(g,'sha',return_value='0'*64),self.assertRaisesRegex(ValueError,'source'):g.load_packer()


class PublishedMetadata(Base):
    """Actual public directories/KV only. Never open a real asset or tensor."""
    @classmethod
    def setUpClass(cls):
        if g.sha(g.METADATA_FIXTURE)!=g.METADATA_FIXTURE_SHA:raise ValueError('actual metadata fixture changed')
        cls.fixture=g.read_json(g.METADATA_FIXTURE);cls.p=g.load_packer()

    def headers(self):
        return [SimpleNamespace(path=self.root/Path(s['path']).name,kv=copy.deepcopy(s['kv']),
                                tensors=copy.deepcopy(s['tensors']),data_start=s['data_start'])
                for s in self.fixture['shards']]

    def altered_header(self,change,pattern='fingerprint'):
        gs=self.headers();change(gs[0].kv)
        with self.assertRaisesRegex(ValueError,pattern):g.header_set(gs)

    def test_export_exact_acquired_asset_identities(self):
        manifest=g.manifest();self.assertEqual(self.fixture['manifest_sha256'],g.MANIFEST_SHA)
        for record,asset in zip(self.fixture['shards'],manifest['files'][:6]):
            self.assertEqual(Path(record['path']).name,Path(asset['path']).name)
            self.assertEqual(record['asset_sha256'],asset['sha256'])
            self.assertEqual(record['asset_stat'][2],asset['size'])
        self.assertEqual(self.fixture['drafter_bytes'],manifest['files'][6]['size'])
        self.assertEqual(self.fixture['vision_bytes'],970536960)

    def test_entire_actual_metadata_expected_outputs(self):
        gs=self.headers();kv=g.header_set(gs);x=self.fixture
        before=copy.deepcopy(kv)
        self.p.ple_to_engram(kv);self.p.int_tensors_to_engram(gs,kv)
        for h in gs:self.p.split_ple(h,kv)
        self.assertEqual(kv,before)
        sizes=[r['asset_stat'][2] for r in x['shards']]+[x['drafter_bytes'],x['vision_bytes']]
        outputs,rows,geo=g.expected_outputs(self.p,gs,kv,x['drafter'],x['vision'],self.root,self.root/'vision',sizes)
        self.assertEqual(len(rows),48795);self.assertEqual(len(outputs),8)
        self.assertEqual(geo['max_position_embeddings'],1048576)
        expected={'vocab.json':'2f0bf5b31f4aa191d5d0d78291927a4f28c9ceb498a5e345b97e926c4cb99c1a',
                  'merges.txt':'547bace837acea98652eef5669c9b01cee1c73ad1d2a44d6fdce9e6a81c22147',
                  'token_type.json':'0a61021438e5ce6041133495f18fc360a6587aea748b17d953f552d2119ba51e',
                  'tokenizer.json':'5a47981b685b75154e29bfb0299584c9b3a4a28679585e86d524c34c065d037f',
                  'chat_template.jinja':'753420ada6b529bbdeefe3c24932f948696a71dd36f54491ec951cbc44f40c16'}
        for n,pin in expected.items():self.assertEqual(hashlib.sha256(outputs['tokenizer/'+n]).hexdigest(),pin)
        self.assertEqual(g.tokenizer_provenance(kv)['incoming_pre'],'joyai-llm')
        self.assertEqual(g.tokenizer_provenance(kv)['emitted_pre'],'deepseek3')
        self.assertEqual(sum(r[4] for r in rows if '.ffn.experts.' in r[0] and r[0].startswith('layers.')),169019965440)

    def test_real_pinned_packer_entire_actual_metadata_no_payload_reads(self):
        model=self.root/'assets/Maya-S';model.mkdir(parents=True)
        draft=model.parent/'dspark';draft.mkdir();vision=self.root/'vision';vision.mkdir()
        gs=self.headers();x=self.fixture
        for h in gs:h.path=model/h.path.name;h.path.write_bytes(b'header-fixture-only')
        (draft/'dspark.json').write_text(json.dumps(x['drafter']));(draft/'dspark.bin').write_bytes(b'placeholder')
        (vision/'vision.json').write_text(json.dumps(x['vision']));(vision/'vision.bin').write_bytes(b'placeholder')
        kv=g.header_set(gs);sizes=[r['asset_stat'][2] for r in x['shards']]+[x['drafter_bytes'],x['vision_bytes']]
        expected,rows,_=g.expected_outputs(self.p,gs,kv,x['drafter'],x['vision'],model,vision,sizes)
        protected={h.path for h in gs}|{draft/'dspark.bin',vision/'vision.bin'}
        actual_open=Path.open
        def metadata_open(path,*args,**kwargs):
            if path in protected:raise AssertionError('tensor payload open attempted')
            return actual_open(path,*args,**kwargs)
        out=self.root/'actual-pack';args=['pack_gguf.py','--model',str(model),'--out',str(out),'--shards',*[h.path.name for h in gs],'--drafter',str(draft/'dspark.json'),'--vision',str(vision)]
        with patch.object(self.p,'Gguf',side_effect=lambda path:copy.deepcopy(next(h for h in gs if h.path==path))), \
             patch.object(self.p.sys,'argv',args),patch.object(Path,'open',metadata_open):
            self.assertEqual(self.p.main(),0)
        self.assertEqual(g.validate_outputs(out,expected),{n:hashlib.sha256(b).hexdigest() for n,b in expected.items()})
        self.assertEqual(len(rows),48795)
        self.assertEqual(sum(p.stat().st_size for p in protected),6*len(b'header-fixture-only')+2*len(b'placeholder'))

    def test_actual_writer_source_and_twelve_gaps(self):
        self.assertEqual(g.sha(g.DRAFTER_WRITER),g.DRAFTER_WRITER_SHA)
        tree=ast.parse(g.DRAFTER_WRITER.read_text())
        self.assertIn(256,[ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ALIGN' for t in n.targets)])
        rows=g.supplemental(self.fixture['drafter'],self.fixture['drafter_bytes'],'drafter')
        layout=g.drafter_layout(rows,self.fixture['drafter_bytes'])
        self.assertEqual((len(rows),len(layout['gaps']),layout['padding_bytes']),(1224,12,2424))
        self.assertEqual({r['bytes'] for r in layout['gaps']},{160,244});self.assertFalse(layout['padding_values_observed'])

    def test_unknown_pre_not_generic_alias(self):
        for pre in ('deepseek-new','joyai-other',None):
            with self.subTest(pre=pre):self.altered_header(lambda k:k.update({'tokenizer.ggml.pre':pre}),'tokenizer pre')
    def test_actual_model_label_changed(self):self.altered_header(lambda k:k.update({'tokenizer.ggml.model':'other'}))
    def test_actual_vocab_changed(self):self.altered_header(lambda k:k['tokenizer.ggml.tokens'].__setitem__(5,'different-unused-word'))
    def test_actual_merges_changed(self):self.altered_header(lambda k:k['tokenizer.ggml.merges'].__setitem__(0,'bad pair'))
    def test_actual_special_changed(self):self.altered_header(lambda k:k.update({'tokenizer.ggml.eos_token_id':2}))
    def test_actual_template_changed_no_baseline_substitution(self):self.altered_header(lambda k:k.update({'tokenizer.chat_template':'{{ messages }}'}))
    def test_actual_token_type_changed(self):self.altered_header(lambda k:k['tokenizer.ggml.token_type'].__setitem__(0,1))
    def test_actual_geometry_changed(self):
        gs=self.headers();gs[0].kv['deepseek41.context_length']=524288
        with self.assertRaisesRegex(ValueError,'geometry'):g.validate_geometry(self.p.geometry(g.header_set(gs),129280))
    def test_actual_missing_role(self):
        gs=self.headers()
        for h in gs:h.tensors=[r for r in h.tensors if r[0]!='blk.0.attn_q_a.weight']
        with self.assertRaisesRegex(ValueError,'mandatory dense'):g.expected_tensors(self.p,gs,gs[0].kv,[],[],['s']*8,[2**50]*8)
    def test_actual_tensor_oob(self):
        gs=self.headers();gs[0].tensors[0][3]=self.fixture['shards'][0]['asset_stat'][2]
        with self.assertRaisesRegex(ValueError,'outside'):g.expected_tensors(self.p,gs,gs[0].kv,[],[],['s']*8,[s['asset_stat'][2] for s in self.fixture['shards']]+[2**50]*2)
    def test_actual_foreign_tensor_role(self):
        gs=self.headers();gs[0].tensors[0][0]='alien.weight'
        with self.assertRaisesRegex(ValueError,'global'):g.expected_tensors(self.p,gs,gs[0].kv,[],[],['s']*8,[2**50]*8)

    def bad_drafter(self,mutate,pattern):
        info=copy.deepcopy(self.fixture['drafter']);mutate(info['tensors'])
        with self.assertRaisesRegex(ValueError,pattern):g.supplemental(info,self.fixture['drafter_bytes'],'drafter')
    def test_actual_drafter_shifted_padding(self):
        self.bad_drafter(lambda r:r[1].__setitem__(2,r[1][2]+1),'alignment')
    def test_actual_drafter_overlap(self):
        self.bad_drafter(lambda r:r[1].__setitem__(2,0),'overlap')
    def test_actual_drafter_internal_expert_gap(self):
        def change(rows):
            row=next(r for r in rows if r[0]=='mtp.0.ffn.experts.1.w1.weight');row[2]+=256
        self.bad_drafter(change,'alignment')
    def test_actual_drafter_expert_ordinal(self):
        def change(rows):
            row=next(r for r in rows if r[0]=='mtp.0.ffn.experts.1.w1.weight');row[0]='mtp.0.ffn.experts.999.w1.weight'
        self.bad_drafter(change,'ordinal')
    def test_actual_drafter_foreign_group(self):
        self.bad_drafter(lambda r:r[0].__setitem__(0,'mtp.3.attn.attn_sink'),'foreign')
    def test_actual_drafter_oob(self):
        self.bad_drafter(lambda r:r[-1].__setitem__(2,self.fixture['drafter_bytes']),'outside')
    def test_actual_drafter_trailing_data(self):
        with self.assertRaisesRegex(ValueError,'trailing'):g.supplemental(self.fixture['drafter'],self.fixture['drafter_bytes']+256,'drafter')
    def test_vision_alignment_holes_not_accepted(self):
        info=copy.deepcopy(self.fixture['vision']);info['tensors'][1][2]+=1
        with self.assertRaisesRegex(ValueError,'gaps/overlap'):g.supplemental(info,self.fixture['vision_bytes'],'vision')


class Construction(Base):
    def exercise(self,mode):
        here=self.root/'family/pack-v3';here.mkdir(parents=True);target=here.parent/'pack-v1/pack-FIRST';target.parent.mkdir();historical=target.parent/'construct-CPU-FIRST';historical.mkdir();(historical/'child.json').write_text('failed-first');assets=here.parent/'assets';model=assets/'Maya-S';model.mkdir(parents=True);draft=assets/'dspark';draft.mkdir();vd=self.root/'vision-assets-1017';vd.mkdir()
        specs=[]
        for i in range(6):
            path='Maya-S/s%d.gguf'%i;(assets/path).write_bytes(b'x');specs.append({'path':path,'size':1,'sha256':hashlib.sha256(b'x').hexdigest()})
        for n,data in [('dspark.bin',b'0'*516),('dspark.json',json.dumps({'tensors':[['mtp.%d.norm.weight'%i,'F32',i*256,4,[1]] for i in range(3)]}).encode())]:
            (draft/n).write_bytes(data);specs.append({'path':'dspark/'+n,'size':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        (vd/'vision.json').write_bytes(b'{}');(vd/'vision.bin').write_bytes(b'v');vp={n:g.sha(vd/n) for n in ('vision.json','vision.bin')}
        receipt={'status':'ALL_EIGHT_ASSETS_VERIFIED_NO_MODEL_RUN','manifest_sha256':g.MANIFEST_SHA,'authorization_sha256':g.AUTH_SHA,'active_inference_authorized':True,'returncode':0,'model_or_service_actions':0,'files':[dict(path=x['path'],bytes=x['size'],sha256=x['sha256'],status='DOWNLOADED_VERIFIED') for x in specs]}
        rp=here/'complete.json';rp.write_text(json.dumps(receipt));m={'files':specs}
        c={'profile':g.PROFILE.copy(),'assets_root':str(assets),'output':str(target),'vision_dir':str(vd),'vision_pins':{str(vd/n):v for n,v in vp.items()},'selected_vision_bin_sha256':vp['vision.bin'],'vision_stats':{str(vd/n):list(g.regular(vd/n)) for n in vp},'acquisition_receipt':str(rp),'acquisition_receipt_sha256':g.sha(rp),'asset_stats':g.path_inventory(assets,m)}
        gs=sparse_headers(model);guard=Mock();argv_before=g.sys.argv;produced=[]
        if mode=='foreign-target':c['output']=str(here/'pack-FIRST')
        if mode=='existing-target':target.mkdir();(target/'keep').write_text('untouched')
        def producer():
            produced.append(True)
            self.assertIn('--shards',g.sys.argv);self.assertIn(str(draft/'dspark.json'),g.sys.argv);self.assertNotIn('--override-experts',g.sys.argv)
            (target/'ds4.txt').write_bytes(b'bad' if mode=='output' else b'metadata')
            if mode=='input':(model/'s0.gguf').write_bytes(b'changed')
            return 0
        pack=SimpleNamespace(ple_to_engram=lambda x:None,int_tensors_to_engram=lambda a,b:None,split_ple=lambda a,b:None,main=producer)
        with patch.object(g,'HERE',here),patch.object(g,'TARGET',target),patch.object(g,'E',self.root),patch.object(g,'VISION_PINS',vp),patch.object(g,'manifest',return_value=m),patch.object(g,'load_packer',return_value=pack),patch.object(g,'Header',side_effect=gs),patch.object(g,'expected_outputs',return_value=({'ds4.txt':b'metadata'},[],{})):
            if mode:
                with self.assertRaises(ValueError):g.construct(c,guard,run=True)
            else:self.assertEqual(g.construct(c,guard,run=True)['status'],'PACK_METADATA_VERIFIED_NO_MODEL_ADMISSION')
        self.assertIs(g.sys.argv,argv_before);self.assertEqual((historical/'child.json').read_text(),'failed-first')
        if mode in ('foreign-target','existing-target'):
            self.assertFalse(produced)
            if mode=='existing-target':self.assertEqual((target/'keep').read_text(),'untouched')
            else:self.assertFalse(target.exists())
        else:self.assertTrue(target.is_dir());self.assertGreater(guard.call_count,1)
    def test_fresh_construction_exact_args_and_postchecks(self):self.exercise('')
    def test_output_corruption_remains_failed(self):self.exercise('output')
    def test_asset_mutation_blocks_success_after_packer(self):self.exercise('input')
    def test_new_namespace_cannot_redirect_pack_target(self):self.exercise('foreign-target')
    def test_existing_old_target_never_adopted(self):self.exercise('existing-target')


class Driver(Base):
    def test_literal_bounds_and_environment(self):
        import run_cpu as d
        with patch.object(d.os,'nice') as nice,patch.object(d.resource,'setrlimit') as limit,patch.object(d.sys,'platform','linux'):
            d.limits();nice.assert_called_once_with(15);self.assertEqual(limit.call_args_list[0].args,(d.resource.RLIMIT_CPU,(30,30)));self.assertEqual(limit.call_args_list[1].args,(d.resource.RLIMIT_AS,(536870912,536870912)))
        self.assertEqual(d.ENV['CUDA_VISIBLE_DEVICES'],'')
    def test_source_review_must_match_before_child(self):
        import run_cpu as d
        r=self.root/'review.json';r.write_text('{}')
        with patch.object(d,'REVIEW',r),self.assertRaisesRegex(ValueError,'review changed'):d.checked('0'*64)
    def test_cleanup_owned_group_only(self):
        import run_cpu as d
        p=Mock(pid=12345)
        with patch.object(d,'gone',side_effect=[False,True,True,True]),patch.object(d.os,'killpg') as kill:
            self.assertEqual(d.cleanup(p),[])
        self.assertTrue(all(c.args[0]==12345 for c in kill.call_args_list));p.wait.assert_called_once()


if __name__=='__main__':unittest.main()
