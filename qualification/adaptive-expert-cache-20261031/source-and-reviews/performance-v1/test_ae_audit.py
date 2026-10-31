"""Saved synthetic evidence only. No model, CUDA, service, or remote actions."""
import copy
import array
import ast
import hashlib
import importlib.util
import json
import math
import os
import pathlib
from contextlib import ExitStack
from pathlib import Path
import shutil
import struct
import stat
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

import ae_audit as m

LC_PATH=Path(__file__).resolve().parents[2]/'maya-s-comparison-v1/long-cold-v1/lc_audit.py'
assert hashlib.sha256(LC_PATH.read_bytes()).hexdigest()=='04c74fdbed213ea037e94827fe5fdd6c52af3981cca7d59b64219bfc78960334'
sys.path.insert(0,str(LC_PATH.parent))
import lc_audit as lc


class Temporary:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.p = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)
    def write(self, name, value):
        p = self.p / name; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value)); return p


def response():
    events = [{'choices': [{'delta': {'reasoning_content': 'Check. '}, 'finish_reason': None}]},
              {'choices': [{'delta': {'content': '{"values":'}, 'finish_reason': None}]},
              {'choices': [{'delta': {'content': '[1]}'}, 'finish_reason': 'stop'}],
               'usage': {'completion_tokens': 3, 'prompt_tokens': 2},
               'timings': {'predicted_n': 3}}]
    return {'status': 200, 'content': '{"values":[1]}', 'reasoning': 'Check. ',
            'finish_reason': 'stop', 'done': True, 'cancelled': False, 'tool_calls': [],
            'events': events, 'usage': events[-1]['usage'], 'timings': events[-1]['timings'],
            'raw': [{'seconds': i, 'line': 'data: ' + json.dumps(e)} for i, e in enumerate(events)]
                   + [{'seconds': 4, 'line': 'data: [DONE]'}], 'client_full_seconds': .2}


STAT_RAW='STAT tok_s=30.00 ms_tok=33.33 vram_hit=0.7500 cpu=4.000 ram=4.000 promo=0.000 engram_ms=0.001 vram_used=11315 ram_used=4045 cpu_n=4045 vram_gb=90.00 ram_gb=50.00 disk_mb=0.000 disk=0.000 ram_fetch=4.000 drafts=0.667'


