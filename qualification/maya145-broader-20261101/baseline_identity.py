"""Pure selected-owner resolver after a separately verified baseline recovery.

A failed experiment is never accepted. Only the selected production identity
with successful public verification can be used for the next fresh admission.
"""
import copy
import re
NATIVE='92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1'
CONFIG='c43dd3d99df86cffaf071d482adb55b100288d04b86f82adddd05543e26424fa'

def require(ok,msg):
    if not ok:raise ValueError(msg)

def selected_binding(state):
    require(type(state) is dict,'Typed canonical state')
    current=state.get('decode_optimization_current') or {}
    verified=current.get('verified') or {}
    if verified.get('passed') is not True:
        recovery=state.get('maya145broader_recovery_current') or state.get('maya145quality2_recovery_current') or state.get('maya145quality_recovery_current') or {}
        require(recovery.get('active') is False and recovery.get('error') is None and recovery.get('status')=='SELECTED_BASELINE_RESTORED_FAILED_ARM_REMAINS_HOLD','No completed baseline recovery')
        if state.get('maya145broader_recovery_current') or state.get('maya145quality2_recovery_current'):
            require(recovery.get('failed_controller')==state.get('maintenance_controller') and type(state.get('maintenance_controller')) is str,'New recovery must belong to current failed controller')
        result=recovery.get('result') or {};verified=result.get('verified') or {}
        require(verified.get('passed') is True and result.get('status')==recovery['status'],'Successful separately verified recovery required')
        require(result.get('start_binding')==recovery.get('start_binding')==verified.get('selected_identity',{}).get('start_binding'),'Recovery result/verification binding changed')
    identity=verified.get('selected_identity') or {};binding=identity.get('start_binding') or {}
    require(type(binding) is dict and set(binding)=={'invocation','main_pid','native_pid','native_start_ticks'} and type(binding['invocation']) is str and re.fullmatch('[0-9a-f]{32}',binding['invocation']) is not None and all(type(binding[k]) is int and binding[k]>1 for k in ('main_pid','native_pid','native_start_ticks')),'Exact typed binding')
    require(type(state.get('current_native_pid')) is int and state['current_native_pid']==binding['native_pid']==identity.get('native_pid'),'Current actual owner must match verified identity')
    require(current.get('selected_identity',{}).get('start_binding')==binding,'Canonical selected identity and successful verification differ')
    require(identity.get('native_sha256')==NATIVE and identity.get('config_sha256')==CONFIG and type(identity.get('context')) is int and identity['context']==1048576 and type(identity.get('output_default')) is int and identity['output_default']==262144 and identity.get('Q8')==[1,1] and identity.get('DSpark') is True and identity.get('images') is True and identity.get('prefill_chunk')==4096 and identity.get('TP')==1 and identity.get('all_CPU_experts_RAM') is True,'Exact selected production policy')
    public=verified.get('public') or {}
    require(public.get('unauthenticated_models')==401 and public.get('authenticated_models')==200 and public.get('content')=='READY' and public.get('finish')=='stop' and public.get('SSE_done') is True and public.get('known_answer_passed') is True,'Verified assembled public authentication/READY-stop-DONE')
    return copy.deepcopy(binding)
