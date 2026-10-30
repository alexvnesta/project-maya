"""Maya-S metadata-only pack construction. No model execution or capacity verdict.

construct(..., run=True) is an entry for a separately qualified bounded CPU
controller. The caller supplies a current-owner/resource/phase guard and owns
process deadlines. This module does not import any serving code or open sockets.
"""
from __future__ import annotations
import contextlib
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import sys
import time

HERE = Path(__file__).resolve().parent
TARGET = HERE.parent / 'pack-v1/pack-FIRST'
E = HERE.parents[2]
PACKER = E / 'native-vision-v2/runtime/tools/dsv41/pack_gguf.py'
PACKER_SHA = '6784a50c4252f0d3af36cf04f5d212524dbf0800dac2d3ea633290d044a18fdf'
MANIFEST = HERE.parent / 'ASSET_MANIFEST.json'
MANIFEST_SHA = '22ecce3e7085e29520fadaa67d603beb8cc0905f834ff3563029f6038825034b'
MAX_HEADER = 128 * 1024**2
MAX_METADATA = 32 * 1024**2
MAX_OUTPUT = 64 * 1024**2
TOTAL_ASSETS = 347445667721
VISION_PINS = {'vision.json':'3b682353a9bf572ae2736ec17b946179b24b83319de46c54950f0c442fd13053','vision.bin':'685d935986a030ba1965af5c1e06b55614c7778c821daae1917dde5d2152ff68'}
AUTH_SHA = 'cb2698ff10b5bd42b029968f20f59aa78d3d6924b4b8a4b5548bc3b28e78ce5a'
# This exact published tokenizer, including its own template, is reviewed.
# pack_gguf writes deepseek3; ST and llama.cpp commita34de861 share JoyAI's
# sequential three-regex family. No incoming metadata or template is replaced.
JOYAI_FINGERPRINT = '818b515300459e38c486089ad775fe78b3e06e9032cd507ceca343db32196ddd'
METADATA_FIXTURE = HERE.parent / 'pack-v2/published-metadata-EXPORTED-v2.json'
METADATA_FIXTURE_SHA = '50d2ee88c136d7cbbde62ef62b908571741e8fed94f6ac055cda5c65608029f9'
DRAFTER_WRITER = E / 'native-vision-v2/runtime/tools/dsv41/drafter_pack.py'
DRAFTER_WRITER_SHA = 'c2acc64df00fd4157409890b4fcec485876ba9fb4b266303bd8e9ee97b2084c5'
# GGML types understood by this pinned packer, plus explicitly recognized integer metadata.
TYPES = {0:('F32',1,4),1:('F16',1,2),8:('Q8_0',32,34),30:('BF16',1,2),39:('MXFP4',32,17),67:('MXFP8',32,33),43:('MXFP8',32,33),10:('Q2_K',256,84),11:('Q3_K',256,110),12:('Q4_K',256,144),13:('Q5_K',256,176),14:('Q6_K',256,210),16:('IQ2_XXS',256,66),17:('IQ2_XS',256,74),18:('IQ3_XXS',256,98),20:('IQ4_NL',32,18),21:('IQ3_S',256,110),22:('IQ2_S',256,82),23:('IQ4_XS',256,136),19:('IQ1_S',256,50),29:('IQ1_M',256,56),145:('TQK6',128,26),146:('TQK7',128,30),224:('TQK5X',128,22),225:('TQK4X',128,18),226:('TQK5T',128,22),227:('TQK4T',128,18)}
BY_NAME = {v[0]: v[1:] for v in TYPES.values()}
INT_TYPES = {24:1,25:2,26:4,27:8,28:8}
INTEGER_METADATA = {'engram_token_map.weight':26, 'engram_primes.weight':27, 'engram_offsets.weight':27, 'engram_multipliers.weight':27}
GEOMETRY = {'vocab_size':129280,'hidden_size':5120,'num_hidden_layers':40,'n_routed_experts':384,'num_experts_per_tok':6,'moe_intermediate_size':2304,'num_attention_heads':64,'head_dim':512,'qk_rope_head_dim':64,'q_lora_rank':1280,'o_lora_rank':1024,'o_groups':8,'hc_mult':4,'sliding_window':128,'max_position_embeddings':1048576,'dspark_block_size':5,'dspark_n_routed_experts':128,'dspark_num_experts_per_tok':3,'dspark_markov_rank':256,'dspark_noise_token_id':128799}
PROFILE = {'context':1048576,'output_allowance':262144,'max_tokens':32768,'effort':100,'reason_budget':0,'chunk':4096,'cpu_threads':24,'tp':1,'reserve_per_device':2048,'q8_batch':1,'q8_check':1,'mode':1,'stream':0,'dspark_conf':0.65,'dspark_max':4,'dspark_cum':0.0,'all_cpu_experts_ram':True,'images':True,'fit':False,'projection_layer':22,'projection_scale':1.0}


