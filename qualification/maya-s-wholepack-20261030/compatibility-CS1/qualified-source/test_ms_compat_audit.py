"""Synthetic saved receipts only; no native, live support, tokenizer or GPU call.

The full terminal fixture reuses only the prior test's setUp data constructor.
Its test classes are not inherited or rerun. Config, tokenizer bytes, SSE, raw
native reconcile, old close, private close, fence and public evidence stay real.
Only live authority/startup observations and the already-qualified derived
manifest adapter are mocked in that fixture.
"""
import ast
import copy
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

import ms_compat_audit as m
import ms_quality_audit as qa
import test_ms_quality_audit as prior

REAL_E = qa.runtime.E
REAL_HERE = m.HERE
SOURCE = REAL_HERE / 'prose-fixtures-B.json'


class Temporary:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.p = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)
    def write(self, name, value):
        p = self.p / name; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value)); return p


class Contracts(Temporary, unittest.TestCase):
    def test_duplicate_nonfinite_and_alias_receipts_refused(self):
        p = self.write('receipt.json', {})
        for raw in ('{"x":1,"x":2}', '{"x":NaN}'):
            p.write_text(raw)
            with self.subTest(raw=raw), self.assertRaises(ValueError): m.Recorder().json(p)
        link = self.p / 'alias'; link.symlink_to(p)
        with self.assertRaises(ValueError): m.Recorder().bytes(link)
    def test_receipt_bytes_changed_during_audit_refused(self):
        p = self.write('receipt.json', {'x': 1}); r = m.Recorder(); r.json(p)
        p.write_text('{"x":2}')
        with self.assertRaises(ValueError): r.json(p)
    def test_large_receipt_rejected_without_payload_read(self):
        p = self.write('large.json', {'x': 123})
        with patch.object(m, 'MAX_EVIDENCE_BYTES', 2), self.assertRaises(ValueError): m.Recorder().bytes(p)
    def test_actual_child_limits_observed_before_project_import(self):
        with patch.object(m, 'observed', side_effect=ValueError('bounds')), patch.object(m, 'load_dispatcher') as load:
            with self.assertRaises(ValueError): m.run({})
            load.assert_not_called()
    def test_actual_observed_environment_and_limits(self):
        with patch.object(m.sys, 'platform', 'linux'), patch.dict(m.os.environ, m.ENV), \
             patch.object(m.os, 'getpriority', return_value=15), \
             patch.object(m.resource, 'getrlimit', side_effect=lambda kind: (30, 30) if kind == m.resource.RLIMIT_CPU else (512*2**20,)*2):
            self.assertEqual(m.observed()['CPU'], [30, 30])
            with patch.dict(m.os.environ, {'CUDA_VISIBLE_DEVICES': '0'}), self.assertRaises(ValueError): m.observed()
    def test_foreign_origin_or_missing_pin_blocks_import(self):
        p = self.write('helper.py', {})
        with patch.object(m.importlib, 'import_module') as load:
            with self.assertRaises(ValueError): m.import_pinned('foreign_test_helper', p, {})
            with patch.dict(m.sys.modules, {'foreign_test_helper': NS(__file__='/foreign.py')}), self.assertRaises(ValueError):
                m.import_pinned('foreign_test_helper', p, {str(p): m.sha(p)})
            load.assert_not_called()
    def test_all_new_auditor_controls_must_be_qualified(self):
        self.write('ms_compat_audit.py', {}); (self.p/'test_ms_compat_audit.py').write_text('class T:\n def test_one(self): pass\n')
        sm = {n: m.sha(self.p/n) for n in ('ms_compat_audit.py', 'test_ms_compat_audit.py')}
        q = {'files': {str(self.p/n): h for n,h in sm.items()}, 'CPU_groups': [{'source_sha256': sm, 'test_ids': ['test_ms_compat_audit.T.test_one']}]}
        with patch.object(m, 'HERE', self.p):
            m.audit_cpu_membership(q); q['CPU_groups'][0]['test_ids'] = []
            with self.assertRaises(ValueError): m.audit_cpu_membership(q)
    def test_source_aligned_case_44_and_policy_required(self):
        manifest = json.loads(SOURCE.read_text()); case = copy.deepcopy(manifest['lifecycle_cases'][-1])
        case.pop('dependency'); case.update(id=qa.runtime.COMPAT_CASE_ID, expected_reuse='zero')
        m.case_contract(case, qa.config, qa.runtime)
        for field, value in [('prompt_tokens', 43), ('expected_reuse', 'warm'), ('expected', 'wrong')]:
            changed = copy.deepcopy(case); changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): m.case_contract(changed, qa.config, qa.runtime)
        changed = copy.deepcopy(case); changed['request']['max_tokens'] = 64
        with self.assertRaises(ValueError): m.case_contract(changed, qa.config, qa.runtime)


