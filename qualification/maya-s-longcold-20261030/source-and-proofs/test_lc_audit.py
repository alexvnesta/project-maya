"""Synthetic LC1 terminal wire contracts. No inference, restart or live authority.

Only prior synthetic setup is composed. Config, token/SSE/native/JSON/closure,
source manifest and80GiB fence consumers stay real; startup/authority adapters
are explicitly synthetic. Three synthetic output IDs are a wire fixture, never
model generation or evidence of token-to-output detokenization correctness.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock,patch
from contextlib import ExitStack

HERE=Path(__file__).resolve().parent
MODEL=HERE.parent/'model-v1'
sys.path.insert(0,str(MODEL))
import test_ms_compat_audit as prior
import ms_compat_audit as original
qa=prior.qa
sys.path.insert(0,str(HERE))
import lc_audit as m
import lc_config as config


class Terminal(unittest.TestCase):
    def setUp(self):
        h=prior.Terminal('runTest');h.setUp();self.addCleanup(h.doCleanups);self.h=h
        self.p=h.p;self.meta=h.meta;self.folder=h.folder;self.out=h.out
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        for key,value in [('E',qa.config.E),('BASE_PACK',qa.config.BASE_PACK),('CANDIDATE_PACK',h.h.pack),
                          ('BASE_NORMALIZED',qa.config.BASE_NORMALIZED)]:
            self.stack.enter_context(patch.object(config,key,value))
        # Give the new real config contract its exact new synthetic namespace.
        target=self.out.with_name('maya-s-longcold-LC1-20261030T000000Z');self.out.rename(target)
        old=self.out;self.out=target;self.folder=target/'native'
        for f in self.p.rglob('*.json'):f.write_text(f.read_text().replace(str(old),str(target)).replace('ms_compat.py','lc_owner.py'))
        h.out=target;h.folder=self.folder;h.dest=self.folder/'skip-controls'/h.case['id']
        source=MODEL/'quality-fixtures-B.json';source_data=json.loads(source.read_text())
        self.case=copy.deepcopy(source_data['cases'][0]);self.case['id']=m.CASE_ID
        self.manifest=copy.deepcopy(h.manifest);self.manifest.update(mode='longcold',cases=[self.case])
        parent=self.p/'model-v1/quality-fixtures-B.json';parent.parent.mkdir();parent.write_bytes(source.read_bytes())
        h.put(self.out/'fixtures.json',self.manifest)
        q=copy.deepcopy(h.q);q['files'][str(parent)]=m.SOURCE_MANIFEST_SHA
        producer=self.p/'hosting-1m-output256k-v3-20261027/capacity_mode.py'
        q['files'][str(producer)]='a1f957e9866388b65eec6a2fcbf943d1143b434f9b106d38aca7e0620aa45ff1'
        for name in ('lc_audit.py','lc_runtime.py','lc_config.py','lc_controls.py','lc_owner.py','lc_audit_dispatch.py'):
            path=self.p/name;path.write_text('synthetic source boundary');q['files'][str(path)]=original.sha(path)
        self.q=q
        self.runtime=NS(P=self.p,E=self.p,R=self.p,Q=self.p,sha=original.sha,
            support=qa.runtime.support,owned_paths=Mock(return_value=(self.out,self.meta)),
            statuses=lambda mode:{'complete':'MAYA_S_LONGCOLD_SELECTED_RESTORED'},
            longcold_manifest=lambda:copy.deepcopy(self.manifest))
        base=h.read(self.p/'base-config.json');c=config.make_config(base,self.folder,'longcold','LC1')
        h.put(self.out/'candidate-config.json',c);csha=original.sha(self.out/'candidate-config.json')
        start=h.read(self.out/'startup-audit.json');start['actual_process'].update(actual_argv=config.expected_native_argv(c),controlled_env=c['env'])
        h.put(self.out/'startup-audit.json',start)
        entry=h.read(self.folder/'entry-audit.json');entry.update(config_sha256=csha,whole_pack_factor=config.factor('longcold','LC1'));h.put(self.folder/'entry-audit.json',entry)
        server=h.read(self.out/'server-start.json');a=server['argv'];a[a.index('--mode')+1]='longcold';a[a.index('--arm')+1]='LC1';a[a.index('--config-sha256')+1]=csha;h.put(self.out/'server-start.json',server)
        (self.folder/'skip-controls'/h.case['id']).rename(self.folder/'skip-controls'/m.CASE_ID);self.dest=self.folder/'skip-controls'/m.CASE_ID
        response=h.read(self.dest/'response.json');response['content']=json.dumps(self.case['expected']);response['usage']['prompt_tokens']=8469
        response['events'][1]['choices'][0]['delta']['content']=response['content'][:20]
        response['events'][2]['choices'][0]['delta']['content']=response['content'][20:]
        for event in response['events']:
            if event.get('usage') is not None:event['usage']=copy.deepcopy(response['usage'])
        response['raw']=[{'seconds':i,'line':'data: '+json.dumps(e)} for i,e in enumerate(response['events'])]+[{'seconds':4,'line':'data: [DONE]'}]
        h.put(self.dest/'request.json',self.case['request']);h.put(self.dest/'response.json',response)
        req=h.read(self.folder/'native-000/request.json');req['ids']=self.case['prompt_ids'];h.put(self.folder/'native-000/request.json',req)
        n=h.read(self.folder/'native-000/native-statistics.json');n.update(prompt_tokens=8469,drafts_offered=3,drafts_accepted=2);h.put(self.folder/'native-000/native-statistics.json',n)
        check=h.h.reconcile(self.folder/'native-000',self.case,response,123);h.put(self.dest/'native-audit.json',check)
        row={'id':m.CASE_ID,'passed':True,'native':n,'observed_tokens':3,'native_decode_tokens_per_second':30.,'client_seconds':.2,
             'content_characters':len(response['content']),'reasoning_characters':len(response['reasoning']),
             'manual_review_pending':False,'general_quality_or_equivalence_claim':False}
        rec=h.read(self.out/'receipt.json');rec.update(mode='longcold',arm='LC1');rec['arm_results'].update(rows=[row],mode1_activation={'activation_early_rows':[5801]},scores=[{'id':m.CASE_ID,'passed':True,'status':'LONGCOLD_JSON_SOURCE_AND_STATE_PASSED'}]);h.put(self.out/'receipt.json',rec)
        fence=h.read(self.out/'private-memory-fence.json');fence['memory_max']=80*2**30;h.put(self.out/'private-memory-fence.json',fence)
        (self.meta/'public-ready-sse.txt').unlink();h.put(self.meta/'public-default-output-request.json',m.PUBLIC_DEFAULT_REQUEST)
        (self.meta/'public-default-output-sse.txt').write_text('data: {"choices":[{"delta":{"content":"READ"},"finish_reason":null}]}\ndata: {"choices":[{"delta":{"content":"Y"},"finish_reason":"stop"}]}\ndata: [DONE]\n')
        state=h.read(self.meta/'state.json');state.update(mode='longcold',arm='LC1',status=self.runtime.statuses('longcold')['complete']);h.put(self.meta/'state.json',state)
        w=h.read(h.window);a=w['command'];a[a.index('--mode')+1]='longcold';a[a.index('--arm')+1]='LC1';h.put(h.window,w)
        dep=qa.dependency.side_effect;skip=dep('skip_controls',None,None);skip.activation.return_value={'activation_early_rows':[5801]}
        self.qa=NS(exact=qa.exact,j=qa.j,sse_contract=qa.sse_contract,tokenizer_contract=qa.tokenizer_contract,
                   dependency=lambda name,path,q:dep('ms_controls' if name=='lc_controls' else name,path,q))
        h.put(self.p/'longcold-arms.json',{'LC1':{'attempted':True,'controller_pid':55,'output':str(self.out)}})
        self.sync()
    def sync(self):
        p=self.p/'longcold-qualification.json';self.h.put(p,self.q);self.pin=original.sha(p)
        self.h.change(self.meta/'state.json',lambda v:v.update(qualification_sha256=self.pin))
        self.h.put(self.meta/'proof.json',{'qualified_for_owned_maya_s':True,'mode':'longcold','arm':'LC1','output':str(self.out),'qualification_sha256':self.pin,'files':self.q['files']})
    def audit(self):return m.audit_saved(self.runtime,config,qa.fixtures,qa.saved,self.qa,self.q,self.pin,self.h.binding,original=original)
    def test_full_saved_terminal_validates_source_native_SSE_and80GiB(self):
        r=self.audit();self.assertTrue(r['passed']);self.assertEqual(r['arm'],'LC1');self.assertEqual(r['rows'][0]['native']['prompt_tokens'],8469)
        self.assertEqual(r['private_fence']['memory_max'],80*2**30)
        self.assertTrue(r['rows'][0]['typed_known_answer_correct']);self.assertFalse(r['performance_claim']);self.assertFalse(r['general_quality_claim'])
        self.assertEqual(r['evidence_sha256'][str(self.meta/'public-default-output-sse.txt')],original.sha(self.meta/'public-default-output-sse.txt'))
    def test_old76GiB_fence_or_enabled_swap_refused(self):
        p=self.out/'private-memory-fence.json';v=self.h.read(p)
        for key,value in [('memory_max',76*2**30),('swap_max',1)]:
            changed=copy.deepcopy(v);changed[key]=value;self.h.put(p,changed)
            with self.assertRaises(ValueError):self.audit()
    def test_changed_source_request_or_cap_refused(self):
        self.manifest['cases'][0]['request']['max_tokens']=64
        with self.assertRaises(ValueError):self.audit()
    def rebind_case(self):
        response=self.h.read(self.dest/'response.json')
        check=self.h.h.reconcile(self.folder/'native-000',self.case,response,123)
        self.h.put(self.dest/'native-audit.json',check)
        n=check['native']
        row={'id':m.CASE_ID,'passed':True,'native':n,'observed_tokens':check['observed_tokens'],
             'native_decode_tokens_per_second':n['generated']/(n['decode_ms']/1000),
             'client_seconds':check.get('client_full_s'),'content_characters':len(response['content']),
             'reasoning_characters':len(response['reasoning']),'manual_review_pending':False,
             'general_quality_or_equivalence_claim':False}
        self.h.change(self.out/'receipt.json',lambda d:d['arm_results'].update(rows=[row]))
    def test_wrong_typed_JSON_with_consistent_wire_and_producer_pass_refused(self):
        r=self.h.read(self.dest/'response.json');r['content']='{"values":[true]}'
        r['events'][1]['choices'][0]['delta']['content']=r['content'][:8]
        r['events'][2]['choices'][0]['delta']['content']=r['content'][8:]
        r['raw']=[{'seconds':i,'line':'data: '+json.dumps(e)} for i,e in enumerate(r['events'])]+[{'seconds':4,'line':'data: [DONE]'}]
        self.h.put(self.dest/'response.json',r);self.rebind_case()
        with self.assertRaisesRegex(ValueError,'known answer'):self.audit()
    def test_cold_reuse_and_positive_draft_path_required_with_consistent_producer(self):
        p=self.folder/'native-000/native-statistics.json';before=self.h.read(p)
        for key,value,why in [('reused',1,'prefix state'),('drafts_accepted',0,'Positive DSpark')]:
            self.h.put(p,{**before,key:value});self.rebind_case()
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,why):self.audit()
    def test_skip5801_required_and_no_second_trace(self):
        self.h.change(self.out/'receipt.json',lambda d:d['arm_results'].update(mode1_activation={'activation_early_rows':[]}))
        with self.assertRaises(ValueError):self.audit()
    def test_no_dump_hooks_or_extra_native_requests(self):
        (self.folder/'logits.1.f32').write_bytes(b'1234')
        with self.assertRaises(ValueError):self.audit()
        (self.folder/'logits.1.f32').unlink();(self.folder/'native-001').mkdir()
        with self.assertRaises(ValueError):self.audit()
    def test_partial_producer_never_passes(self):
        self.h.change(self.out/'receipt.json',lambda d:d['arm_results'].update(complete=False))
        with self.assertRaises(ValueError):self.audit()
    def test_private_API_native_and_old_owner_exits_checked(self):
        self.h.change(self.folder/'server-cleanup.json',lambda d:d.update(server_returncode=1))
        with self.assertRaises(ValueError):self.audit()
    def test_missing_native_DONE_refused(self):
        self.h.change(self.folder/'native-000/trace-receipt.json',lambda d:d.update(DONE_observed=False))
        with self.assertRaises(ValueError):self.audit()
    def test_wrong_public_default_request_or_missing_stream_refused(self):
        self.h.change(self.meta/'public-default-output-request.json',lambda d:d.update(max_tokens=262144))
        with self.assertRaises(ValueError):self.audit()
    def test_unrestored_current_binding_refused(self):
        self.h.binding={**self.h.binding,'native_pid':999}
        with self.assertRaises(ValueError):self.audit()
    def test_read_only_and_no_promotion_or_comparison_claim(self):
        before={str(p):original.sha(p) for p in self.p.rglob('*') if p.is_file()};r=self.audit()
        self.assertEqual(before,{str(p):original.sha(p) for p in self.p.rglob('*') if p.is_file()})
        for k in ('automatic_next_arm','deployment_admitted','performance_claim','finite_logits_checked','near_full_context_or_output_tested'):self.assertIs(r[k],False)

    def test_nonzero_window_and_kernel_capture_failure_refused(self):
        self.h.change(self.h.window,lambda d:d.update(test_returncode=1))
        with self.assertRaisesRegex(ValueError,'window'):self.audit()
    def test_kernel_fault_lines_refused(self):
        p=self.h.window.with_suffix('.telemetry.jsonl');v=json.loads(p.read_text());v['kernel_fault_lines']=['synthetic CUDA fault'];p.write_text(json.dumps(v)+'\n')
        with self.assertRaisesRegex(ValueError,'Kernel'):self.audit()
    def test_transient_fence_collection_required(self):
        self.h.change(self.meta/'private-memory-fence-collected.json',lambda d:d.update(dropins_absent=False))
        with self.assertRaises(ValueError):self.audit()
    def test_raw_old_API_exit0_required(self):
        self.h.change(self.meta/'old-owner-close.json',lambda d:d['after'].update(ExecMainStatus='1'))
        with self.assertRaises(ValueError):self.audit()
    def test_extra_emitted_token_refused(self):
        p=self.folder/'native-000/tokens.jsonl'
        with p.open('a') as f:f.write(json.dumps({'token':42,'seconds':1.})+'\n')
        with self.assertRaises(ValueError):self.audit()
