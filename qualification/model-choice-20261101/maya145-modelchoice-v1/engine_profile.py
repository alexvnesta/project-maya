"""Two new public weight packs, same compiled native and full serving policy.

Pure profile helpers. This file grants no model or GPU admission.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

R=Path('/home/alex/strata-deepseek-test-20261024')
E=R/'reliability-optimization-20261025'
P=E/'decode-optimization-20261028/maya145-modelchoice-v1'
NATIVE=E/'decode-optimization-20261028/maya145-mayas-v1/native-build-r2-FIRST/maya-ds4'
BASE_NORMALIZED='84ebe7a435304f8d1734b8616066edae868b4273a0afec575bd7d3c81159ea6e'
PACKS={'HGU':E/'decode-optimization-20261028/s2-public-hybrid-v1/native-gu-FIRST/pack',
       'UNSLOTH':E/'decode-optimization-20261028/unsloth-pack-v1/pack-r2-FIRST'}
PARSER_SHA='c43e07ed6a4019fb6252c64d40a0b3cd7a9bfe98e64c36e94436e159406ff983'

def require(ok,msg):
    if not ok:raise ValueError(msg)
def packed(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def factor(variant):
    require(variant in PACKS,'Two exact new public pack factors only')
    return {'variant':variant,'tp':2,'native':str(NATIVE),'pack':str(PACKS[variant]),
        'drafter':'same published Maya-S DSpark, enabled','context_total':1048576,'output_allowance':262144,
        'effort':100,'prefill_chunk':4096,'numerical_equivalence_claim':False,'runtime_fit_claim':False,
        'expert_copy_io':'DS4_COPY_DIRECT=1','exact_private_S2':False,'asset_count':9 if variant=='HGU' else 8}

def profile(base,directory,variant):
    require(hashlib.sha256(packed(base)).hexdigest()==BASE_NORMALIZED,'Exact selected4096 base typed config')
    f=factor(variant);directory=Path(directory)
    require(directory.is_absolute() and '..' not in directory.parts and directory.name=='native'
        and directory.parent.parent==E/'results'
        and re.fullmatch(r'maya145-modelchoice-(?:HGU|UNSLOTH)-[0-9]{8}T[0-9]{6}Z',directory.parent.name)
        and directory.parent.name.startswith('maya145-modelchoice-'+variant+'-'),'Fresh exact candidate namespace')
    out=copy.deepcopy(base)
    out.update(exe=str(NATIVE),tokenizer=str(PACKS[variant]/'tokenizer'),port=18041,log=str(directory/'engine.log'))
    for key,value in [('--pack',str(PACKS[variant])),('--tp','2'),('--expert-profile',str(directory/'expert-profile.bin'))]:
        require(out['args'].count(key)==1,'Unique original native option: '+key)
        out['args'][out['args'].index(key)+1]=value
    out['args'].append('--verbose')
    for key,tail in [('STRATA_DS4_SLOT_DIR','cache'),('DS4_LANE_CAL','lane.txt'),('DS4_LT_STORE','lt.txt')]:out['env'][key]=str(directory/tail)
    require(not any(k in out['env'] for k in ['DS4_SERVE_DUMP','DS4_ROUND_LOG','DS4_YOCO_KEEP','DS4_DRAFT_VRAM','DS4_TP_SHARES','DS4_DENSE_REQ','DS4_COPY_DIRECT']),'Unfrozen profile factor')
    out['env'].update(DS4_TP_GGUF_UNEVEN='1',DS4_TP_CHECK='1',DS4_AR2='1',DS4_COPY_DIRECT='1',
        DS4_SERVE_DUMP=str(directory/'logits'),DS4_ROUND_LOG=str(directory/'rounds.tsv'))
    return out

def check_profile(base,value,directory,variant):
    require(packed(value)==packed(profile(base,directory,variant)),'Exact new pack/fullpolicy profile')
    return True

def pack_variant(c):
    require(c['args'].count('--pack')==1,'One pack')
    path=c['args'][c['args'].index('--pack')+1]
    found=[v for v,p in PACKS.items() if str(p)==path]
    require(len(found)==1,'Explicit candidate pack only')
    return found[0]

def startup(log,variant):
    factor(variant)
    path=Path(__file__).resolve().parent.parent/'maya145-directstate-v1/engine_profile.py'
    require(hashlib.sha256(path.read_bytes()).hexdigest()==PARSER_SHA,'Unchanged current-native startup parser')
    name='model_choice_current_native_startup_parser';m=sys.modules.get(name)
    if m is None:
        s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m)
    require(Path(m.__file__)==path,'Exact pure startup parser origin')
    # Parser consumes actual per-device Q8/projection/TP2/placement evidence.
    # Its old model factor is not substituted for this candidate's config or INFO.
    return m.startup(log,'TP2')