class Dispatch(Temporary, unittest.TestCase):
    def setUp(self):
        super().setUp(); self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(m, 'HERE', self.p))
        self.bounds = {'CPU': [30,30], 'AS': [512*2**20]*2, 'nice': 15, 'environment': dict(m.ENV)}
        self.stack.enter_context(patch.object(m, 'observed', return_value=self.bounds))
        self.binding = {'native_pid': 321}; self.dispatch = NS(fresh_idle=Mock(return_value=self.binding))
        self.stack.enter_context(patch.object(m, 'load_dispatcher', return_value=self.dispatch))
        names = ('ms_config','ms_fixtures','ms_runtime','ms_audit','ms_quality_audit')
        for n in names: (self.p/(n+'.py')).write_text('synthetic pinned boundary')
        self.q = {'files': {str(self.p/(n+'.py')):m.sha(self.p/(n+'.py')) for n in names}}
        self.qpath = self.write('compatibility-qualification.json', self.q); self.pin = m.sha(self.qpath)
        self.runtime = NS(qualified=Mock(return_value=self.q))
        modules = {n: NS() for n in names}; modules['ms_runtime'] = self.runtime
        self.importer = self.stack.enter_context(patch.object(m, 'import_pinned', side_effect=lambda n,p,q: modules[n]))
        self.stack.enter_context(patch.object(m, 'audit_cpu_membership'))
        self.attempt = self.write('CS1/offline-audit-FIRST/attempt.json', {'stage':'compatibility-terminal','arm':'CS1',
                    'qualification_sha256':self.pin,'expected_binding':self.binding})
        self.context = {'qualification_sha256':self.pin,'expected_binding':self.binding,'attempt_sha256':m.sha(self.attempt)}
        self.evidence = self.write('raw.json', {'observed': True}); self.write('ms_compat_audit.py', {})
        self.saved = self.stack.enter_context(patch.object(m, 'audit_saved', return_value={'passed':True,'evidence_sha256':{str(self.evidence):m.sha(self.evidence)}}))
    def test_one_bounded_saved_audit_and_no_replay(self):
        r = m.run(self.context); self.assertTrue(r['parent_exit0_cleanup_and_wall90_proof_required'])
        self.assertTrue((self.attempt.parent/'audit-started.json').is_file())
        with self.assertRaises(FileExistsError): m.run(self.context)
        self.saved.assert_called_once()
    def test_busy_prevents_qualification_import_and_claim(self):
        self.dispatch.fresh_idle.side_effect = ValueError('busy')
        with self.assertRaises(ValueError): m.run(self.context)
        self.importer.assert_not_called(); self.assertFalse((self.attempt.parent/'audit-started.json').exists())
    def test_post_audit_busy_prevents_heavy_posthash(self):
        self.dispatch.fresh_idle.side_effect = [self.binding, self.binding, ValueError('busy')]
        with self.assertRaises(ValueError): m.run(self.context)
        self.assertEqual(self.runtime.qualified.call_count, 1)
    def test_preimport_support_omission_refused(self):
        del self.q['files'][str(self.p/'ms_config.py')]; self.qpath.write_text(json.dumps(self.q))
        self.context['qualification_sha256'] = m.sha(self.qpath)
        with self.assertRaises(ValueError): m.run(self.context)
        self.importer.assert_not_called()
    def test_attempt_mutation_or_foreign_arm_refused(self):
        data = json.loads(self.attempt.read_text()); data['arm'] = 'QS1'; self.attempt.write_text(json.dumps(data))
        self.context['attempt_sha256'] = m.sha(self.attempt)
        with self.assertRaises(ValueError): m.run(self.context)
        self.saved.assert_not_called()
    def test_post_audit_mutation_keeps_started_attempt(self):
        original = self.saved.return_value
        def changed(*args): self.evidence.write_text('{}'); return original
        self.saved.side_effect = changed
        with self.assertRaises(ValueError): m.run(self.context)
        self.assertTrue((self.attempt.parent/'audit-started.json').exists())
    def test_failed_audit_retained_and_not_retried(self):
        self.saved.side_effect = ValueError('raw fault')
        with self.assertRaisesRegex(ValueError, 'raw fault'): m.run(self.context)
        with self.assertRaises(FileExistsError): m.run(self.context)
        self.saved.assert_called_once()