def require(ok, message):
    if not ok: raise ValueError(message)


def integer(x, lo=0, hi=2**63-1):
    require(type(x) is int and lo <= x <= hi, 'integer bound/type')
    return x


def packed(x):
    return json.dumps(x, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def pairs(xs):
    out = {}
    for k,v in xs:
        require(k not in out, 'duplicate JSON key')
        out[k] = v
    return out


def read_json(path):
    regular(path); require(path.stat().st_size <= MAX_METADATA, 'metadata bound')
    return json.loads(path.read_text(), object_pairs_hook=pairs, parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def canonical(path):
    path = Path(path)
    require(path.is_absolute() and str(path) == os.path.normpath(str(path)), 'absolute canonical path required')
    # Check every ancestor lexically before any resolve; never follow an alias.
    for p in reversed((path, *path.parents)):
        if p.exists() or p.is_symlink(): require(not p.is_symlink(), 'path symlink')
    return path


def regular(path):
    path = canonical(path); s = path.lstat()
    require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, 'regular exclusive-link file required')
    return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)


def sha(path, guard=lambda: None, limit=MAX_METADATA):
    before=regular(path); require(before[2] <= limit, 'hash exceeds metadata bound')
    h=hashlib.sha256()
    with path.open('rb') as f:
        while True:
            guard(); b=f.read(1024**2)
            if not b: break
            h.update(b)
    require(regular(path)==before,'input changed during hash')
    return h.hexdigest()


def load_packer():
    require(sha(PACKER)==PACKER_SHA,'packer source changed')
    spec=importlib.util.spec_from_file_location('_maya_s_pinned_packer',PACKER)
    p=importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
    require(Path(p.__file__)==PACKER and sha(PACKER)==PACKER_SHA,'packer origin/source')
    return p


