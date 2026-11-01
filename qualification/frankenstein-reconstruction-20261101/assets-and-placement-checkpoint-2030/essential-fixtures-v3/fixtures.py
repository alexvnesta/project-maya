"""Actual pack/tokenizer CPU encoding of the frozen B0/A0 essential requests.

No model, native process, GPU or Hosting entry point. Reuses the exact qualified
API picker and MockEngine tokenizer/vision prompt encoder. Original modules and
their globals are unchanged. FIRST controls publish both exact manifests only
after source/input checks and all focused controls pass.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

HERE=Path(__file__).resolve().parent
Q=HERE.parent
DC=Q.parent
E=DC.parent
RUNTIME=Q/'essential-runtime-v2/runtime.py'
RUNTIME_SHA='65f23d800bc4f749abd78c42aa06d7c4dcdeabde66318a63965649dfa159a0cf'
FIXTURE=DC/'maya-s-comparison-v1/model-v1/ms_fixtures.py'
FIXTURE_SHA='76e3731d48792545b6135f335df60e9d9b4e7266ce23e70a3093a9916b74a869'
CONSTRUCTOR=Q/'candidate-pack-v1/CONSTRUCTION_FIRST.json'
CONSTRUCTOR_SHA='4edd0dd37dc058366bb4596875dbd13d0be7816ca6ea89a10c29046186ce1633'
PANEL_SHA='7fd8da9db5ebc42ab67c5d1f07d7f9300b214a101f16fd2749dd7a8c9a760034'
PACKS={'B0':Q/'candidate-pack-v1/pack-FIRST','A0':E/'pack-native-vision-v1'}
DIRECTORIES={'B0':PACKS['B0']/'tokenizer','A0':E/'native-vision-v2/tokenizer'}
NAMES=('vocab.json','merges.txt','token_type.json','tokenizer.json','chat_template.jinja')
SOURCES=('fixtures.py','test_fixtures.py','run_cpu.py')


def require(ok,why):
    if not ok:raise ValueError(why)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def packed(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(value):return hashlib.sha256(packed(value)).hexdigest()


def ordinary(path):
    p=Path(path)
    require(p.is_absolute() and p.resolve()==p and not p.is_symlink() and p.is_file() and
            p.stat().st_nlink==1 and p.stat().st_size<=64*2**20,'Exact bounded real metadata file')
    return p


def exact(name,path,pin):
    require(sha(ordinary(path))==pin,'Pinned CPU-only source changed')
    old=sys.modules.get(name)
    require(old is None or Path(old.__file__)==path,'Foreign cached fixture helper')
    if old is not None:return old
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    try:spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[name];raise
    return module


def helpers():
    return exact('s2_encoded_runtime',RUNTIME,RUNTIME_SHA),exact('s2_original_fixtures',FIXTURE,FIXTURE_SHA)


def tokenizer_bytes(arm,fixture):
    require(arm in ('B0','A0'),'Exact separately frozen fixture arm')
    directory=DIRECTORIES[arm]
    require(directory.resolve()==directory and directory.is_dir(),'Actual profile tokenizer directory required')
    blobs={name:ordinary(directory/name).read_bytes() for name in NAMES}
    pins={name:hashlib.sha256(raw).hexdigest() for name,raw in blobs.items()}
    if arm=='A0':require(pins==fixture.BASE_TOKENIZER_PINS,'Exact existing selected baseline tokenizer')
    else:
        require(sha(ordinary(CONSTRUCTOR))==CONSTRUCTOR_SHA,'Exact actual constructed metadata receipt')
        receipt=json.loads(CONSTRUCTOR.read_text())
        require(receipt.get('metadata_only') is True and receipt.get('weights_ready') is False,'Actual metadata constructor, no weight/model claim')
        for name,row in receipt['outputs'].items():
            path=PACKS[arm]/name;ordinary(path)
            require(path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],'Actual constructed pack metadata changed')
        require(pins=={n:receipt['outputs']['tokenizer/'+n]['sha256'] for n in NAMES},'Actual candidate tokenizer publication')
    return blobs,pins,directory


def input_map():
    """All actual small source/metadata inputs, identical relative names on hosts."""
    runtime,fixture=helpers()
    result={'runtime':sha(RUNTIME),'original_fixtures':sha(FIXTURE),
            'essential_panel':sha(Q/'essential-panel-v1/panel.py'),'constructor':sha(CONSTRUCTOR)}
    require(result['essential_panel']==PANEL_SHA and result['constructor']==CONSTRUCTOR_SHA,'Frozen panel/constructor identity')
    for arm in ('B0','A0'):
        _,pins,_=tokenizer_bytes(arm,fixture)
        result.update({arm+'/tokenizer/'+n:h for n,h in pins.items()})
    receipt=json.loads(CONSTRUCTOR.read_text())
    result.update({'B0/metadata/'+n:sha(PACKS['B0']/n) for n in receipt['outputs']})
    for name,pin in fixture.SUPPORT_PINS.items():
        require(sha(ordinary(E/name))==pin,'Pinned unchanged CPU API/vision/template support')
        result['support/'+name]=pin
    image=E/fixture.IMAGE_SOURCE
    require(sha(ordinary(image))==fixture.SOURCE_PINS[fixture.IMAGE_SOURCE],'Frozen synthetic two-image requests')
    result['synthetic_images']=sha(image)
    return result


def encode(arm):
    runtime,fixture=helpers();before=input_map()
    raw,pins,directory=tokenizer_bytes(arm,fixture)
    tokens,merges,types,cfg=fixture.tokenizer_schema(raw)
    support=fixture.load_support();server=support.server
    tokenizer=support.ST.Tokenizer(tokens,merges,types,cfg['pre'],cfg['special_ids'])
    selected,template=fixture.effective_template(support,directory,raw)
    cases=runtime.expected_cases(fixture,arm)
    with tempfile.TemporaryDirectory(prefix='s2-essential-cpu-prompt-') as tmp:
        vision=support.ds4_vision.Vision(support.ds4_vision.Geometry(),Path(tmp),server.Vision.load)
        try:
            service=server.Service(server.MockEngine(tokenizer,['CPU'],max_context=1048576),tokenizer,
                server.ChatTemplate(selected),vision=vision,fit_max_tokens=False)
            service.set_family('deepseek41');service.answer_room=False
            service.reasoning_budget_configured=True;service.reasoning_budget_tokens=0
            service.reasoning_loop_recovery=False;service.repeat_stop_tokens=0
            def body_ids(body):
                messages,tools,kwargs=server.openai_to_messages(copy.deepcopy(body))
                messages,_=server.prepare_format(body.get('response_format'),messages,with_tools=bool(tools))
                return service.encode_prompt(messages,tools,kwargs,store=False)
            encoded=[]
            for case in cases:
                ids=body_ids(case['request'])
                require(type(ids) is list and all(type(t) is int and 0<=t<129280 for t in ids),'Actual CPU tokenizer vocabulary IDs')
                encoded.append(dict(copy.deepcopy(case),prompt_ids=ids,prompt_tokens=len(ids),
                    prompt_ids_sha256=digest(ids),request_sha256=digest(case['request']),image_spans=fixture.image_spans(ids)))
            normalization=False
            if arm=='B0':
                followup=next(c for c in encoded if c['id']=='ms-prose-tool-followup')
                for identifier in ('s2-essential-alternate-call-1','different-provider-ID-2'):
                    require(body_ids(fixture.tool_followup(fixture.synthetic_call(identifier)))==followup['prompt_ids'],
                            'Actual candidate picker/tokenizer tool-ID normalization')
                normalization=True
            manifest={'schema':'s2-essential-encoded-v1','arm':arm,'context_total':1048576,'output_allowance':262144,
                'policy':copy.deepcopy(runtime.panel().POLICY),'pack_relative_to_E':str(PACKS[arm].relative_to(E)),
                'tokenizer_relative_to_E':str(directory.relative_to(E)),'tokenizer_source_sha256':pins,
                'effective_template':template,'runtime_source_sha256':RUNTIME_SHA,'original_fixture_source_sha256':FIXTURE_SHA,
                'constructed_metadata_receipt_sha256':CONSTRUCTOR_SHA if arm=='B0' else None,
                'cases':encoded,'tool_ID_normalization_CPU_proved':normalization,
                'CPU_only':True,'native_model_executed':False,'GPU_launch_ready':False,
                'near_full_context_or_output_executed':False}
            runtime.fixture_contract(manifest,fixture,arm)
            require('torch' not in sys.modules and input_map()==before and
                fixture.effective_template(support,directory,raw)==(selected,template),'Stable source/actual picker inputs; no GPU framework')
            return manifest
        finally:vision.shutdown()


def write_manifest(path,manifest):
    path=Path(path);require(path.parent.resolve()==path.parent and not path.is_symlink(),'Exact existing manifest parent')
    with path.open('x') as f:f.write(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
