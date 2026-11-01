"""Private copy of qualified cancellation transport, source-placement adaptation only.

No old module or global is patched. The freshly loaded private module has one
new activation callback, fully bound to the same actual native startup.
"""
from pathlib import Path
import time
import current_skip

def adapter(start,variant,expected_early):
    def activation(text,mode,*,required):
        if type(mode) is not int or mode!=1 or required is not True:raise ValueError('Exact mode1 cancellation activation')
        return current_skip.activation(text,start,variant,[expected_early],complete=True)
    return activation

def requester(runtime,old,numerical,controls,folder,start,variant):
    cancellation=runtime.reusable('pv_runtime').lifecycle_helper()
    # lifecycle_helper creates a fresh module namespace for this controller.
    cancellation.activation=adapter(start,variant,8471-2668)
    def cancel(case,out,pid,deadline):
        runtime.require(Path(out)==Path(folder) and type(pid) is int and pid==start['native_pid'],'Exact current private cancellation owner/namespace')
        runtime.require(case['kind']=='prefill-cancel' and case['id']=='ms-prose-prefill-cancel' and case['prompt_tokens']==8471,'Frozen cancellation only')
        destination=Path(out)/'skip-controls'/case['id'];destination.mkdir(parents=True,exist_ok=False)
        runtime.emit(destination/'request.json',case['request']);before=set(old.q8_phase.native_paths(out));next_resource=[0.]
        def guard_resource():
            if time.monotonic()>=next_resource[0]:
                runtime.require(numerical.owned_storage_snapshot(out)['status']!='INCOMPLETE_HOLD' and runtime.memory_available()>=runtime.HOST_MARGIN,'Cancellation resource margin exhausted')
                next_resource[0]=time.monotonic()+1
        def observe(base,path):guard_resource();return cancellation.json_get(base,path)
        def progress(base):guard_resource();return cancellation.progress(base)
        try:response=cancellation.prefill_cancel(old.q8_phase.BASE,case['request'],deadline,Path(out)/'engine.log',1,observe=observe,observe_progress=progress)
        except BaseException as exc:
            runtime.emit(destination/'transport-error.json',{'error':repr(exc),'raw':getattr(exc,'raw_transport',None),'retry':False});raise
        runtime.emit(destination/'response.json',response);traces=set(old.q8_phase.native_paths(out))-before
        if response.get('budget_not_started') or (response.get('intentional_budget_stop') and not traces):
            runtime.require(not traces,'Unstarted cancellation reached native');exc=controls.Incomplete('UNRUN prefill cancel before unchanged deadline');exc.native_started=False;raise exc
        runtime.require(len(traces)==1,'Exactly one cancelled native request')
        trace=next(iter(traces));old.q8_phase.await_trace(trace,max(deadline,time.monotonic()+5))
        proof=cancellation.reconcile(trace,case,response.get('transport') or {},pid,cancelled=True)
        proof['emitted_token_contract']=controls.token_contract(trace/'tokens.jsonl',proof['observed_tokens'])
        controls.native_stat(trace,pid,required=False)  # also retained in the phase's per-request STAT array
        runtime.emit(destination/'native-audit.json',proof)
        return response,proof
    return cancel