class Header:
    """Strict bounded GGUF directory reader; tensor payloads are never read."""
    def __init__(self, path, guard=lambda: None):
        self.path=canonical(path); before=regular(path); self.guard=guard; self.next_guard=0.0
        with path.open('rb') as self.f:
            require(self.take(4)==b'GGUF','GGUF magic')
            version,nt,nkv=self.unpack('<IQQ'); require(version==3,'GGUF version')
            integer(nt,1,100000);integer(nkv,1,8192);self.kv={};self.tensors=[]
            for _ in range(nkv):
                name=self.string();require(name not in self.kv,'duplicate GGUF key')
                self.kv[name]=self.value(self.unpack('<I')[0])
            names=set()
            for _ in range(nt):
                name=self.string();require(name and name not in names and not any(c.isspace() for c in name),'duplicate/invalid tensor name');names.add(name)
                nd=self.unpack('<I')[0];integer(nd,1,4)
                dims=list(self.unpack('<'+'Q'*nd));[integer(d,1,2**40) for d in dims]
                typ,off=self.unpack('<IQ');self.tensors.append((name,typ,dims,off))
            alignment=self.kv.get('general.alignment',32);integer(alignment,1,4096);require(alignment&(alignment-1)==0,'alignment power of two')
            self.data_start=(self.f.tell()+alignment-1)//alignment*alignment
        del self.f
        intervals=[]
        for name,typ,dims,off in self.tensors:
            if typ in TYPES:
                _,per,bpb=TYPES[typ];require(dims[0]%per==0,'quant row not block divisible');nb=math.prod(dims)//per*bpb
            else:
                require(INTEGER_METADATA.get(name)==typ and typ in INT_TYPES,'unsupported type/metadata role');nb=math.prod(dims)*INT_TYPES[typ];require(nb<=MAX_METADATA,'integer metadata payload bound')
            integer(nb,1);require(off%alignment==0,'tensor offset alignment')
            start=self.data_start+off;require(start+nb<=before[2],'tensor outside asset');intervals.append((start,start+nb))
        intervals.sort();require(all(a[1]<=b[0] for a,b in zip(intervals,intervals[1:])),'overlapping tensor intervals')
        require(regular(path)==before,'GGUF changed while reading');self.stat=before
    def take(self,n):
        integer(n,0,MAX_HEADER);require(self.f.tell()+n<=MAX_HEADER,'header bound');
        if time.monotonic()>=self.next_guard: self.guard();self.next_guard=time.monotonic()+1.0
        b=self.f.read(n);require(len(b)==n,'truncated header');return b
    def unpack(self,fmt): return struct.unpack(fmt,self.take(struct.calcsize(fmt)))
    def string(self):
        n=self.unpack('<Q')[0];integer(n,0,8*1024**2);return self.take(n).decode('utf-8','strict')
    def value(self,t,depth=0):
        fmt={0:'B',1:'b',2:'H',3:'h',4:'I',5:'i',6:'f',7:'B',10:'Q',11:'q',12:'d'}
        if t in fmt:
            v=self.unpack('<'+fmt[t])[0]
            if t==7: require(v in (0,1),'invalid GGUF bool');return bool(v)
            if isinstance(v,float):require(math.isfinite(v),'nonfinite metadata')
            return v
        if t==8:return self.string()
        require(t==9 and depth==0,'unknown/nested array type');at,n=self.unpack('<IQ');integer(n,0,2000000);require(at!=9,'nested array');return [self.value(at,depth+1) for _ in range(n)]


def header_set(gs):
    require(len(gs)==6,'exact six shards')
    names=set();base=gs[0].kv;count=0
    require(base.get('general.architecture')=='deepseek41','base architecture')
    for i,g in enumerate(gs):
        k=g.kv
        # Published later shards may contain only the three split keys.
        # An explicit null or conflicting architecture is not absence.
        if 'general.architecture' in k:require(k['general.architecture']=='deepseek41','architecture')
        require(type(k.get('split.no')) is int and k['split.no']==i and k.get('split.count')==6,'split index/count')
        for key,v in k.items():
            if key.startswith(('deepseek41.','tokenizer.')):require(key in base and packed(v)==packed(base[key]),'inconsistent shard metadata')
        for name,typ,dims,off in g.tensors:
            require(name not in names,'duplicate tensor across shards');names.add(name);count+=1
    require(type(base.get('split.tensors.count')) is int and base['split.tensors.count']==count,'split total count')
    for g in gs:require(g.kv.get('split.tensors.count',count)==count,'inconsistent tensor count')
    tokens=base.get('tokenizer.ggml.tokens');require(isinstance(tokens,list) and len(tokens)==129280 and all(type(t)is str for t in tokens) and len(set(tokens))==len(tokens),'vocabulary')
    tokenizer_provenance(base)
    template=base.get('tokenizer.chat_template');require(type(template)is str and template and '\x00' not in template,'missing/invalid native chat template')
    types=base.get('tokenizer.ggml.token_type');require(isinstance(types,list) and len(types)==len(tokens) and all(type(t)is int for t in types),'token types')
    require(isinstance(base.get('tokenizer.ggml.merges'),list) and all(type(t)is str and '\n' not in t for t in base['tokenizer.ggml.merges']),'merges')
    for k in ('bos_token_id','eos_token_id','padding_token_id'):integer(base.get('tokenizer.ggml.'+k),0,len(tokens)-1)
    return base