class Terminal(unittest.TestCase):
    def setUp(self):
        source = json.loads(SOURCE.read_text()); case = copy.deepcopy(source['lifecycle_cases'][-1])
        case.pop('dependency'); case.update(id=qa.runtime.COMPAT_CASE_ID, expected_reuse='zero')
        path = REAL_E/'decode-optimization-20261028/q8-sharing-v1/model-v1/q8share_model_runtime.py'
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), '9bd594247cecc13980d864780b778a66da08fcaf2b0a3ff5b386e84e33a1ad2c')
        nodes = [n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in ('binding_contract','close_contract')]
        self.assertEqual({n.name for n in nodes}, {'binding_contract','close_contract'})
        ns={'re':re}; exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),ns)
        self.legacy=NS(close_contract=ns['close_contract']); self.bind_contract=ns['binding_contract']
        h=prior.Terminal('runTest'); h.setUp(); self.addCleanup(h.doCleanups); self.h=h; self.p=h.p
        stack=ExitStack(); self.addCleanup(stack.close); self.case=case
        oldout=h.output; self.out=oldout.with_name('maya-s-compatibility-CS1-20261030T000000Z')
        oldout.rename(self.out); self.folder=self.out/'native'; self.meta=self.p/'maintenance'
        # Rewrite synthetic owned paths, never any real or production evidence.
        for f in self.p.rglob('*.json'):
            f.write_text(f.read_text().replace(str(oldout),str(self.out)).replace('ms_quality.py','ms_compat.py'))
        for f in self.folder.glob('logits*.f32'): f.unlink()
        (self.folder/'native-file-bound.json').unlink()
        for i in range(1,4): shutil.rmtree(self.folder/('native-%03d'%i))
        shutil.rmtree(self.folder/'skip-controls')
        for key,value in [('CANDIDATE_PACK',h.pack)]: stack.enter_context(patch.object(qa.config,key,value))
        stack.enter_context(patch.object(qa.fixtures,'BASE_PACK',self.p/'unused-baseline'))
        stack.enter_context(patch.object(qa.fixtures,'CANDIDATE_PACK',h.pack))
        tok=h.pack/'tokenizer'; shutil.copytree(h.tok,tok)
        tm=copy.deepcopy(h.tm); template=tok/'chat_template.jinja'; t=tm['effective_template']
        t.update(pack_template_relative_to_E=str(template.relative_to(self.p)),effective_template_relative_to_E=str(template.relative_to(self.p)),
                 effective_template_sha256=m.sha(template),pack_template_replaced=False)
        self.manifest={**tm,'mode':'compatibility','context':1048576,'default_output':262144,'policy':qa.fixtures.POLICY,
                       'cases':[case],'pack_relative_to_E':'pack','derived_without_reencoding':True,
                       'quality_or_performance_pass':False,'automatic_next_arm':False}
        self.put(self.p/'prose-fixtures-B.json',self.manifest); self.put(self.out/'fixtures.json',self.manifest)
        stack.enter_context(patch.object(qa.runtime,'COMPAT_SOURCE_SHA',m.sha(self.p/'prose-fixtures-B.json')))
        stack.enter_context(patch.object(qa.runtime,'compatibility_manifest',return_value=self.manifest))
        stack.enter_context(patch.object(qa.runtime,'owned_paths',return_value=(self.out,self.meta)))
        self.binding={'invocation':'b'*32,'main_pid':320,'native_pid':321,'native_start_ticks':9}
        qa.runtime.support.return_value=(Mock(),Mock(),NS(binding_contract=self.bind_contract),self.legacy,Mock())
        base=self.read(self.p/'base-config.json'); c=qa.config.make_config(base,self.folder,'compatibility','CS1')
        self.put(self.out/'candidate-config.json',c); configsha=m.sha(self.out/'candidate-config.json')
        startup=self.read(self.out/'startup-audit.json'); startup.pop('native_file_limit_raw')
        startup['actual_process'].update(actual_argv=qa.config.expected_native_argv(c),controlled_env=c['env'])
        self.put(self.out/'startup-audit.json',startup)
        entry=self.read(self.folder/'entry-audit.json'); entry.update(config_sha256=configsha,whole_pack_factor=qa.config.factor('compatibility','CS1'))
        self.put(self.folder/'entry-audit.json',entry)
        server=self.read(self.out/'server-start.json'); argv=server['argv']; argv[argv.index('--mode')+1]='compatibility'; argv[argv.index('--arm')+1]='CS1'; argv[argv.index('--config-sha256')+1]=configsha
        self.put(self.out/'server-start.json',server)
        response=prior.response(); response['content']='RECOVERED_Q8_LITERAL'; response['usage']['prompt_tokens']=44
        response['events'][1]['choices'][0]['delta']['content']='RECOVERED_'
        response['events'][2]['choices'][0]['delta']['content']='Q8_LITERAL'
        response['raw']=[{'seconds':i,'line':'data: '+json.dumps(e)} for i,e in enumerate(response['events'])]+[{'seconds':4,'line':'data: [DONE]'}]
        dest=self.folder/'skip-controls'/case['id']; self.dest=dest
        self.put(dest/'request.json',case['request']); self.put(dest/'response.json',response)
        req=self.read(self.folder/'native-000/request.json'); req['ids']=case['prompt_ids']; self.put(self.folder/'native-000/request.json',req)
        n=self.read(self.folder/'native-000/native-statistics.json'); n.update(prompt_tokens=44,drafts_offered=0,drafts_accepted=0)
        self.put(self.folder/'native-000/native-statistics.json',n)
        check=h.reconcile(self.folder/'native-000',case,response,123); self.put(dest/'native-audit.json',check)
        row={'id':case['id'],'passed':True,'native':n,'observed_tokens':3,'native_decode_tokens_per_second':30.0,
             'client_seconds':.2,'content_characters':len(response['content']),'reasoning_characters':len(response['reasoning']),
             'manual_review_pending':False,'general_quality_or_equivalence_claim':False}
        receipt=self.read(self.out/'receipt.json'); receipt.update(mode='compatibility',arm='CS1')
        receipt['arm_results'].update(native_request_count=1,rows=[row],automatic_next_arm=False,quality_or_performance_pass=False,manual_review_required=True,
                scores=[{'id':case['id'],'passed':True,'status':'SHORT_LITERAL_SOURCE_AND_STATE_PASSED'}])
        self.put(self.out/'receipt.json',receipt)
        state=self.read(self.meta/'state.json'); state.update(mode='compatibility',arm='CS1',status=qa.runtime.statuses('compatibility')['complete'])
        state['verified']['selected_identity']['start_binding']=self.binding
        self.window=Path(state['window']); w=self.read(self.window); argv=w['command']; argv[argv.index('--mode')+1]='compatibility'; argv[argv.index('--arm')+1]='CS1'; self.put(self.window,w)
        oldbinding={'invocation':'a'*32,'main_pid':220,'native_pid':221,'native_start_ticks':8}
        u={'InvocationID':'a'*32,'MainPID':'0','ActiveState':'inactive','ExecMainCode':'1','ExecMainStatus':'0','Result':'success'}
        self.put(self.meta/'old-owner-close.json',{'passed':True,'binding':oldbinding,'native_close':{'native_pid':221,'server_pid':220,'returncode':0,'closed':True},'before':u,'after':u})
        self.q=copy.deepcopy(qa.runtime.qualified.return_value); self.q['allowed_automatic_cuts']['B']=[[19,21]]
        for f in tok.iterdir(): self.q['files'][str(f)]=m.sha(f)
        self.put(self.p/'ms_compat_audit.py',{})
        for name in ('ms_compat_audit.py','prose-fixtures-B.json'): self.q['files'][str(self.p/name)]=m.sha(self.p/name)
        self.put(self.p/'compatibility-qualification.json',self.q); self.qpin=m.sha(self.p/'compatibility-qualification.json')
        state['qualification_sha256']=self.qpin; self.put(self.meta/'state.json',state)
        self.put(self.meta/'proof.json',{'qualified_for_owned_maya_s':True,'mode':'compatibility','arm':'CS1','output':str(self.out),'qualification_sha256':self.qpin,'files':self.q['files']})
        self.put(self.p/'compatibility-arms.json',{'CS1':{'attempted':True,'controller_pid':55,'output':str(self.out)}})
    def put(self,path,value): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(value))
    def read(self,path): return json.loads(path.read_text())
    def change(self,path,fn): d=self.read(path); fn(d); self.put(path,d)
    def audit(self): return m.audit_saved(qa.runtime,qa.config,qa.fixtures,qa.saved,qa,self.q,self.qpin,self.binding)
    def test_full_saved_terminal_success_with_actual_byte_contracts(self):
        r=self.audit(); self.assertTrue(r['passed']); self.assertEqual(r['rows'][0]['native']['drafts_offered'],0)
        for name in ('performance_claim','general_quality_claim','deployment_admitted','automatic_next_arm','finite_logits_checked'):
            self.assertIs(r[name],False)
        self.assertTrue(r['evidence_sha256']); self.assertEqual(r['rows'][0]['observed_tokens'],3)
    def test_wrong_literal_not_cleared_by_producer_pass(self):
        self.change(self.dest/'response.json',lambda d:d.update(content='WRONG'))
        with self.assertRaises(ValueError): self.audit()
    def test_missing_DONE_or_changed_native_count_refused(self):
        self.change(self.folder/'native-000/trace-receipt.json',lambda d:d.update(DONE_observed=False))
        with self.assertRaises(ValueError): self.audit()
    def test_extra_native_trace_even_non_three_digit_refused(self):
        (self.folder/'native-1000').mkdir()
        with self.assertRaises(ValueError): self.audit()
    def test_private_API_nonzero_cannot_be_overridden_by_pass(self):
        self.change(self.folder/'server-cleanup.json',lambda d:d.update(server_returncode=1))
        with self.assertRaises(ValueError): self.audit()
    def test_raw_old_API_unit_exit_failure_refused(self):
        self.change(self.meta/'old-owner-close.json',lambda d:d['after'].update(ExecMainStatus='1'))
        with self.assertRaises(ValueError): self.audit()
    def test_raw_old_native_close_failure_refused(self):
        self.change(self.meta/'old-owner-close.json',lambda d:d['native_close'].update(returncode=1))
        with self.assertRaises(ValueError): self.audit()
    def test_fence_restore_and_collection_required(self):
        self.change(self.meta/'private-memory-fence-collected.json',lambda d:d.update(dropins_absent=False))
        with self.assertRaises(ValueError): self.audit()
    def test_kernel_fault_or_window_nonzero_refused(self):
        self.change(self.window,lambda d:d.update(test_returncode=1))
        with self.assertRaises(ValueError): self.audit()
    def test_current_binding_cannot_be_substituted(self):
        self.binding={**self.binding,'native_pid':999}
        with self.assertRaises(ValueError): self.audit()
    def test_public_READY_must_be_reconstructed(self):
        (self.meta/'public-ready-sse.txt').write_text('data: [DONE]\n')
        with self.assertRaises(ValueError): self.audit()
    def test_tokenizer_missing_membership_refused(self):
        del self.q['files'][str(self.h.pack/'tokenizer/vocab.json')]
        self.change(self.meta/'proof.json',lambda d:d.update(files=self.q['files']))
        with self.assertRaises(ValueError): self.audit()
    def test_config_output_policy_change_refused(self):
        self.change(self.out/'candidate-config.shared-settings.json',lambda d:d.update(max_tokens=64))
        with self.assertRaises(ValueError): self.audit()
    def test_producer_retry_or_automatic_advance_refused(self):
        self.change(self.out/'receipt.json',lambda d:d['arm_results'].update(automatic_next_arm=True))
        with self.assertRaises(ValueError): self.audit()
    def test_logits_rejected_without_scan(self):
        (self.folder/'logits.1.f32').write_bytes(b'not a float array')
        with self.assertRaises(ValueError): self.audit()
    def test_private_native_nonzero_is_not_hidden_by_cleanup_label(self):
        p=self.folder/'native-close.jsonl'; d=json.loads(p.read_text()); d['returncode']=1; p.write_text(json.dumps(d)+'\n')
        with self.assertRaises(ValueError): self.audit()
    def test_memory_oom_or_root_resource_failure_refused(self):
        self.change(self.out/'receipt.json',lambda d:d['resource_fence_terminal']['events_after'].update(oom=2))
        with self.assertRaises(ValueError): self.audit()
    def test_effective_template_hash_cannot_be_substituted(self):
        self.manifest['effective_template']['effective_template_sha256']='0'*64
        self.put(self.out/'fixtures.json',self.manifest)
        with self.assertRaises(ValueError): self.audit()
    def test_foreign_native_cgroup_refused(self):
        self.change(self.out/'startup-audit.json',lambda d:d['actual_process'].update(actual_cgroup='0::/user/foreign.service'))
        with self.assertRaises(ValueError): self.audit()