def stat_files(trace,pid=123,index=0,*,cancelled=False):
    raw='' if cancelled else STAT_RAW+'\n'
    rows=[] if cancelled else [{'native_pid':pid,'trace_number':index,'seconds':.02,'raw':STAT_RAW}]
    (trace/'stat-lines.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in rows))
    (trace/'stat-receipt.json').write_text(json.dumps({'native_pid':pid,'trace_number':index,'samples':len(rows),
        'raw_lines_sha256':hashlib.sha256(raw.encode()).hexdigest(),'DONE_observed':True,'capture_error':None,'primary_error':None,'complete':True}))
    n=json.loads((trace/'native-statistics.json').read_text())
    (trace/'raw-done.txt').write_text('DONE %d %d %.1f %.1f %s %d %d %d %d %d'%(
        n['generated'],n['prompt_tokens'],n['prompt_ms'],n['decode_ms'],n['finish'],n['drafts_accepted'],n['drafts_offered'],n['reused'],n['hits'],n['lookups']))


class Stats(Temporary,unittest.TestCase):
    def setUp(self):
        super().setUp();self.trace=self.p/'native-000';self.trace.mkdir()
        (self.trace/'native-statistics.json').write_text(json.dumps({'generated':3,'prompt_tokens':2,'prompt_ms':1.0,
            'decode_ms':100.0,'finish':'stop','drafts_accepted':2,'drafts_offered':3,'reused':0,'hits':12,'lookups':16}))
        stat_files(self.trace)
    def test_original_stats_and_raw_DONE_are_independently_parsed(self):
        c=m.stat_contract(self.trace,123,0);self.assertEqual(c['sample_count'],1)
        self.assertFalse(c['exact_swap_count_available']);self.assertFalse(c['exact_PCIe_migration_bytes_available'])
        self.assertEqual(m.raw_done_contract(self.trace,m.j(self.trace/'native-statistics.json'))['generated'],3)
    def test_promotion_positive_is_only_rounded_sample_evidence(self):
        sample=m.parse_stat(STAT_RAW.replace('promo=0.000','promo=0.125'));self.assertEqual(sample['promo'],.125)
    def test_malformed_duplicate_nonfinite_negative_or_streaming_stat_refused(self):
        for raw in [STAT_RAW+' promo=1',STAT_RAW.replace('cpu=4.000','cpu=NaN'),STAT_RAW.replace('promo=0.000','promo=-1'),
                    STAT_RAW.replace('vram_hit=0.7500','vram_hit=1.1'),STAT_RAW.replace('cpu_n=4045','cpu_n=1.5'),
                    STAT_RAW+' pcie=0.1',STAT_RAW+' skipped=1',STAT_RAW.replace('promo=0.000',''),STAT_RAW+'\n']:
            with self.subTest(raw=raw),self.assertRaises(ValueError):m.parse_stat(raw)
    def test_missing_sample_allowed_only_for_confirmed_zero_token_cancel(self):
        stat_files(self.trace,cancelled=True)
        self.assertEqual(m.stat_contract(self.trace,123,0,cancelled=True)['sample_count'],0)
        with self.assertRaises(ValueError):m.stat_contract(self.trace,123,0)
    def test_wrong_pid_ordinal_digest_counts_or_capture_error_refused(self):
        p=self.trace/'stat-receipt.json';before=p.read_text()
        for key,value in [('native_pid',124),('native_pid',True),('trace_number',1),('samples',2),('complete',False),
                          ('DONE_observed',False),('capture_error','disk'),('primary_error','ERR'),('raw_lines_sha256','0'*64)]:
            row=json.loads(before);row[key]=value;p.write_text(json.dumps(row))
            with self.subTest(key=key),self.assertRaises(ValueError):m.stat_contract(self.trace,123,0)
        p.write_text(before)
    def test_line_time_and_attribution_refused(self):
        p=self.trace/'stat-lines.jsonl';before=p.read_text()
        for key,value in [('native_pid',999),('trace_number',1),('seconds',-1),('seconds',True),('seconds',float('nan'))]:
            row=json.loads(before);row[key]=value;p.write_text(json.dumps(row)+'\n')
            with self.subTest(key=key),self.assertRaises(ValueError):m.stat_contract(self.trace,123,0)
        p.write_text(before)
    def test_duplicate_JSONL_keys_and_overflow_rejected(self):
        p=self.trace/'stat-lines.jsonl'
        for raw in ['{"seconds":0,"seconds":1}','{"seconds":1e400}']:
            p.write_text(raw+'\n')
            with self.subTest(raw=raw),self.assertRaises(ValueError):m.lines(p)
    def test_raw_DONE_field_count_counter_or_finiteness_changes_refused(self):
        p=self.trace/'raw-done.txt';before=p.read_text();native=m.j(self.trace/'native-statistics.json')
        for raw in [before.replace('DONE ','DONE\n'),before+' extra',before.replace('DONE 3','DONE 4'),before.replace('1.0','nan'),before.replace(' 12 16',' 17 16')]:
            p.write_text(raw)
            with self.subTest(raw=raw),self.assertRaises(ValueError):m.raw_done_contract(self.trace,native)


class SSE(unittest.TestCase):
    def test_split_content_and_reasoning_reconstructed(self):
        self.assertTrue(m.sse_contract(response())['raw_SSE_reconstructed'])
    def test_edited_content_or_reasoning_refused(self):
        for key in ('content', 'reasoning'):
            r = response(); r[key] += 'x'
            with self.subTest(key=key), self.assertRaises(ValueError): m.sse_contract(r)
    def test_missing_or_duplicate_DONE_refused(self):
        for remove in (True, False):
            r = response(); r['raw'] = r['raw'][:-1] if remove else r['raw'] + [r['raw'][-1]]
            with self.subTest(remove=remove), self.assertRaises(ValueError): m.sse_contract(r)
    def test_saved_events_usage_timings_cannot_diverge(self):
        for key in ('events', 'usage', 'timings'):
            r = response(); r[key] = None
            with self.subTest(key=key), self.assertRaises(ValueError): m.sse_contract(r)
    def test_error_length_or_tool_delta_refused(self):
        for event in ({'error': 'fault'}, {'choices': [{'delta': {}, 'finish_reason': 'length'}]},
                      {'choices': [{'delta': {'tool_calls': [{'id': 'bad'}]}}]}):
            r = response(); r['raw'].insert(0, {'line': 'data: ' + json.dumps(event)})
            with self.subTest(event=event), self.assertRaises(ValueError): m.sse_contract(r)


class Fence(unittest.TestCase):
    def setUp(self):
        self.initial = {'memory_max': 80 * 2**30, 'swap_max': 0, 'events_before': {'oom': 1, 'oom_kill': 0}}
        unit = {'Transient': 'yes', 'InvocationID': 'a' * 32, 'ControlGroup': '/user/strata-deepseek-window.service',
                'MemoryMax': 'infinity', 'MemorySwapMax': 'infinity',
                'FragmentPath': '/run/user/1000/systemd/transient/strata-deepseek-window.service'}
        self.initial.update(prior_properties={'MemoryMax': 'max', 'MemorySwapMax': 'max'},
                            unit_before=unit, fragment=unit['FragmentPath'], owned_dropin_directory=unit['FragmentPath'] + '.d')
        self.end = {'passed': True, 'events_after': {'oom': 1, 'oom_kill': 0}, 'events_delta': {'oom': 0, 'oom_kill': 0}}
        self.restore = {'passed': True, 'same_invocation': True, 'children_closed': True,
                        'prior_properties': {'MemoryMax': 'max', 'MemorySwapMax': 'max'},
                        'restored_properties': {'MemoryMax': 'max', 'MemorySwapMax': 'max'}, 'unit_after': copy.deepcopy(unit)}
        self.collected = dict.fromkeys(('passed', 'transient', 'unit_collected', 'fragment_absent', 'dropins_absent'), True)
        self.collected.update(original_invocation=unit['InvocationID'], fragment=unit['FragmentPath'],
                              owned_dropin_directory=unit['FragmentPath'] + '.d')
    def test_complete_fence_and_collection(self):
        self.assertTrue(m.fence_contract(self.initial, self.end, self.restore, self.collected)['passed'])
    def test_OOM_not_cleared_by_success_label(self):
        self.end['events_after']['oom'] += 1; self.end['events_delta']['oom'] += 1
        with self.assertRaises(ValueError): m.fence_contract(self.initial, self.end, self.restore, self.collected)
    def test_changed_limits_or_counter_types(self):
        for key, value in [('memory_max', 76 * 2**30), ('swap_max', False)]:
            i = copy.deepcopy(self.initial); i[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): m.fence_contract(i, self.end, self.restore, self.collected)
    def test_foreign_invocation_or_children_still_open(self):
        for key in ('same_invocation', 'children_closed'):
            r = copy.deepcopy(self.restore); r[key] = False
            with self.subTest(key=key), self.assertRaises(ValueError): m.fence_contract(self.initial, self.end, r, self.collected)
    def test_old_properties_and_collection_are_required(self):
        r = copy.deepcopy(self.restore); r['restored_properties']['MemorySwapMax'] = '0'
        with self.assertRaises(ValueError): m.fence_contract(self.initial, self.end, r, self.collected)
        for key in self.collected:
            c = dict(self.collected); c[key] = False
            with self.subTest(key=key), self.assertRaises(ValueError): m.fence_contract(self.initial, self.end, self.restore, c)
    def test_restoration_cannot_substitute_prior_or_unit_identity(self):
        for key in ('InvocationID', 'ControlGroup', 'FragmentPath'):
            r = copy.deepcopy(self.restore); r['unit_after'][key] += 'x'
            with self.subTest(key=key), self.assertRaises(ValueError): m.fence_contract(self.initial, self.end, r, self.collected)
        r = copy.deepcopy(self.restore)
        r['prior_properties']['MemoryMax'] = r['restored_properties']['MemoryMax'] = '123'
        with self.assertRaises(ValueError): m.fence_contract(self.initial, self.end, r, self.collected)


class TokenizerFiles(Temporary):
    def tokenizer_fixture(self, *, swapped=True):
        self.pack = self.p / 'pack'; self.v = self.p / 'native-vision-v2'
        self.tok = self.v / 'tokenizer'; self.tok.mkdir(parents=True)
        pins = {}
        for name in m.fixtures.TOKENIZER_NAMES:
            path = self.tok / name; path.write_bytes(('synthetic:' + name).encode()); pins[name] = m.runtime.sha(path)
        fallback = self.p / m.fixtures.FALLBACK_TEMPLATE; fallback.parent.mkdir(parents=True, exist_ok=True); fallback.write_text('fallback')
        picker_name = 'native-vision-v2/runtime/serve/dsml.py'
        picker = self.p / picker_name; picker.parent.mkdir(parents=True, exist_ok=True); picker.write_text('picker')
        source = self.tok / 'chat_template.jinja'; selected = fallback if swapped else source
        self.tm = {'tokenizer_source_sha256': pins, 'effective_template': {
            'pack_template_relative_to_E': str(source.relative_to(self.p)), 'pack_template_sha256': pins['chat_template.jinja'],
            'effective_template_relative_to_E': str(selected.relative_to(self.p)), 'effective_template_sha256': m.runtime.sha(selected),
            'pack_template_replaced': swapped, 'api_picker_sha256': m.runtime.sha(picker),
            'selection_policy': 'EXACT_UNCHANGED_B1_DSML_PICKER_WITH_PINNED_V41_FALLBACK'}}
        self.tq = {'files': {str(self.tok / n): v for n, v in pins.items()}}
        self.tq['files'].update({str(fallback): m.runtime.sha(fallback), str(picker): m.runtime.sha(picker)})
        stack = ExitStack(); self.addCleanup(stack.close)
        for key, value in [('E', self.p), ('V', self.v), ('BASE_PACK', self.pack)]: stack.enter_context(patch.object(m.fixtures, key, value))
        stack.enter_context(patch.dict(m.fixtures.SUPPORT_PINS, {m.fixtures.FALLBACK_TEMPLATE: m.runtime.sha(fallback), picker_name: m.runtime.sha(picker)}))


class Tokenizer(TokenizerFiles, unittest.TestCase):
    def setUp(self): super().setUp(); self.tokenizer_fixture()
    def test_exact_fallback_and_unswapped_template_bytes(self):
        self.assertTrue(m.tokenizer_contract(self.tm, self.pack, self.tq)['passed'])
        t = copy.deepcopy(self.tm); x = t['effective_template']; x['pack_template_replaced'] = False
        x['effective_template_relative_to_E'] = x['pack_template_relative_to_E']; x['effective_template_sha256'] = x['pack_template_sha256']
        self.assertTrue(m.tokenizer_contract(t, self.pack, self.tq)['passed'])
    def test_every_tokenizer_and_template_pin_is_required(self):
        for path in self.tq['files']:
            q = copy.deepcopy(self.tq); del q['files'][path]
            with self.subTest(path=path), self.assertRaises(ValueError): m.tokenizer_contract(self.tm, self.pack, q)
    def test_changed_current_bytes_or_mismatched_pin_refused(self):
        path = self.tok / 'vocab.json'; old = path.read_bytes(); path.write_bytes(old + b'x')
        with self.assertRaises(ValueError): m.tokenizer_contract(self.tm, self.pack, self.tq)
        path.write_bytes(old); q = copy.deepcopy(self.tq); q['files'][str(path)] = '0' * 64
        with self.assertRaises(ValueError): m.tokenizer_contract(self.tm, self.pack, q)
    def test_template_traversal_and_selection_substitution_refused(self):
        for key, value in [('effective_template_relative_to_E', '../elsewhere'), ('pack_template_replaced', 1),
                           ('api_picker_sha256', '0' * 64), ('effective_template_sha256', '0' * 64)]:
            t = copy.deepcopy(self.tm); t['effective_template'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): m.tokenizer_contract(t, self.pack, self.tq)
    def test_tokenizer_extra_file_or_alias_refused(self):
        t = copy.deepcopy(self.tm); t['tokenizer_source_sha256']['extra'] = '0' * 64
        with self.assertRaises(ValueError): m.tokenizer_contract(t, self.pack, self.tq)
        path = self.tok / 'vocab.json'; dest = self.p / 'replacement'; path.rename(dest); path.symlink_to(dest)
        with self.assertRaises(ValueError): m.tokenizer_contract(self.tm, self.pack, self.tq)


class Contracts(Temporary,unittest.TestCase):
    def panel(self,required=True):
        cases=[{'id':'case'+str(i)} for i in range(5)];life=[{'id':'life'+str(i),'kind':'prefill-cancel' if i==2 else 'json'} for i in range(4)] if required else []
        manifest={'cases':cases,'lifecycle_cases':life}
        result={'complete':True,'native_request_count':5+len(life),'retry':False,'reason':None,'unrun_ids':[],'DSI1_leftovers':[],
            'rows':cases,'scores':[{'id':c['id'],'passed':True,'status':'NATURAL_RESULT_SOURCE_AND_STATE_PASSED'} for c in cases],
            'lifecycle':{'required':required,'complete':True,'rows':life,'scores':[{'id':c['id'],'passed':True,'status':'CONFIRMED_PREFILL_CANCEL_PASSED' if c['kind']=='prefill-cancel' else 'NATURAL_RESULT_SOURCE_AND_STATE_PASSED'} for c in life],'unrun_ids':[]}}
        return manifest,{'mode':'prose','arm':'A1','private_cleanup_passed':True,'not_a_promotion':True,'arm_results':result}
    def test_typed_poststop88GiB_witness(self):
        self.assertTrue(m.poststop_memory_contract({'passed':True,'required_bytes':88*2**30,'available_bytes':90*2**30})['passed'])
        for key,value in [('passed',False),('required_bytes',80*2**30),('available_bytes',1),('available_bytes',True)]:
            x={'passed':True,'required_bytes':88*2**30,'available_bytes':90*2**30};x[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.poststop_memory_contract(x)
    def test_five_main_and_four_required_lifecycle(self):
        manifest,r=self.panel()
        with patch.object(m.runtime,'lifecycle_required',return_value=True):self.assertEqual(m.complete_contract(r,manifest,'prose','A1')['native_request_count'],9)
    def test_reversed_or_coding_family_refused(self):
        manifest,r=self.panel()
        for mode,arm in [('coding','A1'),('prose','A2'),('prose','B2')]:
            with self.subTest(mode=mode,arm=arm),self.assertRaises(ValueError):m.config.factor(mode,arm)
    def test_partial_retry_unrun_extra_native_or_image_leak_blocks(self):
        manifest,r=self.panel()
        for key,value in [('complete',False),('retry',True),('unrun_ids',['x']),('native_request_count',8),('DSI1_leftovers',['leak']),('reason','HOLD')]:
            x=copy.deepcopy(r);x['arm_results'][key]=value
            with self.subTest(key=key),patch.object(m.runtime,'lifecycle_required',return_value=True),self.assertRaises(ValueError):m.complete_contract(x,manifest,'prose','A1')
    def test_missing_lifecycle_or_failed_case_blocks(self):
        manifest,r=self.panel()
        for key,value in [('complete',False),('rows',[]),('scores',[]),('unrun_ids',['cancel'])]:
            x=copy.deepcopy(r);x['arm_results']['lifecycle'][key]=value
            with self.subTest(key=key),patch.object(m.runtime,'lifecycle_required',return_value=True),self.assertRaises(ValueError):m.complete_contract(x,manifest,'prose','A1')
    def test_wrong_mode_or_private_cleanup_blocks(self):
        manifest,r=self.panel()
        for key,value in [('mode','quality'),('arm','B1'),('private_cleanup_passed',False),('not_a_promotion',False)]:
            x=copy.deepcopy(r);x[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.complete_contract(x,manifest,'prose','A1')
    def test_window_command_and_actual_exit0(self):
        out=self.p/'out';meta=self.p/'meta';cmd=[str(m.runtime.R/'venv/bin/python3.14'),'-B',str(m.runtime.P/'ae_owner.py'),'--phase','--mode','prose','--arm','A1','--output',str(out),'--proof',str(meta/'proof.json')]
        w={'command':cmd,'continued_from':'prior','test_returncode':0,'maintenance_held':True,'maintenance_resume_allowed':True,'restored':False}
        m.window_contract(w,out,meta,'prose','A1')
        for key,value in [('test_returncode',False),('test_returncode',1),('command',cmd+['x']),('maintenance_resume_allowed',False),('continued_from',None)]:
            x=copy.deepcopy(w);x[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.window_contract(x,out,meta,'prose','A1')
    def test_alias_hardlink_and_duplicate_nonfinite_JSON_refused(self):
        p=self.write('x.json',{});link=self.p/'link';link.symlink_to(p)
        with self.assertRaises(ValueError):m.regular(link)
        link.unlink();link.hardlink_to(p)
        with self.assertRaises(ValueError):m.regular(p)
        link.unlink()
        for raw in ('{"x":1,"x":2}','{"x":NaN}'):
            p.write_text(raw)
            with self.subTest(raw=raw),self.assertRaises(ValueError):m.j(p)
    def test_foreign_cached_dependency_not_imported(self):
        p=self.write('fake.py',{});pin=hashlib.sha256(p.read_bytes()).hexdigest()
        with patch.dict(m.sys.modules,{'ae_fake':NS(__file__='/foreign.py')}),patch.object(m.importlib,'import_module') as imp:
            with self.assertRaises(ValueError):m.dependency('ae_fake',p,{'files':{str(p):pin}})
            imp.assert_not_called()
    def test_phase_or_busy_refuses_before_hash(self):
        self.write('STATE.json',{'active_private_phase':'foreign'});a=NS(ChunkProductionHost=Mock())
        with patch.object(m.runtime,'E',self.p),self.assertRaises(ValueError):m.fresh_idle(a,Mock())
        a.ChunkProductionHost.assert_not_called()
        self.write('STATE.json',{});host=Mock();host.idle.return_value=False
        with patch.object(m.runtime,'E',self.p),self.assertRaises(ValueError):m.fresh_idle(NS(ChunkProductionHost=lambda:host),NS(current_binding=lambda s:{'native_pid':123}))
        host.guard_binding.assert_not_called()


class Lifecycle(unittest.TestCase):
    def cancel(self):
        c={'passed':True,'replay':False,'classification':'confirmed_prefill_cancel','recovery_required':True,'client_disconnect_cancels_delta':1,
            'observed_before_cancel':{'state':'reading','read':2048,'total':8471,'first_delta':False}}
        c['transport']={'cancelled':True,'content':'','reasoning':'','tool_calls':[]}
        proof={'native':{'finish':'cancel','generated':0},'observed_tokens':0,'cancelled_control_or_budget':True}
        return c,proof,{'prompt_tokens':8471}
    def test_confirmed_gen0_cancel_with_partial_read(self):
        self.assertTrue(m.cancel_contract(*self.cancel())['confirmed_prefill_cancel'])
    def test_cancel_labels_cannot_replace_native_gen0(self):
        for key,value in [('finish','stop'),('generated',1),('generated',False)]:
            c,p,case=self.cancel();p['native'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.cancel_contract(c,p,case)
    def test_cancel_must_be_before_first_delta_and_partial_prefill(self):
        for key,value in [('state','done'),('read',0),('read',8470),('total',9000),('first_delta',True)]:
            c,p,case=self.cancel();c['observed_before_cancel'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.cancel_contract(c,p,case)
    def test_cancel_requires_release_counter_and_no_budget_stop(self):
        for key,value in [('passed',False),('replay',True),('recovery_required',False),('client_disconnect_cancels_delta',0),('intentional_budget_stop',True),('cleanup_error','survivor')]:
            c,p,case=self.cancel();c[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.cancel_contract(c,p,case)
    def test_followup_changes_only_actual_call_identifiers(self):
        first=m.fixtures.synthetic_call('actual-ID');frozen=m.fixtures.tool_followup(m.fixtures.synthetic_call(m.fixtures.FROZEN_CALL_ID))
        out=m.normalized_followup({'request':frozen},first)
        self.assertEqual(out['messages'][-1]['tool_call_id'],'actual-ID')
        self.assertEqual(out['messages'][-2]['tool_calls'][0]['id'],'actual-ID')
    def test_followup_rejects_wrong_typed_arguments_or_changed_request(self):
        frozen=m.fixtures.tool_followup(m.fixtures.synthetic_call(m.fixtures.FROZEN_CALL_ID))
        first=m.fixtures.synthetic_call('actual');first['tool_calls'][0]['function']['arguments']='{"sku":"PF2-731","quantity":true}'
        with self.assertRaises(ValueError):m.normalized_followup({'request':frozen},first)
        frozen['temperature']=0
        with self.assertRaises(ValueError):m.normalized_followup({'request':frozen},m.fixtures.synthetic_call('actual'))
    def test_tool_fragments_reassembled(self):
        r=response();events=[{'choices':[{'delta':{'tool_calls':[{'index':0,'id':'call','type':'function','function':{'name':'lookup_','arguments':'{"sku":'}}]},'finish_reason':None}]},
            {'choices':[{'delta':{'tool_calls':[{'index':0,'function':{'name':'quote','arguments':'"x"}'}}]},'finish_reason':'tool_calls'}]}]
        r.update(content='',reasoning='',events=events,usage=None,timings=None,finish_reason='tool_calls',tool_calls=[{'id':'call','type':'function','function':{'name':'lookup_quote','arguments':'{"sku":"x"}'}}],raw=[{'line':'data: '+json.dumps(e)} for e in events]+[{'line':'data: [DONE]'}])
        self.assertEqual(m.sse_contract(r,tool=True)['finish'],'tool_calls')
        r['tool_calls'][0]['function']['arguments']='edited'
        with self.assertRaises(ValueError):m.sse_contract(r,tool=True)


class CaseFiles(Temporary):
    def setUp(self):
        super().setUp()
        # The unchanged dependency is pure saved-data code. No producer imports.
        path = m.runtime.E / 'q8-batch-v1/q8_audit.py'
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), '59c396154604496ec01a0ef8d0e3dddf677e31e9b57d91472fb0e0965af3dcd1')
        spec = importlib.util.spec_from_file_location('quality_test_raw_reconcile', path)
        dep = importlib.util.module_from_spec(spec); spec.loader.exec_module(dep); self.reconcile = dep.reconcile
        self.case = {'id': 'test-json', 'kind': 'json', 'expected_reuse': 'zero', 'expected': {'values': [1]},
                     'prompt_ids': [1, 2], 'prompt_tokens': 2,
                     'request': {'messages': [{'role': 'user', 'content': 'synthetic'}], 'max_tokens': 32768,
                                 'reasoning_effort': 100, 'temperature': 1, 'top_p': 1, 'seed': 1}}
        self.response = response(); self.pid = 123
        self.write('skip-controls/test-json/request.json', self.case['request'])
        self.write('skip-controls/test-json/response.json', self.response)
        self.write('native-000/request.json', {'native_pid': 123, 'ids': [1, 2], 'max_new': 32768,
                   'has_images': False, 'sampling': {'temperature': 1, 'top_p': 1, 'seed': 1}})
        self.write('native-000/trace-receipt.json', {'native_pid': 123, 'error': None, 'DONE_observed': True, 'T_lines': 3})
        self.native = {'generated': 3, 'prompt_tokens': 2, 'reused': 0, 'finish': 'stop',
                       'prompt_ms': 1.0, 'decode_ms': 100.0, 'drafts_offered': 3, 'drafts_accepted': 2,'hits':12,'lookups':16}
        self.write('native-000/native-statistics.json', self.native)
        (self.p / 'native-000/tokens.jsonl').write_text(''.join(json.dumps({'token': x, 'seconds': i * .1}) + '\n' for i, x in enumerate([3, 4, 5])))
        binding = self.reconcile(self.p / 'native-000', self.case, self.response, 123)
        self.write('skip-controls/test-json/native-audit.json', binding)
        self.row={'id':'test-json','passed':True,'native':self.native,'observed_tokens':3,'native_decode_tokens_per_second':30.0,'client_seconds':.2,'emitted_token_contract':m.saved.emitted_ids(self.p/'native-000/tokens.jsonl',3)}
        stat_files(self.p/'native-000')
    def run_case(self):
        return m.case_audit(self.case,self.p,0,123,self.row,self.reconcile)


class Cases(CaseFiles,unittest.TestCase):
    def saved_cancel(self):
        self.case.update(kind='prefill-cancel',prompt_ids=list(range(3000)),prompt_tokens=3000)
        request=json.loads((self.p/'native-000/request.json').read_text());request['ids']=self.case['prompt_ids'];self.write('native-000/request.json',request)
        native={**self.native,'generated':0,'prompt_tokens':3000,'finish':'cancel','decode_ms':0.0};self.write('native-000/native-statistics.json',native)
        self.write('native-000/trace-receipt.json',{'native_pid':123,'error':None,'DONE_observed':True,'T_lines':0});(self.p/'native-000/tokens.jsonl').write_text('')
        control,_,_=Lifecycle().cancel();control['observed_before_cancel'].update(read=1024,total=3000)
        self.write('skip-controls/test-json/response.json',control)
        proof=self.reconcile(self.p/'native-000',self.case,control['transport'],123,cancelled=True)
        token=m.saved.emitted_ids(self.p/'native-000/tokens.jsonl',0)
        self.write('skip-controls/test-json/native-audit.json',{**proof,'emitted_token_contract':token})
        self.row={'id':'test-json','passed':True,'native':native,'observed_tokens':0,'emitted_token_contract':token}
        stat_files(self.p/'native-000',cancelled=True)
        return control
    def test_saved_cancel_extra_emitted_field_is_independently_reconciled(self):
        self.saved_cancel();row,_=self.run_case();self.assertTrue(row['transport']['confirmed_prefill_cancel']);self.assertIsNone(row['metric'])
    def test_saved_cancel_mutated_token_contract_refused(self):
        self.saved_cancel();path=self.p/'skip-controls/test-json/native-audit.json';value=json.loads(path.read_text());value['emitted_token_contract']['count']=1;path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):self.run_case()
    def test_saved_cancel_visible_output_refused(self):
        control=self.saved_cancel();control['transport']['content']='unexpected';self.write('skip-controls/test-json/response.json',control)
        with self.assertRaises(ValueError):self.run_case()
    def test_real_native_SSE_ID_and_typed_answer_reconciliation(self):
        row,response_=self.run_case();self.assertEqual(row['metric']['native_decode_tps'],30.0);self.assertEqual(row['observed_tokens'],3)
    def test_pid_cap_DONE_or_sampling_mutation_refused(self):
        for name,key,value in [('request.json','native_pid',124),('request.json','max_new',64),('trace-receipt.json','DONE_observed',False)]:
            p=self.p/'native-000'/name;old=p.read_text();x=json.loads(old);x[key]=value;p.write_text(json.dumps(x))
            with self.subTest(key=key),self.assertRaises(ValueError):self.run_case()
            p.write_text(old)
    def test_float_answer_is_not_integer(self):
        self.case['expected']={'values':[1.0]}
        with self.assertRaises(ValueError):self.run_case()
    def test_edited_native_counters_observed_length_and_rate_refused(self):
        for key,value in [('observed_tokens',4),('native_decode_tokens_per_second',31),('client_seconds',3),('passed',False)]:
            old=copy.deepcopy(self.row);self.row[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.run_case()
            self.row=old
    def test_cache_state_mismatch_refused(self):
        self.case['expected_reuse']='prompt-minus-one'
        with self.assertRaises(ValueError):self.run_case()
    def test_capped_or_missing_SSE_stays_failed(self):
        for key,value in [('finish_reason','length'),('done',False),('cancelled',True)]:
            old=copy.deepcopy(self.response);self.response[key]=value;self.write('skip-controls/test-json/response.json',self.response)
            with self.subTest(key=key),self.assertRaises(ValueError):self.run_case()
            self.response=old


class Terminal(CaseFiles, TokenizerFiles, unittest.TestCase):
    """Synthetic terminal tree; live authority/source-observation adapters mocked.

    Actual saved byte readers, config contract, tokenizer pins, SSE/native
    reconciliation, closure/resource validators and finite scans remain real.
    """
    def setUp(self):
        super().setUp(); self.tokenizer_fixture()
        helper = m.runtime.E / 'decode-optimization-20261028/model-v1'
        path = helper / 'imma_storage.py'
        self.assertEqual(m.runtime.sha(path), 'd03c8f6d69e198e648014b15a00a4a7c3dd986815dac4a391b747924239e0143')
        spec = importlib.util.spec_from_file_location('performance_test_storage', path)
        storage = importlib.util.module_from_spec(spec); spec.loader.exec_module(storage)
        path = helper / 'imma_numeric_controls.py'
        self.assertEqual(m.runtime.sha(path), 'cb3252d95fdbeef733b7f14a1dea1629f59f2d7f6b741709b95b4ac654eab323')
        names = {'owned_storage_snapshot', 'dump_snapshot', 'dump_size', 'finite_dump'}
        tree = ast.parse(path.read_text()); funcs = [x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name in names]
        self.assertEqual({x.name for x in funcs}, names)
        ns = dict(array=array, hashlib=hashlib, math=math, os=os, pathlib=pathlib, stat=stat, sys=sys, storage=storage)
        exec(compile(ast.Module(body=funcs, type_ignores=[]), str(path), 'exec'), ns)
        numerical = NS(**{n: ns[n] for n in names})
        self.output = self.p / 'results/adaptive-cache-prose-v1-A1-20261030T000000Z'
        self.folder = self.output / 'native'; self.folder.mkdir(parents=True)
        meta = self.p / 'maintenance'; meta.mkdir()
        window = self.p / 'windows/20261030T000001Z.json'
        self.write(str(window.relative_to(self.p)), {'command': [str(self.p / 'venv/bin/python3.14'), '-B', str(self.p / 'ae_owner.py'),
            '--phase', '--mode', 'prose', '--arm', 'A1', '--output', str(self.output), '--proof', str(meta / 'proof.json')],
            'continued_from': 'synthetic-clean-parent', 'test_returncode': 0, 'maintenance_held': True,
            'maintenance_resume_allowed': True, 'restored': False})
        window.with_suffix('.telemetry.jsonl').write_text(json.dumps({'root_free_bytes': 130 * 2**30,
            'swap_pages': {'pswpout': 0}, 'kernel_capture_returncode': 0, 'kernel_fault_lines': []}) + '\n')
        def emit(path, obj): return self.write(str(path.relative_to(self.p)), obj)
        cases=[];rows=[]
        first=m.fixtures.synthetic_call('actual-731')
        frozen=m.fixtures.tool_followup(m.fixtures.synthetic_call(m.fixtures.FROZEN_CALL_ID))
        for i in range(9):
            case=copy.deepcopy(self.case);case['id']='terminal-'+str(i)
            resp=copy.deepcopy(self.response);native=copy.deepcopy(self.native)
            if i==4:
                case.update(kind='prose',expected_last_sentence='Complete end.');resp['content']='Synthetic prose. Complete end.'
            elif i==5:
                case.update(id='ae-prose-tool',kind='tool',request=copy.deepcopy(m.fixtures.TOOL_REQUEST))
                resp.update(first);resp.update(content='',reasoning='')
            elif i==6:
                case.update(kind='json',dependency='ae-prose-tool',request=frozen,expected=m.fixtures.TOOL_EXPECTED)
                resp['content']=json.dumps(case['expected'])
            elif i==7:
                case.update(kind='prefill-cancel',prompt_ids=list(range(3000)),prompt_tokens=3000)
                native.update(generated=0,prompt_tokens=3000,decode_ms=0.0,finish='cancel')
            elif i==8:
                case.update(kind='literal',dependency='terminal-7',expected='RECOVERED_Q8_LITERAL')
                resp['content']=case['expected']
            if i!=7:
                event={'choices':[{'delta':{'content':resp['content'],'reasoning_content':resp['reasoning']},'finish_reason':resp['finish_reason']}],
                       'usage':{'completion_tokens':3,'prompt_tokens':2},'timings':{'predicted_n':3}}
                if i==5:
                    event['choices'][0]['delta']={'tool_calls':[{'index':0,**first['tool_calls'][0]}]}
                resp.update(events=[event],usage=event['usage'],timings=event['timings'],
                    raw=[{'line':'data: '+json.dumps(event)},{'line':'data: [DONE]'}])
            trace=self.folder/('native-%03d'%i);shutil.copytree(self.p/'native-000',trace)
            native['prompt_tokens']=case['prompt_tokens'];emit(trace/'native-statistics.json',native)
            request={'native_pid':123,'ids':case['prompt_ids'],'max_new':32768,'has_images':False,
                     'sampling':{'temperature':1,'top_p':1,'seed':1}}
            emit(trace/'request.json',request)
            if i==7:
                emit(trace/'trace-receipt.json',{'native_pid':123,'error':None,'DONE_observed':True,'T_lines':0})
                (trace/'tokens.jsonl').write_text('')
                resp,_,_=Lifecycle().cancel();resp['observed_before_cancel'].update(read=1024,total=3000)
            dest=self.folder/'skip-controls'/case['id']
            actual=m.fixtures.tool_followup(first) if i==6 else case['request']
            emit(dest/'request.json',actual);emit(dest/'response.json',resp)
            check=self.reconcile(trace,case,resp['transport'] if i==7 else resp,123,cancelled=i==7)
            token=m.saved.emitted_ids(trace/'tokens.jsonl',check['observed_tokens'])
            emit(dest/'native-audit.json',{**check,'emitted_token_contract':token} if i==7 else check)
            row={'id':case['id'],'passed':True,'native':native,'observed_tokens':check['observed_tokens'],'emitted_token_contract':token}
            if i!=7:row.update(native_decode_tokens_per_second=30.0,client_seconds=.2)
            stat_files(trace,index=i,cancelled=i==7);cases.append(case);rows.append(row)
        maincases=cases[:5];lifecases=cases[5:]
        manifest = {**self.tm, 'mode': 'prose', 'context': 1048576, 'default_output': 262144,
            'policy': m.fixtures.POLICY, 'cases': maincases, 'lifecycle_cases': lifecases, 'pack_relative_to_E': 'pack',
            'expected_mode1_activation_skipped_tokens': []}
        emit(self.p / 'prose-fixtures-A.json', manifest); emit(self.output / 'fixtures.json', manifest)
        base = {'exe': str(m.config.D / 'bin/maya-ds4'), 'tokenizer': str(self.tok),
                'args': ['--pack', str(self.pack), '--expert-profile', 'seed'], 'env': {}}
        stack = ExitStack(); self.addCleanup(stack.close)
        for module, key, value in [(m.runtime, 'P', self.p), (m.runtime, 'E', self.p), (m.runtime, 'R', self.p),
                                    (m.config, 'E', self.p), (m.config, 'BASE_PACK', self.pack),
                                    (m.config, 'BASE_NORMALIZED', m.config.normalized(base))]:
            stack.enter_context(patch.object(module, key, value))
        c = m.config.make_config(base, self.folder, 'prose', 'A1'); factor = m.config.factor('prose', 'A1')
        emit(self.p / 'base-config.json', base); emit(self.output / 'candidate-config.json', c)
        emit(self.output / 'candidate-config.shared-settings.json', {'max_tokens': 262144})
        configsha = m.runtime.sha(self.output / 'candidate-config.json')
        emit(self.folder / 'native-ready.json', {'pid': 123}); (self.folder / 'engine.log').write_text('synthetic startup')
        emit(self.output / 'startup-health.json', {}); emit(self.output / 'startup-models.json', {})
        actual = {'synthetic_observation': True}
        emit(self.output / 'startup-audit.json', {**actual, 'actual_process': {
            'actual_argv': m.config.expected_native_argv(c), 'controlled_env': c['env'],
            'actual_cgroup': '0::/user/strata-deepseek-window.service', 'same_executable': True,
            'native_sha256': m.config.BASE_NATIVE, 'native_pid': 123, 'start_ticks': 10},
            'native_file_limit_raw': 'Max file size unlimited unlimited bytes'})
        emit(self.output / 'server-start.json', {'pid': 122, 'argv': [str(self.p / 'venv/bin/python3.14'), '-u', '-B',
            str(self.p / 'ae_owner.py'), '--entry', '--mode', 'prose', '--arm', 'A1', '--config',
            str(self.output / 'candidate-config.json'), '--config-sha256', configsha, '--trace-directory', str(self.folder)]})
        emit(self.folder / 'entry-audit.json', {'server_pid': 122, 'startup_retries': 0, 'default_effort': 100,
            'native_sha256': m.config.BASE_NATIVE, 'config_sha256': configsha, 'owned_window': str(window),
            'context': 1048576, 'output_allowance': 262144, 'request_scoped_STAT_observer':True, 'adaptive_cache_policy': factor})
        close = {'native_pid': 123, 'server_pid': 122, 'returncode': 0, 'closed': True}
        (self.folder / 'native-close.jsonl').write_text(json.dumps(close) + '\n'); (self.folder / 'server.log').write_text('[strata] stopped')
        emit(self.folder / 'server-cleanup.json', {'passed': True, 'server_pid': 122, 'server_returncode': 0,
            'grace_timeout': False, 'application_stopped': True, 'native_ready_pid': 123, 'wait_error': None, 'native_close': [close]})
        fence = Fence(); fence.setUp()
        emit(self.output / 'private-memory-fence.json', fence.initial)
        emit(self.output / 'private-memory-fence-restored.json', fence.restore)
        emit(meta / 'private-memory-fence-collected.json', fence.collected)
        original_seed=Path(__file__).parent/'profile-seed.bin'
        shutil.copyfile(original_seed,self.output/'profile-seed-at-start.bin')
        shutil.copyfile(original_seed,self.p/'profile-seed.bin')
        emit(self.output / 'receipt.json', {'mode': 'prose', 'arm': 'A1', 'private_cleanup_passed': True,
            'not_a_promotion': True, 'resource_fence_terminal': fence.end, 'arm_results': {
                'complete': True, 'native_request_count': 9, 'retry': False, 'reason': None, 'unrun_ids': [], 'DSI1_leftovers': [],
                'lifecycle':{'required':True,'complete':True,'rows':rows[5:],'scores':[{'id':x['id'],'passed':True,'status':'CONFIRMED_PREFILL_CANCEL_PASSED' if x['kind']=='prefill-cancel' else 'NATURAL_RESULT_SOURCE_AND_STATE_PASSED'} for x in lifecases],'unrun_ids':[]}, 'rows': rows[:5], 'mode1_activation': {'activation_early_rows': [332]},
                'scores': [{'id': x['id'], 'passed': True, 'status': 'NATURAL_RESULT_SOURCE_AND_STATE_PASSED'} for x in maincases]}})
        identity = {'native_sha256': m.config.BASE_NATIVE, 'config_sha256': m.config.BASE_SHA, 'context': 1048576,
            'output_default': 262144, 'prompt_skip_mode': 1, 'prefill_chunk': 4096, 'Q8': [1, 1], 'DSpark': True, 'images': True,
            'runtime_ablation': True, 'TP': 1, 'all_CPU_experts_RAM': True, 'native_pid': 321, 'start_binding': {'native_pid': 321}}
        verified = {'passed': True, 'selected_identity': identity, 'public': {'unauthenticated_models': 401,
            'authenticated_models': 200, 'known_answer_passed': True, 'SSE_done': True, 'finish': 'stop'},
            'health': {'loaded': True, 'max_context': 1048576, 'images': True,
                       'switcher': {'active_model': 'deepseek', 'default_model': 'deepseek', 'fault': None}}}
        emit(meta/'post-stop-memory.json',{'passed':True,'available_bytes':90*2**30,'required_bytes':88*2**30})
        emit(meta/'public-default-output-request.json',lc.PUBLIC_DEFAULT_REQUEST)
        (meta / 'public-default-output-sse.txt').write_text('data: {"choices":[{"delta":{"content":"READ"},"finish_reason":null}]}\ndata: {"choices":[{"delta":{"content":"Y"},"finish_reason":"stop"}]}\ndata: [DONE]\n')
        emit(meta / 'old-owner-close.json', {'passed': True, 'binding': {}, 'native_close': {}, 'before': {}, 'after': {}})
        for name in ('ae_audit.py', 'ae_dispatch.py'): (self.p / name).write_text('qualified synthetic source boundary')
        q = {'files': {**self.tq['files'],str(self.p/'profile-seed.bin'):m.runtime.sha(self.p/'profile-seed.bin')}, 'allowed_automatic_cuts': {'A': [[19, 21]]}}
        for name in ('ae_audit.py', 'ae_dispatch.py', 'prose-fixtures-A.json'): q['files'][str(self.p / name)] = m.runtime.sha(self.p / name)
        emit(self.p / 'prose-qualification.json', q); qpin = m.runtime.sha(self.p / 'prose-qualification.json')
        emit(meta / 'state.json', {'status': m.runtime.statuses('prose')['complete'], 'mode': 'prose', 'arm': 'A1',
            'output': str(self.output), 'proof_path': str(meta / 'proof.json'), 'controller_pid': 55,
            'qualification_sha256': qpin, 'window': str(window), 'verified': verified})
        emit(meta / 'proof.json', {'qualified_for_owned_adaptive_cache': True, 'mode': 'prose', 'arm': 'A1',
            'output': str(self.output), 'qualification_sha256': qpin, 'files': q['files']})
        emit(self.p / 'prose-arms.json', {'A1': {'attempted': True, 'controller_pid': 55, 'output': str(self.output)}})
        modules = {'ae_controls': NS(startup=Mock(return_value=actual)), 'imma_numeric_controls': numerical,
                   'imma_storage': storage, 'q8_audit': NS(reconcile=self.reconcile),
                   'skip_controls': NS(activation=Mock(return_value={'activation_early_rows': [332]})), 'lc_audit': lc}
        for obj, name, value in [(m, 'fresh_idle', Mock()), (m.runtime, 'support', Mock(return_value=(Mock(), Mock(),
            NS(binding_contract=Mock()), NS(close_contract=Mock(return_value=True)), Mock()))),
            (m.runtime, 'qualified', Mock(return_value=q)), (m.runtime,'encoded_path',Mock(return_value=self.p/'prose-fixtures-A.json')),
            (m.runtime,'performance_manifest',Mock(return_value=manifest)), (m.runtime,'lifecycle_required',Mock(return_value=True)), (m.runtime, 'owned_paths', Mock(return_value=(self.output, meta))),
            (m.runtime, 'validate_manifest', Mock()), (m, 'dependency', Mock(side_effect=lambda name, path, q: modules[name]))]:
            stack.enter_context(patch.object(obj, name, value))
    def test_full_saved_terminal_keeps_raw_config_SSE_native_and_cleanup_gates(self):
        result=m.audit('prose','A1');self.assertTrue(result['passed']);self.assertEqual(len(result['rows']),9)
        self.assertEqual(result['main_metric']['generated_tokens'],3);self.assertFalse(result['accepted'])
        self.assertFalse(result['deployment_authorized']);self.assertFalse(list(self.folder.glob('logits.*')))
    def test_raw_public_stream_failure_blocks_despite_saved_success(self):
        (self.p/'maintenance/public-default-output-sse.txt').write_text('data: [DONE]\n')
        with self.assertRaises(ValueError):m.audit('prose','A1')
    def test_timed_dump_or_fsize_file_refused(self):
        (self.folder/'logits.1.f32').write_bytes(b'xxxx')
        with self.assertRaises(ValueError):m.audit('prose','A1')
    def test_required_poststop_floor_not_merely_archived(self):
        path=self.p/'maintenance/post-stop-memory.json';value=json.loads(path.read_text());value['available_bytes']=1;path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):m.audit('prose','A1')
    def test_changed_initial_profile_seed_blocks(self):
        (self.output/'profile-seed-at-start.bin').write_bytes(b'wrong')
        with self.assertRaises(ValueError):m.audit('prose','A1')
    def test_missing_raw_stat_samples_blocks(self):
        (self.folder/'native-000/stat-lines.jsonl').write_text('')
        with self.assertRaises(ValueError):m.audit('prose','A1')
    def test_missing_entry_observer_flag_refused(self):
        p=self.folder/'entry-audit.json';d=json.loads(p.read_text());d.pop('request_scoped_STAT_observer');p.write_text(json.dumps(d))
        with self.assertRaises(ValueError):m.audit('prose','A1')
    def test_private_API_nonzero_blocks_saved_result(self):
        path=self.folder/'server-cleanup.json';value=json.loads(path.read_text());value['server_returncode']=1;path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):m.audit('prose','A1')


if __name__=='__main__':unittest.main()
