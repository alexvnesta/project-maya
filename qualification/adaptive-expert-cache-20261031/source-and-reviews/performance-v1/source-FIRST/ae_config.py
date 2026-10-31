"""Fixed versus existing adaptive expert-cache policy on selected native92. No actions."""
import copy
import hashlib
import json
from pathlib import Path
import re

R=Path('/home/alex/strata-deepseek-test-20261024')
E=R/'reliability-optimization-20261025'
D=Path('/home/alex/deepseek-hosted-20261025')
Q=E/'decode-optimization-20261028/maya-s-comparison-v1'
BASE_PACK=E/'pack-native-vision-v1'
CANDIDATE_PACK=BASE_PACK
BASE_SHA='c43dd3d99df86cffaf071d482adb55b100288d04b86f82adddd05543e26424fa'
BASE_NORMALIZED='84ebe7a435304f8d1734b8616066edae868b4273a0afec575bd7d3c81159ea6e'
BASE_NATIVE='92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1'
MODE_ARMS={'prose':('A1','B1')}
MODES=MODE_ARMS


def packed(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def normalized(value):return hashlib.sha256(packed(value)).hexdigest()


def factor(mode,arm):
    if type(mode) is not str or mode not in MODE_ARMS or type(arm) is not str or arm not in MODE_ARMS[mode]:
        raise ValueError('Exact new adaptive-cache mode and arm required')
    candidate=arm == 'B1'
    return {'candidate':candidate,'exe':str(D/'bin/maya-ds4'),'native_sha256':BASE_NATIVE,
            'pack':str(BASE_PACK),
            'factor':'adaptive-expert-cache-policy',
            'adaptive_cache_policy':'current-adaptive' if candidate else 'fixed-placement',
            'same_selected_weights_drafter_tokenizer':True,
            'placement_and_prompt_path_may_differ':True,
            'runtime_projection_policy':'L22 scale1 unchanged','numerical_equivalence_claim':False}


def selected_base(base):
    if normalized(base)!=BASE_NORMALIZED:raise ValueError('Exact typed selected4096 config required')
    if base['exe']!=str(D/'bin/maya-ds4') or base['args'].count('--pack')!=1 or base['args'][base['args'].index('--pack')+1]!=str(BASE_PACK):
        raise ValueError('Selected executable/pack differs')
    if base.get('layer_split') is not None or base.get('split_skip_if_fits') or '--layer-split' in base['args']:
        raise ValueError('Placement override refused')
    return True


def native_directory(directory,mode,arm):
    factor(mode,arm);p=Path(directory)
    if (not p.is_absolute() or '..' in p.parts or p.name!='native' or p.parent.parent!=E/'results' or
        re.fullmatch('adaptive-cache-'+mode+'-v1-'+arm+r'-[0-9]{8}T[0-9]{6}Z',p.parent.name) is None):
        raise ValueError('Exact fresh adaptive-cache native namespace required')
    return p


def make_config(base,directory,mode,arm):
    selected_base(base);p=native_directory(directory,mode,arm);f=factor(mode,arm)
    out=copy.deepcopy(base);out.update(port=18041,log=str(p/'engine.log'))
    out['args'][out['args'].index('--pack')+1]=f['pack']
    if not f['candidate']:out['args'].append('--no-expert-cache')
    out['args'][out['args'].index('--expert-profile')+1]=str(p/'expert-profile.bin')
    out['args'].append('--verbose')
    for key,tail in [('STRATA_DS4_SLOT_DIR','cache'),('DS4_LANE_CAL','lane.txt'),('DS4_LT_STORE','lt.txt')]:
        out['env'][key]=str(p/tail)
    if 'DS4_SERVE_DUMP' in out['env']:raise ValueError('Timed native must not dump logits')
    return out


def check_config(base,value,directory,mode,arm):
    if packed(value)!=packed(make_config(base,directory,mode,arm)):
        raise ValueError('Typed config differs from frozen cache policy')
    return True


def controlled_environment(env):
    return {k:v for k,v in env.items() if k.startswith(('DS4_','STRATA_DS4_','MAYA_DS4_'))}


def expected_native_argv(config):
    if config.get('layer_split') is not None or config.get('split_skip_if_fits') or '--layer-split' in config['args']:
        raise ValueError('Placement override refused')
    return [config['exe'],'--serve',*config['args'],'--layer-split','auto','']


def process_contract(config,argv,env,cgroup,*,same_executable):
    if same_executable is not True or 'strata-deepseek-window.service' not in cgroup.strip().split('/'):
        raise ValueError('Exact owned window executable required')
    if argv!=expected_native_argv(config):raise ValueError('Native argv differs')
    if controlled_environment(env)!=controlled_environment(config['env']):raise ValueError('Native controlled env differs')
    return {'argv_matches':True,'controlled_env_matches':True,'owned_window_cgroup':True,'same_executable':True}
