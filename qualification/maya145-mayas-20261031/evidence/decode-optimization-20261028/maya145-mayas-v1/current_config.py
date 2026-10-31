"""New native145/public Maya-S short compatibility factors. No actions at import."""
import hashlib
import json
from pathlib import Path
import engine_profile as profile

R=Path('/home/alex/strata-deepseek-test-20261024')
E=R/'reliability-optimization-20261025'
D=Path('/home/alex/deepseek-hosted-20261025')
BASE_SHA='c43dd3d99df86cffaf071d482adb55b100288d04b86f82adddd05543e26424fa'
SELECTED_NATIVE='92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1'
BASE_NATIVE='adff28a2d3a3f54ebfc0399e5e3ec7385f6fbb848e4e675fa1044cf7c6961f4f'
BASE_NORMALIZED=profile.BASE_NORMALIZED
MODE_ARMS={'compatibility':('RTP2','RTP1')}
MODES=MODE_ARMS


def packed(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def normalized(value):return hashlib.sha256(packed(value)).hexdigest()


def variant(mode,arm):
    if mode!='compatibility' or arm not in MODE_ARMS['compatibility']:
        raise ValueError('New native145 short compatibility profiles only')
    return arm[1:]


def factor(mode,arm):
    v=variant(mode,arm)
    return {**profile.factor(v),'candidate':True,'exe':str(profile.NATIVE),'native_sha256':BASE_NATIVE,
        'factor':'Maya145-public-MayaS-'+v,'includes_published_drafter_and_Engram':True,
        'runtime_projection_policy':'L22 scale1 all40 main blocks; drafter unchanged'}


def make_config(base,directory,mode,arm):
    return profile.profile(base,str(directory),variant(mode,arm))


def check_config(base,value,directory,mode,arm):
    return profile.check_profile(base,value,str(directory),variant(mode,arm))


def controlled_environment(env):
    return {k:v for k,v in env.items() if k.startswith(('DS4_','STRATA_DS4_','MAYA_DS4_'))}


def expected_native_argv(c):
    if c.get('layer_split') is not None or c.get('split_skip_if_fits') or '--layer-split' in c['args']:
        raise ValueError('Manual layer placement forbidden')
    # Final empty string is /proc/cmdline's null terminator, not an argv element.
    return [c['exe'],'--serve',*c['args'],'--layer-split','auto','']


def process_contract(c,argv,env,cgroup,*,same_executable):
    if same_executable is not True or 'strata-deepseek-window.service' not in cgroup.strip().split('/'):
        raise ValueError('Exact owned private native required')
    if argv!=expected_native_argv(c) or controlled_environment(env)!=controlled_environment(c['env']):
        raise ValueError('Actual native argv or controlled environment differs')
    return {'argv_matches':True,'controlled_env_matches':True,'owned_window_cgroup':True,'same_executable':True}
