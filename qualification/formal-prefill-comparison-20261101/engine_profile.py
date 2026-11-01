"""Same qualified native, four explicit pack/TP factors, no timing instrumentation."""
import copy,hashlib,importlib.util,json,re,sys
from pathlib import Path
import short_tasks
R=Path('/home/alex/strata-deepseek-test-20261024');E=R/'reliability-optimization-20261025';P=E/'decode-optimization-20261028/maya145-formal-prefill-v1'
NATIVE=E/'decode-optimization-20261028/maya145-mayas-v1/native-build-r2-FIRST/maya-ds4'
BASE_NORMALIZED='84ebe7a435304f8d1734b8616066edae868b4273a0afec575bd7d3c81159ea6e'
PACKS={'PROD':E/'pack-native-vision-v1','HGU':E/'decode-optimization-20261028/s2-public-hybrid-v1/native-gu-FIRST/pack','UNSLOTH':E/'decode-optimization-20261028/unsloth-pack-v1/pack-r2-FIRST','MS2':E/'decode-optimization-20261028/maya-s-comparison-v1/pack-v1/pack-FIRST','MS1':E/'decode-optimization-20261028/maya-s-comparison-v1/pack-v1/pack-FIRST'}
PARSER_SHA='c43e07ed6a4019fb6252c64d40a0b3cd7a9bfe98e64c36e94436e159406ff983'
def require(ok,msg):
    if not ok:raise ValueError(msg)
def packed(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def factor(variant):
    require(variant in PACKS,'Explicit frozen model/TP factor')
    return {'variant':variant,'tp':1 if variant in ('PROD','MS1') else 2,'native':str(Path('/home/alex/deepseek-hosted-20261025/bin/maya-ds4') if variant=='PROD' else NATIVE),'pack':str(PACKS[variant]),'drafter':'same selected DSpark, enabled' if variant=='PROD' else 'same published Maya-S DSpark, enabled','context_total':1048576,'output_allowance':262144,'effort':100,'prefill_chunk':4096,'expert_copy_io':'unchanged selected loader' if variant=='PROD' else 'DS4_COPY_DIRECT=1','asset_count':None if variant=='PROD' else (9 if variant=='HGU' else 8),'numerical_equivalence_claim':False,'near_full_context_or_output_tested':False}
def profile(base,directory,variant,arm):
    require(hashlib.sha256(packed(base)).hexdigest()==BASE_NORMALIZED,'Exact typed selected4096 base')
    f=factor(variant);a=short_tasks.factor(arm);require(a['profile']==variant,'Exact arm/pack factor')
    directory=Path(directory)
    require(directory.is_absolute() and '..' not in directory.parts and directory.name=='native' and directory.parent.parent==E/'results' and re.fullmatch('maya145-formal-prefill-'+re.escape(arm)+r'-[0-9]{8}T[0-9]{6}Z',directory.parent.name),'Fresh exact short-task namespace')
    c=copy.deepcopy(base);c.update(port=18041,log=str(directory/'engine.log'))
    if variant!='PROD':c.update(exe=str(NATIVE),tokenizer=str(PACKS[variant]/'tokenizer'))
    for key,value in [('--pack',str(PACKS[variant])),('--tp',str(f['tp'])),('--expert-profile',str(directory/'expert-profile.bin'))]:
        require(c['args'].count(key)==1,'One original option '+key);c['args'][c['args'].index(key)+1]=value
    c['args'].append('--verbose')
    for key,tail in [('STRATA_DS4_SLOT_DIR','cache'),('DS4_LANE_CAL','lane.txt'),('DS4_LT_STORE','lt.txt')]:c['env'][key]=str(directory/tail)
    forbidden=('DS4_SERVE_DUMP','DS4_ROUND_LOG','DS4_PROF','DS4_YOCO_KEEP','DS4_DRAFT_VRAM','DS4_TP_SHARES','DS4_DENSE_REQ','DS4_COPY_DIRECT','DS4_TP_GGUF_UNEVEN','DS4_TP_CHECK','DS4_AR2')
    require(not any(k in c['env'] for k in forbidden),'No inherited instrumentation or unfrozen factor')
    if variant!='PROD':c['env']['DS4_COPY_DIRECT']='1'
    if f['tp']==2:c['env'].update(DS4_TP_GGUF_UNEVEN='1',DS4_TP_CHECK='1',DS4_AR2='1')
    return c

def check_profile(base,value,directory,variant,arm):
    require(packed(value)==packed(profile(base,directory,variant,arm)),'Exact full capacity/quality profile');return True

def pack_variant(c):
    require(c['args'].count('--pack')==c['args'].count('--tp')==1,'One pack/TP factor');pack=c['args'][c['args'].index('--pack')+1];tp=c['args'][c['args'].index('--tp')+1]
    matches=[v for v,p in PACKS.items() if str(p)==pack and str(factor(v)['tp'])==tp];require(len(matches)==1,'Explicit model/TP identity');return matches[0]

def startup(log,variant):
    f=factor(variant);path=Path(__file__).resolve().parent.parent/'maya145-directstate-v1/engine_profile.py'
    require(hashlib.sha256(path.read_bytes()).hexdigest()==PARSER_SHA,'Exact qualified pure native startup parser');name='modeltask_current_native_parser'
    if name not in sys.modules:
        s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m)
    m=sys.modules[name];require(Path(m.__file__)==path,'Parser origin');return m.startup(log,'TP'+str(f['tp']))