def tokenizer_provenance(kv):
    pre=kv.get('tokenizer.ggml.pre')
    require(pre in ('deepseek3','joyai-llm'),'tokenizer pre')
    fingerprint=hashlib.sha256(packed({k:v for k,v in kv.items() if k.startswith('tokenizer.')})).hexdigest()
    if pre=='joyai-llm':
        require(kv.get('tokenizer.ggml.model')=='gpt2' and fingerprint==JOYAI_FINGERPRINT,
                'published JoyAI tokenizer fingerprint')
    return {'incoming_pre':pre,'emitted_pre':'deepseek3','incoming_tokenizer_sha256':fingerprint,
            'template_sha256':hashlib.sha256((kv.get('tokenizer.chat_template') if type(kv.get('tokenizer.chat_template')) is str else '').encode()).hexdigest(),
            'packer_sha256':PACKER_SHA,'normalization':'existing pinned packer; original tokenizer/template retained'}


def validate_geometry(geo):
    for k,v in GEOMETRY.items():require(packed(geo.get(k))==packed(v),'trunk/DSpark geometry '+k)
    require(geo.get('dspark_target_layer_ids')==[37,38,39],'draft target layers')
    require(geo.get('engram_layer_ids')==[1,14],'Engram layers')
    for k in ('compress_ratios','kv_source_layer_ids','index_source_layer_ids'):
        require(isinstance(geo.get(k),list) and bool(geo[k]) and all(type(x)is int and x>=0 for x in geo[k]),'missing cache geometry')
    require(len(geo['compress_ratios'])>=40,'compress geometry length')


