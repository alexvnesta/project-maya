"""Exact selected4096 factors for new numerical and decode comparisons. No execution."""
import copy,hashlib,json,pathlib,re
R=pathlib.Path('/home/alex/strata-deepseek-test-20261024')
E=R/'reliability-optimization-20261025';D=pathlib.Path('/home/alex/deepseek-hosted-20261025')
P=E/'decode-optimization-20261028/model-v1'
BASE_SHA='c43dd3d99df86cffaf071d482adb55b100288d04b86f82adddd05543e26424fa'
BASE_NORMALIZED='84ebe7a435304f8d1734b8616066edae868b4273a0afec575bd7d3c81159ea6e'
BASE_NATIVE='92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1'
CANDIDATE_NATIVE='bef0b4d37e4ca028698d69babe227e23aa701c00d2bb1a706b821f1e98e4367a'
CANDIDATE_EXE=P.parent/'build-FIRST/maya-ds4-candidate'
MODES={'numerical':('N0','N1'),'performance':('A1','B1','B2','A2')}

def packed(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def normalized(value):return hashlib.sha256(packed(value)).hexdigest()
def factor(mode,arm):
    if type(mode) is not str or mode not in MODES or type(arm) is not str or arm not in MODES[mode]:
        raise ValueError('Exact new mode and arm required')
    candidate=arm in ('N1','B1','B2')
    return {'exe':str(CANDIDATE_EXE if candidate else D/'bin/maya-ds4'),
            'native_sha256':CANDIDATE_NATIVE if candidate else BASE_NATIVE,'minimum_columns':2 if candidate else 0}

def selected_base(base):
    if normalized(base)!=BASE_NORMALIZED:raise ValueError('Selected4096 baseline changed')
    if base['exe']!=str(D/'bin/maya-ds4') or base.get('hosted_default_effort')!=100:
        raise ValueError('Unqualified model or effort')
    for flag,value in [('--max-context','1048576'),('--prefill-chunk','4096'),('--cpu-threads','24'),
                       ('--tp','1'),('--vision','on'),('--dspark','on'),('--dspark-conf','0.65'),
                       ('--mmap-experts','off'),('--ablate-scale','1')]:
        if base['args'].count(flag)!=1 or base['args'][base['args'].index(flag)+1]!=value:
            raise ValueError('Selected capacity/quality/placement changed')
    if base.get('layer_split') is not None or base.get('split_skip_if_fits') or '--layer-split' in base['args']:
        raise ValueError('Unqualified placement override')
    return True

def native_directory(directory,mode,arm):
    factor(mode,arm);directory=pathlib.Path(directory)
    if (not directory.is_absolute() or '..' in directory.parts or directory.name!='native' or
        directory.parent.parent!=E/'results' or
        re.fullmatch('decode-imma-'+mode+'-'+arm+r'-[0-9]{8}T[0-9]{6}Z',directory.parent.name) is None):
        raise ValueError('Exact new native namespace required')
    return directory

def make_config(base,directory,mode,arm):
    selected_base(base);directory=native_directory(directory,mode,arm);f=factor(mode,arm)
    value=copy.deepcopy(base);value.update(exe=f['exe'],port=18041,log=str(directory/'engine.log'))
    value['args'][value['args'].index('--expert-profile')+1]=str(directory/'expert-profile.bin')
    value['args'].append('--verbose') # Common private observation only, both factors.
    for key,tail in [('STRATA_DS4_SLOT_DIR','cache'),('DS4_LANE_CAL','lane.txt'),('DS4_LT_STORE','lt.txt')]:
        value['env'][key]=str(directory/tail)
    for key in ['STRATA_DS4_Q5K_IMMA','DS4_Q5K_IMMA']:value['env'][key]=str(f['minimum_columns'])
    if mode=='numerical':value['env']['DS4_SERVE_DUMP']=str(directory/'logits')
    return value

def check_config(base,value,directory,mode,arm):
    if packed(value)!=packed(make_config(base,directory,mode,arm)):raise ValueError('Private typed settings differ from frozen factor')
    return True

def controlled_environment(env):
    return {k:v for k,v in env.items() if k.startswith(('DS4_','STRATA_DS4_','MAYA_DS4_'))}

def expected_native_argv(config):
    # Last empty string is the terminating /proc/cmdline NUL, not an argv we append.
    if config.get('layer_split') is not None or config.get('split_skip_if_fits') or '--layer-split' in config['args']:
        raise ValueError('Unqualified placement override')
    return [config['exe'],'--serve',*config['args'],'--layer-split','auto','']

def process_contract(config,argv,env,cgroup,*,same_executable):
    if same_executable is not True or 'strata-deepseek-window.service' not in cgroup.strip().split('/'):
        raise ValueError('Native is not the exact owned window child')
    if argv!=expected_native_argv(config):raise ValueError('Actual native arguments differ')
    if controlled_environment(env)!=controlled_environment(config['env']):raise ValueError('Native environment differs')
    return {'argv_matches':True,'controlled_env_matches':True,'owned_window_cgroup':True,'same_executable':True}

def factor_activation(log,mode,arm):
    f=factor(mode,arm)
    line='ds4: Q5_K GEMVs of >= 2 activations on the int8 tensor cores (DS4_Q5K_IMMA)'
    relevant=[x for x in log.splitlines() if '(DS4_Q5K_IMMA)' in x]
    # This is checked after requests, not required before the first Q5 GEMV.
    if relevant!=([line] if f['minimum_columns']==2 else []):raise ValueError('Missing/foreign IMMA factor activation')
    return {'minimum_columns':f['minimum_columns'],'eligible_flag_observed':bool(relevant),
            'per_model_kernel_launch_count_observed':False,'direct_dispatch_proof':'separate244caseGPUfixture'}
