"""Pure production selection and exact relocation of the tested Maya-S pack."""
import copy
import hashlib
import posixpath
from pathlib import Path

R = Path('/home/alex/strata-deepseek-test-20261024')
E = R/'reliability-optimization-20261025'
DC = E/'decode-optimization-20261028'
D = Path('/home/alex/deepseek-hosted-20261025')
P = DC/'mayas-tp2-production-v4'
PACK = P/'pack-FIRST'
ASSETS = DC/'s2-reconstruction-v1/base-acquisition-v1/assets'
OLD_ROOT = str(DC/'maya-s-comparison-v1/assets/Maya-S')
NEW_ROOT = str(ASSETS/'Maya-S')
VISION = str(E/'vision-assets-1017/vision.bin')
CACHE = D/'state/conversation-cache-mayas-tp2-1m-chunk4096-20261101'
PROFILE = D/'state/expert-profile-mayas-tp2.bin'
NATIVE = DC/'maya145-mayas-v1/native-build-r2-FIRST/maya-ds4'
NATIVE_SHA = 'adff28a2d3a3f54ebfc0399e5e3ec7385f6fbb848e4e675fa1044cf7c6961f4f'
BASE_SHA = 'c43dd3d99df86cffaf071d482adb55b100288d04b86f82adddd05543e26424fa'
FLAGS = {'DS4_TP_GGUF_UNEVEN':'1','DS4_TP_CHECK':'1','DS4_AR2':'1','DS4_COPY_DIRECT':'1'}


def require(ok, why):
    if not ok: raise ValueError(why)


def sha(data): return hashlib.sha256(data).hexdigest()


def target_config(base):
    c = copy.deepcopy(base)
    for flag, value in (('--tp','1'),('--max-context','1048576'),('--prefill-chunk','4096'),
                        ('--dspark','on'),('--dspark-conf','0.65'),('--cpu-threads','24'),
                        ('--mmap-experts','off'),('--vision','on'),('--ablate-scale','1')):
        require(c['args'].count(flag) == 1 and c['args'][c['args'].index(flag)+1] == value, 'Unchanged base policy '+flag)
    for key in FLAGS: require(key not in c['env'], 'Unexpected preexisting candidate flag')
    for flag, value in (('--tp','2'),('--pack',str(PACK)),('--expert-profile',str(PROFILE))):
        require(c['args'].count(flag) == 1, 'One original flag')
        c['args'][c['args'].index(flag)+1] = value
    c['tokenizer'] = str(PACK/'tokenizer')
    c['env'].update(FLAGS)
    c['env'].update(STRATA_DS4_SLOT_DIR=str(CACHE),DS4_LANE_CAL=str(D/'state/lane-times-mayas-tp2.txt'),
                    DS4_LT_STORE=str(D/'state/lt-picks-mayas-tp2.txt'))
    return c


def config_contract(base, target):
    require(target == target_config(base), 'Only explicit model/TP2/namespaces may change')
    require(target['hosted_default_effort'] == 100 and
            target['env']['DS4_DSPARK_MAX'] == '4' and target['env']['DS4_REQUIRE_ALL_RAM'] == '1' and
            target['env']['DS4_STREAM'] == '0', 'Preserved effort/drafter/allCPU RAM')
    return True


def rebind_metadata(blobs, pins):
    expected = {'ds4.txt','tensors.txt','engram.bin','tokenizer/vocab.json','tokenizer/merges.txt',
                'tokenizer/token_type.json','tokenizer/tokenizer.json','tokenizer/chat_template.jinja'}
    require(set(blobs) == set(pins) == expected and all(type(v) is bytes and sha(v) == pins[k] for k,v in blobs.items()), 'Exact tested metadata')
    ds4 = blobs['ds4.txt'].decode(); tensors = blobs['tensors.txt'].decode()
    require([l for l in ds4.splitlines() if l.startswith('model_dir ')] == ['model_dir '+OLD_ROOT], 'Exact old source root')
    lines = tensors.splitlines(); files = [l for l in lines if l.startswith('file ')]
    expected_files = ['file %d DeepSeek-V4.1-Flash-1017-Maya-S-IQ2_XXS-%05d-of-00006.gguf'%(i,i+1) for i in range(6)]
    expected_files += ['file 6 ../dspark/dspark.bin','file 7 ../../../../vision-assets-1017/vision.bin']
    require(files == expected_files, 'Only the original eight model source files')
    new7 = 'file 7 '+posixpath.relpath(VISION, NEW_ROOT)
    result = dict(blobs)
    result['ds4.txt'] = ds4.replace('model_dir '+OLD_ROOT+'\n','model_dir '+NEW_ROOT+'\n').encode()
    result['tensors.txt'] = '\n'.join(new7 if l == expected_files[-1] else l for l in lines).encode()+b'\n'
    require([l for l in result['tensors.txt'].decode().splitlines() if not l.startswith('file ')] ==
            [l for l in lines if not l.startswith('file ')], 'Every tensor type/offset/size unchanged')
    return result


def process_contract(config, argv, env, cgroup, same):
    controlled = lambda e: {k:v for k,v in e.items() if k.startswith(('DS4_','STRATA_DS4_','MAYA_DS4_'))}
    require(same is True and cgroup.strip().split('/').count('deepseek-hosted.service') == 1 and
            argv == [config['exe'],'--serve',*config['args'],'--layer-split','auto',''] and
            controlled(env) == controlled(config['env']), 'Exact existing-unit native argv/env/executable')
    return True


def switch_guard_contract(state, binding, health, *, user_interrupt_authorized):
    phases = ('active_private_phase','active_GPU_phase','active_gpu_experiment','private_window','active_cpu_build',
              'production_restore_in_progress','production_verification_pending','production_temporarily_stopped')
    require(user_interrupt_authorized is True, 'Explicit user-selected interruptible switch only')
    require(not any(state.get(k) for k in phases) and
            state['decode_optimization_current']['selected_identity']['start_binding'] == binding, 'Exact selected owner and no other phase')
    s = health.get('switcher',{})
    require(health.get('status') == 'ok' and health.get('loaded') is True and health.get('images') is True and
            health.get('max_context') == 1048576 and s.get('active_model') == s.get('default_model') == 'deepseek' and
            s.get('fault') is None, 'Healthy default DeepSeek; no foreign model/fault')
    # Active DeepSeek user requests are explicitly interruptible for this switch.
    # This read-only staging guard never sends a request, drains or stops a unit.
    return True