def tensor_record(name,dt,off,nb,shape,size):
    require(type(name)is str and name and not any(c.isspace() for c in name),'tensor name')
    require(dt in BY_NAME and isinstance(shape,list) and 1<=len(shape)<=4,'tensor type/shape');[integer(d,1,2**40) for d in shape]
    integer(off);integer(nb,1);per,bpb=BY_NAME[dt];require(shape[-1]%per==0 and math.prod(shape)//per*bpb==nb,'tensor byte geometry')
    require(off+nb<=size,'tensor offset outside binary')
    return (name,dt,off,nb,shape)


def supplemental(info,size,kind):
    require(isinstance(info,dict) and isinstance(info.get('tensors'),list),'supplement tensor metadata')
    rows=[];names=set();intervals=[]
    for r in info['tensors']:
        require(isinstance(r,list) and len(r)==5,'supplement record')
        name,dt,off,nb,shape=tensor_record(*r,size)
        require(name not in names,'duplicate supplemental tensor');names.add(name)
        require(bool(re.fullmatch(r'mtp\.[012]\..+',name)) if kind=='drafter' else name.startswith(('vision.','aligner.')) or name in ('image_start','image_end','image_newline'),'foreign supplemental role')
        rows.append((name,dt,off,nb,shape));intervals.append((off,off+nb))
    if kind=='drafter':drafter_layout(rows,size)
    else:
        intervals.sort();require(intervals and intervals[0][0]==0 and all(a[1]==b[0] for a,b in zip(intervals,intervals[1:])) and intervals[-1][1]==size,'supplement gaps/overlap/trailing bytes')
    if kind=='drafter':require(all(any(n.startswith('mtp.%d.'%i) for n in names) for i in range(3)),'missing drafter block')
    else:require(isinstance(info.get('config'),dict) and info['config'].get('image_token_id')==129264,'vision config')
    return rows


def drafter_layout(rows,size):
    """Exact requant writer layout: ALIGN256 before dense/new expert role.

    Same-role experts0..127 are adjacent. Padding is unreferenced; its byte
    values are not inspected or asserted here. Full acquisition SHA owns bytes.
    """
    end=0;previous=None;groups={};gaps=[]
    for name,dt,off,nb,shape in rows:
        match=re.fullmatch(r'mtp\.([012])\.ffn\.experts\.(\d+)\.(w[123])\.weight',name)
        require('.ffn.experts.' not in name or match is not None,'foreign expert role')
        group=(int(match[1]),match[3]) if match else None
        require(off>=end,'drafter overlap/order')
        start=end if group is not None and group==previous else (end+255)//256*256
        require(off==start,'drafter writer alignment/gap')
        if off>end:gaps.append({'offset':end,'bytes':off-end})
        if group is not None:
            if group!=previous:require(group not in groups,'expert group revisited')
            entries=groups.setdefault(group,[])
            require(int(match[2])==len(entries) and len(entries)<128,'expert ordinal/count')
            if entries:require((dt,nb,shape)==entries[0],'expert group geometry/type')
            entries.append((dt,nb,shape))
        end=off+nb;previous=group
    require(bool(rows) and rows[0][2]==0 and end==size,'drafter trailing bytes/empty')
    if groups:
        require(set(groups)=={(i,r) for i in range(3) for r in ('w1','w2','w3')}
                and all(len(v)==128 for v in groups.values()),'missing expert group/count')
    return {'alignment':256,'padding_bytes':sum(r['bytes'] for r in gaps),'gaps':gaps,
            'padding_values_observed':False,'writer_sha256':DRAFTER_WRITER_SHA}


def expected_tensors(p,gs,kv,drafter,vision,files,sizes):
    rows=[]
    for fi,g in enumerate(gs):
        for name,typ,dims,off in g.tensors:
            if typ not in TYPES:require(INTEGER_METADATA.get(name)==typ,'unknown skipped metadata');continue
            dt,per,bpb=TYPES[typ];shape=list(reversed(dims));nb=math.prod(dims)//per*bpb;start=g.data_start+off
            m=re.fullmatch(r'blk\.(\d+)\.(.+)',name)
            if m: require(int(m[1])<40 and m[2] in p.LAYER,'unknown layer tensor');ck='layers.'+m[1]+'.'+p.LAYER[m[2]]
            else:require(name in p.GLOBAL,'unknown global tensor');ck=p.GLOBAL[name]
            if '.ffn.experts.' in ck:
                require(len(shape)==3 and shape[0]==384,'expert count')
                role=ck.rsplit('.',1)[1];require(shape[1:]==([5120,2304] if role=='w2' else [2304,5120]),'expert role dimensions')
                for i in range(384):rows.append((ck.rsplit('.',1)[0]+'.'+str(i)+'.'+role+'.weight',dt,fi,start+i*(nb//384),nb//384,shape[1:]))
            elif ck.endswith('.attn.wo_a.slice'):
                if len(shape)==3 and shape[0]==8:shape=[shape[0]*shape[1],shape[2]]
                require(len(shape)==2 and shape[0]%8==0 and nb%8==0,'output group shape')
                for i in range(8):rows.append((ck+'.%d.weight'%i,dt,fi,start+i*(nb//8),nb//8,[shape[0]//8,shape[1]]))
            else:rows.append((ck,dt,fi,start,nb,shape))
    for fi,records in ((6,drafter),(7,vision)):
        for name,dt,off,nb,shape in records:
            if fi==6 and name.endswith('.attn.wo_a.weight'):
                require(len(shape)==2 and shape[0]%8==0 and nb%8==0,'drafter output groups')
                for i in range(8):rows.append((name[:-7]+'.slice.%d.weight'%i,dt,fi,off+i*(nb//8),nb//8,[shape[0]//8,shape[1]]))
            else:rows.append((name,dt,fi,off,nb,shape))
    names={}
    for name,dt,fi,off,nb,shape in rows:
        require(name not in names,'duplicate mapped tensor');tensor_record(name,dt,off,nb,shape,sizes[fi]);names[name]=(dt,shape)
    for name,shape in {'embed.weight':[129280,5120],'head.weight':[129280,5120],'norm.weight':[5120]}.items():require(name in names and names[name][1]==shape,'global geometry '+name)
    for il in range(40):
        for e in range(384):
            for role in ('w1','w2','w3'):require('layers.%d.ffn.experts.%d.%s.weight'%(il,e,role) in names,'missing expert role')
    # Mandatory selected-loader roles (dfe326, lines4396-4432). Shape-specific
    # cache allocations remain a separate source/capacity review, not a fit claim.
    base_roles=('attn.wq_a.weight','attn.wq_b.weight','attn.wkv.weight','attn.wo_b.weight','attn.q_norm.weight','attn.kv_norm.weight','attn.attn_sink','attn_norm.weight','ffn_norm.weight','hc_attn_fn','hc_attn_scale','hc_attn_base','hc_ffn_fn','hc_ffn_scale','hc_ffn_base','ffn.gate.weight','ffn.gate.bias','ffn.shared_experts.w1.weight','ffn.shared_experts.w2.weight','ffn.shared_experts.w3.weight')
    for il in range(40):
        for role in base_roles+tuple('attn.wo_a.slice.%d.weight'%i for i in range(8)):
            require('layers.%d.%s'%(il,role) in names,'missing mandatory dense role')
    for il in (1,14):require('layers.%d.engram.embed.weight'%il in names and names['layers.%d.engram.embed.weight'%il][0]=='Q6_K','published Engram Q6_K missing')
    require(len(files)==8,'foreign pack source file')
    return rows


def engram_bytes(kv):
    get=lambda k:kv['deepseek41.engram.'+k]
    layers=get('layers');require(layers==[1,14],'Engram layer map')
    ngram,heads,hd=(integer(get(k),1,1024) for k in ('max_ngram_size','head_count','head_dim'))
    tm=get('token_map');require(isinstance(tm,list) and 0<len(tm)<=129280 and all(type(x)is int and 0<=x<129280 for x in tm),'Engram token map')
    pad=tm[integer(get('pad_token_id'),0,len(tm)-1)];tm=tm+[0]*(129280-len(tm));mult=get('multipliers');primes=get('primes');offs=get('offsets');cols=(ngram-1)*heads
    require(len(mult)==2*ngram and len(primes)==len(offs)==2*cols,'Engram hash geometry')
    require(all(type(x)is int and 0<=x<2**63 for x in mult+primes+offs),'Engram integer parameters')
    return struct.pack('<4s6i',b'DSE1',129280,2,ngram,heads,hd,pad)+struct.pack('<129280i',*tm)+b''.join(struct.pack('<%dq'%len(x),*x) for x in (mult,primes,offs))


def expected_outputs(p,gs,kv,di,vi,model,vision_dir,sizes):
    geo=p.geometry(kv,129280);validate_geometry(geo)
    files=[g.path.name for g in gs]+['../dspark/dspark.bin',os.path.relpath(vision_dir/'vision.bin',model)]
    require(all(not any(c.isspace() for c in x) for x in files),'whitespace file path')
    dr=supplemental(di,sizes[6],'drafter');vr=supplemental(vi,sizes[7],'vision')
    rows=expected_tensors(p,gs,kv,dr,vr,files,sizes)
    lines=[]
    for k,v in geo.items():
        if v is not None:lines.append(k+' '+(','.join(map(str,v)) if isinstance(v,list) else str(int(v) if isinstance(v,bool) else v)))
    require(not(set(geo)&set(vi['config'])),'vision/trunk key collision')
    lines.extend(k+' '+str(v) for k,v in vi['config'].items());lines+=['format gguf','model_dir '+str(model)]
    tt=['file %d %s'%(i,n) for i,n in enumerate(files)]
    tt+=['t %s %s %d %d %d %s'%(n,dt,fi,o,nb,' '.join(map(str,sh))) for n,dt,fi,o,nb,sh in rows]
    tokens=kv['tokenizer.ggml.tokens'];types=kv['tokenizer.ggml.token_type'];special={k:int(kv['tokenizer.ggml.'+v]) for k,v in [('bos','bos_token_id'),('eos','eos_token_id'),('pad','padding_token_id')]}
    outputs={'ds4.txt':('\n'.join(lines)+'\n').encode(),'tensors.txt':('\n'.join(tt)+'\n').encode(),'engram.bin':engram_bytes(kv),'tokenizer/vocab.json':json.dumps({t:i for i,t in enumerate(tokens)},ensure_ascii=False).encode(),'tokenizer/merges.txt':'\n'.join(kv['tokenizer.ggml.merges']).encode(),'tokenizer/token_type.json':json.dumps(types).encode(),'tokenizer/tokenizer.json':json.dumps({'pre':'deepseek3','special_ids':special},indent=1).encode(),'tokenizer/chat_template.jinja':kv['tokenizer.chat_template'].encode()}
    return outputs,rows,geo


def capacity_inputs(rows,geo):
    groups={'routed':0,'dense':0,'drafter':0,'vision':0,'engram':0};experts={};types={}
    for name,dt,fi,off,nb,shape in rows:
        m=re.fullmatch(r'layers\.(\d+)\.ffn\.experts\.(\d+)\.w[123]\.weight',name)
        kind='routed' if m else 'drafter' if name.startswith('mtp.') else 'vision' if fi==7 else 'engram' if '.engram.embed.' in name else 'dense'
        groups[kind]+=nb;types[dt]=types.get(dt,0)+nb
        if m:
            key=m[1]+':'+m[2];experts[key]=experts.get(key,0)+nb
    return {'tensor_payload_bytes':groups,'per_expert_three_role_bytes':experts,'bytes_by_type':types,'geometry':geo,'fit_verdict':'UNPROVEN_REQUIRES_SELECTED_SOURCE_CAPACITY_AND_ACTUAL_STATIC_RESOURCE_REVIEW','limits_preserved':PROFILE,'notes':['Byte counts are file payloads, not RAM/VRAM allocations.','No 1M-fill or 262144-generation qualification; no placement inference.']}


def profile_contract(profile):require(packed(profile)==packed(PROFILE),'profile/policy change')


def manifest():
    require(sha(MANIFEST)==MANIFEST_SHA,'manifest pin');m=read_json(MANIFEST)
    require(len(m['files'])==8 and sum(x['size'] for x in m['files'])==TOTAL_ASSETS,'inventory')
    return m


def receipt_contract(receipt,m,root):
    require(receipt.get('status')=='ALL_EIGHT_ASSETS_VERIFIED_NO_MODEL_RUN' and receipt.get('authorization_sha256')==AUTH_SHA and receipt.get('active_inference_authorized') is True and type(receipt.get('returncode')) is int and receipt['returncode']==0 and type(receipt.get('model_or_service_actions')) is int and receipt['model_or_service_actions']==0 and receipt.get('manifest_sha256')==MANIFEST_SHA,'completed asset receipt required')
    rows=receipt.get('files');require(isinstance(rows,list) and len(rows)==8,'complete asset receipts')
    require({x['path']:x['sha256'] for x in rows}=={x['path']:x['sha256'] for x in m['files']},'asset receipt hash map')
    for x in rows:
        expected=next(y for y in m['files'] if y['path']==x['path']);require(type(x.get('bytes')) is int and x['bytes']==expected['size'] and x.get('status') in ('DOWNLOADED_VERIFIED','VERIFIED_EXISTING'),'asset size/status receipt')
    # Full asset hashes must already have been verified by the admitted acquisition.
    # The separately pinned custody snapshot brackets stat identity of all eight files.
    return {str(root/x['path']):x['sha256'] for x in m['files']}


def path_inventory(root,m):
    root=canonical(root);require(root.is_dir(),'assets root');allowed={x['path'] for x in m['files']};found=set()
    for base,dirs,files in os.walk(root,followlinks=False):
        for d in dirs:
            directory=canonical(Path(base)/d);require(directory in (root/'Maya-S',root/'dspark'),'foreign asset directory')
        for name in files:
            path=Path(base)/name;regular(path);found.add(str(path.relative_to(root)))
    require(found==allowed,'foreign/missing asset or override')
    # Packer inspects only model/parent and model/Engram. The exact inventory rules
    # exclude dspark-*.gguf, mmproj*.gguf, Engram, overrides, and all partials.
    require({x.name for x in root.iterdir()}=={'Maya-S','dspark'},'foreign sibling directory')
    return {str(root/x['path']):list(regular(root/x['path'])) for x in m['files']}


def validate_outputs(out,expected):
    found=set();total=0
    for base,dirs,files in os.walk(out,followlinks=False):
        for d in dirs:canonical(Path(base)/d)
        for name in files:
            p=Path(base)/name;s=regular(p);total+=s[2];require(total<=MAX_OUTPUT,'output metadata budget');key=str(p.relative_to(out));found.add(key)
            require(key in expected and p.read_bytes()==expected[key],'pack output bytes/reference changed')
    require(found==set(expected),'missing pack outputs')
    return {k:hashlib.sha256(v).hexdigest() for k,v in expected.items()}


def construct(contract,guard,*,run=False):
    """Metadata only; outer qualified controller supplies bounds/custody and guard.

    contract itself must be an immutable qualification input. acquisition_receipt,
    asset_stats and all vision pins are mandatory; no payload hash is performed
    here. A changed stat identity requires a separately authorized full hash.
    """
    require(run is True and callable(guard),'explicit qualified run/guard required');guard()
    profile_contract(contract['profile']);m=manifest();root=canonical(Path(contract['assets_root']));out=canonical(Path(contract['output']));vdir=canonical(Path(contract['vision_dir']))
    require(root==HERE.parent/'assets' and out==TARGET and not out.exists() and out.parent.is_dir(),'fresh exact assets/output namespace required')
    require(vdir==E/'vision-assets-1017','same selected vision directory required')
    for name in ('vision.json','vision.bin'):
        require(contract['vision_pins'].get(str(vdir/name))==VISION_PINS[name],'selected vision pin required')
    require(contract['vision_pins'][str(vdir/'vision.bin')]==contract['selected_vision_bin_sha256'],'selected vision mismatch')
    rp=canonical(Path(contract['acquisition_receipt']));require(sha(rp,guard)==contract['acquisition_receipt_sha256'],'receipt changed');receipt_contract(read_json(rp),m,root)
    before=path_inventory(root,m);require(before==contract['asset_stats'],'asset stat custody changed')
    for x in m['files']:require(before[str(root/x['path'])][2]==x['size'],'asset stat size')
    vision_before={str(vdir/n):list(regular(vdir/n)) for n in ('vision.json','vision.bin')};require(vision_before==contract['vision_stats'],'vision stat custody changed')
    require(sha(vdir/'vision.json',guard)==contract['vision_pins'][str(vdir/'vision.json')],'vision metadata changed')
    guard();p=load_packer();gs=[Header(root/x['path'],guard) for x in m['files'][:6]];kv=header_set(gs)
    # Exact pinned normalization; bounded integer tensors only, never expert weights.
    p.ple_to_engram(kv);p.int_tensors_to_engram(gs,kv)
    for g in gs:p.split_ple(g,kv)
    di=read_json(root/'dspark/dspark.json');require(sha(root/'dspark/dspark.json',guard)==m['files'][7]['sha256'],'drafter metadata changed');vi=read_json(vdir/'vision.json')
    sizes=[x['size'] for x in m['files'][:6]]+[m['files'][6]['size'],vision_before[str(vdir/'vision.bin')][2]]
    expected,rows,geo=expected_outputs(p,gs,kv,di,vi,root/'Maya-S',vdir,sizes)
    require(sum(map(len,expected.values()))<=MAX_OUTPUT,'metadata budget');guard();require(path_inventory(root,m)==before,'assets changed before construction')
    out.mkdir();old=sys.argv;stream=io.StringIO()
    try:
        sys.argv=[str(PACKER),'--model',str(root/'Maya-S'),'--out',str(out),'--shards',*[x['path'].split('/')[1] for x in m['files'][:6]],'--drafter',str(root/'dspark/dspark.json'),'--vision',str(vdir)]
        with contextlib.redirect_stdout(stream):require(p.main()==0,'packer return')
    finally:sys.argv=old
    guard();require(path_inventory(root,m)==before,'asset custody changed after pack');require({str(vdir/n):list(regular(vdir/n)) for n in ('vision.json','vision.bin')}==vision_before,'vision custody changed')
    require(sha(PACKER,guard)==PACKER_SHA,'packer changed after run');hashes=validate_outputs(out,expected)
    return {'status':'PACK_METADATA_VERIFIED_NO_MODEL_ADMISSION','output_sha256':hashes,'asset_sha256':{x['path']:x['sha256'] for x in m['files']},'capacity_inputs':capacity_inputs(rows,geo),'packer_sha256':PACKER_SHA,'stdout':stream.getvalue(),'asset_stats':before,'vision_stats':vision_before,'tokenizer_provenance':tokenizer_provenance(kv),'drafter_layout':drafter_layout(supplemental(di,sizes[6],'drafter'),sizes[6])}


if __name__=='__main__':
    raise SystemExit('Source-only library. Invoke construct(run=True) only through a separately qualified bounded pack controller; no standalone action authority.')
