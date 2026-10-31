"""Current-engine startup/process observations, unchanged transport and owned fence."""
import os
from pathlib import Path
import current_runtime as runtime
import current_config as config
import engine_profile

# Reuse exact qualified pure scoring, bounded transport and private-memory fence.
# These helpers do not invoke the old controller/old native/old arm registries.
prior=runtime.legacy_controls()
Incomplete=prior.Incomplete
for _name in ('token_contract','bounded_request','score','fenced_phase','fence_terminal'):
    globals()[_name]=getattr(prior,_name)


def startup(a,old,ready,health,models,log,variant):
    result=old.capacity_startup(ready,health,models,log,4096,expected_context=1048576)
    result['current_engine']=engine_profile.startup(log,variant)
    runtime.require(result['expert_slots']+result['cpu_experts']==15360,'Actual trunk expert accounting')
    return result


def actual_native(c,pid,config):
    proc=Path('/proc')/str(pid)
    env=dict(x.split('=',1) for x in (proc/'environ').read_bytes().decode().split('\0') if '=' in x)
    argv=(proc/'cmdline').read_bytes().decode().split('\0');group=(proc/'cgroup').read_text()
    same=os.path.samefile(proc/'exe',c['exe'])
    result=config.process_contract(c,argv,env,group,same_executable=same)
    runtime.require(runtime.sha(c['exe'])==config.BASE_NATIVE,'New native changed')
    return {**result,'native_pid':pid,'native_sha256':config.BASE_NATIVE,
        'controlled_env':config.controlled_environment(env),'actual_argv':argv,'actual_cgroup':group,
        'same_executable':same,'start_ticks':int((proc/'stat').read_text().rsplit(') ',1)[1].split()[19])}
