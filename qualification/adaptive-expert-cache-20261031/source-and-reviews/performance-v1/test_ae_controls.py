"""Synthetic negatives for the new cache-policy boundary. No GPU/service action."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
import hashlib
import importlib.util
import importlib
import time
import io
import queue
import threading
import traceback
from unittest.mock import Mock, patch

import ae_controls as c
import ae_runtime as r


STAT = ('STAT tok_s=40.00 ms_tok=25.00 vram_hit=0.7500 cpu=1.500 ram=1.500 '
        'promo=0.125 engram_ms=0.100 vram_used=11000 ram_used=4360 cpu_n=4360 '
        'vram_gb=115.00 ram_gb=40.00\n')


class StatCapture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        # Actual pinned API reader and existing Trace, synthetic queue/process only.
        fixtures=r.original_module('ms_fixtures');self.server=fixtures.load_support().server
        path=r.E/'prefill-v2/native_observer.py'
        self.assertEqual(r.sha(path),'d1f612c0772dd4afe10ec717506fbb7f8920a018d8e9d0c186c7b083df5b7587')
        spec=importlib.util.spec_from_file_location('ae_test_original_trace',path)
        observer=importlib.util.module_from_spec(spec);spec.loader.exec_module(observer)
        server=self.server
        class Engine:
            generate=server.StrataEngine.generate
            _parse_done=server.StrataEngine._parse_done
            _stall_check=server.StrataEngine._stall_check
            _silent=server.StrataEngine._silent
            def __init__(self):
                self.lines=queue.Queue();self.proc=types.SimpleNamespace(pid=71,stdin=io.StringIO(),kill=Mock(),wait=Mock())
                self.max_context=1048576;self.info={};self.can_stop=True;self.batch=0
                self.silence_s=0;self.last={};self.gpu_busy=None;self.activity_reads=0
            def _activity(self):
                self.activity_reads+=1;return (float(self.activity_reads),0)
            def alive(self):return True
            def exit_code(self):return 1
            def sampling_keys(self,sampling):return ''
        self.engine=c.stat_trace_class(observer.trace_class(Engine,self.root),self.root)()
        self.original_queue=self.engine.lines

    def put(self,*lines):
        for line in lines:self.original_queue.put(line)

    def generate(self,cancel=None):
        return self.engine.generate([1,2,3],32768,{},cancel or threading.Event())

    def receipt(self):return json.loads((self.root/'native-000/stat-receipt.json').read_text())

    def test_real_API_reader_STAT_T_DONE_preserved(self):
        self.put('RESUME 0\n','PP 3 3 1 3000\n',STAT,'T 7\n','T 1\n',STAT,'DONE 2 3 1.0 50.0 stop 1 2 0 30 40\n')
        self.assertEqual(list(self.generate()),[None,7,1])
        rows=[json.loads(x) for x in (self.root/'native-000/stat-lines.jsonl').read_text().splitlines()]
        self.assertEqual([x['raw'] for x in rows],[STAT.rstrip('\n')]*2)
        self.assertEqual([x['native_pid'] for x in rows],[71,71]);self.assertEqual([x['trace_number'] for x in rows],[0,0])
        self.assertLessEqual(rows[0]['seconds'],rows[1]['seconds'])
        receipt=self.receipt();self.assertTrue(receipt['complete']);self.assertEqual(receipt['samples'],2)
        self.assertEqual(receipt['raw_lines_sha256'],hashlib.sha256((STAT*2).encode()).hexdigest())
        self.assertEqual(self.engine.last['hits'],30);self.assertEqual(self.engine.last['lookups'],40)
        self.assertEqual(self.engine.proc.stdin.getvalue(),'GEN 32768 1,2,3\n')
        self.assertIs(self.engine.lines,self.original_queue)

    def test_real_API_generator_close_drains_terminal_STAT_and_DONE(self):
        self.put('T 7\n',STAT,'DONE 1 3 1.0 2.0 cancel 0 0 0 0 0\n')
        gen=self.generate();self.assertEqual(next(gen),7);gen.close()
        self.assertIn('STOP\n',self.engine.proc.stdin.getvalue())
        self.assertTrue(self.receipt()['complete']);self.assertEqual(self.receipt()['samples'],1)
        self.assertEqual(self.engine.last['finish'],'cancel');self.assertIs(self.engine.lines,self.original_queue)

    def test_zero_output_cancel_allows_empty_STAT_series(self):
        flag=threading.Event();flag.set()
        self.put('PP 1024 8469 1 1\n','DONE 0 8469 1.0 0.0 cancel 0 0 0 0 0\n')
        self.assertEqual(list(self.generate(flag)),[])
        self.assertTrue(self.receipt()['complete']);self.assertEqual(self.receipt()['samples'],0)
        self.assertEqual((self.root/'native-000/stat-lines.jsonl').read_text(),'')

    def test_real_API_ERR_preserved_beside_incomplete_observation(self):
        self.put(STAT,'ERR native-primary\n')
        with self.assertRaisesRegex(ValueError,'native-primary') as caught:list(self.generate())
        self.assertFalse(self.receipt()['complete']);self.assertIn('native-primary',self.receipt()['primary_error'])
        self.assertIn('STAT observation',str(caught.exception.__notes__))
        self.assertIs(self.engine.lines,self.original_queue)

    def test_real_API_EOF_preserved(self):
        self.put(None)
        with self.assertRaises(self.server.EngineDied):list(self.generate())
        self.assertFalse(self.receipt()['DONE_observed']);self.assertIs(self.engine.lines,self.original_queue)

    def test_queue_timeout_and_put_semantics_unchanged(self):
        raw=queue.Queue();capture=Mock();tap=c.StatQueueTap(raw,capture)
        with self.assertRaises(queue.Empty):tap.get(block=False)
        tap.put(None);self.assertIsNone(tap.get(timeout=.1));capture.assert_not_called()

    def test_actual_reader_queue_empty_runs_exact_watchdog_before_DONE(self):
        self.assertGreater(self.server.ENGINE_STALL_S,0)
        self.assertIs(type(self.engine)._stall_check,self.server.StrataEngine._stall_check)
        original=self.original_queue.get;calls=[]
        self.put(STAT,'DONE 0 3 1.0 0.0 cancel 0 0 0 0 0\n')
        def get(*args,**kwargs):
            calls.append(kwargs)
            if len(calls)==1:raise queue.Empty
            return original(*args,**kwargs)
        with patch.object(self.original_queue,'get',side_effect=get):
            self.assertEqual(list(self.generate()),[])
        self.assertEqual(calls[0],{'timeout':.5});self.assertEqual(self.engine.activity_reads,1)
        self.assertTrue(self.receipt()['complete']);self.assertEqual(self.receipt()['samples'],1)
        self.engine.proc.kill.assert_not_called();self.engine.proc.wait.assert_not_called()

    def test_exact_watchdog_frozen_synthetic_process_still_refused(self):
        # Only synthetic activity/process operations: never inspect or signal PID 71.
        state={'base':(0.,0)}
        with patch.object(self.engine,'_activity',return_value=(0.,0)),patch.object(self.server.time,'monotonic',return_value=100.):
            with self.assertRaisesRegex(self.server.EngineSilent,'frozen'):
                self.engine._stall_check(0.,state,1.)
        self.assertTrue(self.engine.ended)
        self.engine.proc.kill.assert_called_once_with();self.engine.proc.wait.assert_called_once_with(timeout=20)

    def test_capture_write_fault_drains_before_refusal(self):
        self.put(STAT,'T 1\n','DONE 1 3 1.0 2.0 stop 0 0 0 1 1\n')
        original=Path.open;fail=[True]
        def opened(path,*args,**kwargs):
            if path.name=='stat-lines.jsonl' and fail[0]:fail[0]=False;raise OSError('observer-write')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',opened),self.assertRaisesRegex(ValueError,'Incomplete STAT'):list(self.generate())
        self.assertTrue(self.engine.trace_done);self.assertEqual(self.engine.last['generated'],1)
        self.assertIn('observer-write',self.receipt()['capture_error']);self.assertFalse(self.receipt()['complete'])

    def test_capture_fault_does_not_replace_native_primary(self):
        self.put('STAT bad\nembedded\n','ERR primary\n')
        with self.assertRaisesRegex(ValueError,'primary'):list(self.generate())
        self.assertIn('single STAT',self.receipt()['capture_error']);self.assertIn('primary',self.receipt()['primary_error'])

    def test_embedded_or_overlong_STAT_fail_closed_after_DONE(self):
        self.put('STAT '+('x'*4097)+'\n','DONE 0 3 1.0 0.0 cancel 0 0 0 0 0\n')
        with self.assertRaisesRegex(ValueError,'Incomplete STAT'):list(self.generate())
        self.assertTrue(self.receipt()['DONE_observed']);self.assertFalse(self.receipt()['complete'])

    def test_foreign_PID_STAT_association_refused(self):
        self.put(STAT,'DONE 0 3 1.0 0.0 cancel 0 0 0 0 0\n');original=self.original_queue.get
        def get(*args,**kwargs):
            line=original(*args,**kwargs)
            if isinstance(line,str) and line.startswith('STAT '):self.engine.proc.pid=99
            return line
        with patch.object(self.original_queue,'get',side_effect=get),self.assertRaisesRegex(ValueError,'Incomplete STAT'):
            list(self.generate())
        self.assertIn('Unowned STAT',self.receipt()['capture_error'])

    def test_request_ordinal_and_zero_cross_request_leak(self):
        for _ in range(2):
            self.put(STAT,'T 1\n','DONE 1 3 1.0 2.0 stop 0 0 0 1 1\n');self.assertEqual(list(self.generate()),[1])
        second=json.loads((self.root/'native-001/stat-receipt.json').read_text())
        self.assertEqual(second['trace_number'],1);self.assertEqual(second['samples'],1)
        self.assertEqual(self.receipt()['trace_number'],0)

    def test_concurrent_generate_refused_without_consuming_line(self):
        self.put('T 7\n',STAT,'DONE 1 3 1.0 2.0 cancel 0 0 0 0 0\n')
        gen=self.generate();next(gen);before=self.original_queue.qsize()
        with self.assertRaisesRegex(ValueError,'Concurrent'):next(self.generate())
        self.assertEqual(self.original_queue.qsize(),before);gen.close()



class ActualHTTPStatCapture(unittest.TestCase):
    def test_actual_API_loopback_tap_natural_cancel_release_and_recovery(self):
        fixtures=r.original_module('ms_fixtures');support=fixtures.load_support()
        api=support.server;tok=support.tokenizer()
        r.lifecycle_helper()  # verifies the unchanged transport import and origin
        protocol=importlib.import_module('protocol')
        self.assertEqual(Path(protocol.__file__),r.E/'prefill-v2/protocol.py')
        path=r.E/'prefill-v2/native_observer.py'
        self.assertEqual(r.sha(path),'d1f612c0772dd4afe10ec717506fbb7f8920a018d8e9d0c186c7b083df5b7587')
        spec=importlib.util.spec_from_file_location('ae_http_original_trace',path)
        observer=importlib.util.module_from_spec(spec);spec.loader.exec_module(observer)
        seen=[];entered=threading.Event();cancel_seen=threading.Event();watchdog_seen=threading.Event();threads=[]
        class Engine(api.MockEngine):
            _stall_check=api.StrataEngine._stall_check
            _silent=api.StrataEngine._silent
            def __init__(inner):
                super().__init__(tok,'</think>\n\nRECOVERED_Q8_LITERAL',max_context=1048576)
                inner.script=tok.encode('</think>\n\nRECOVERED_Q8_LITERAL')+[1]
                inner.lines=queue.Queue();inner.proc=types.SimpleNamespace(pid=321,stdin=io.StringIO(),kill=Mock(),wait=Mock())
                inner.info={};inner.can_stop=True;inner.batch=0;inner.last={};inner.silence_s=0
                inner.block_next=False;inner.gpu_busy=None;inner.activity_reads=0
            def _activity(inner):
                inner.activity_reads+=1;watchdog_seen.set();return (float(inner.activity_reads),0)
            def alive(inner):return True
            def exit_code(inner):return 1
            def sampling_keys(inner,sampling):return ''
            def _parse_done(inner,line):return api.StrataEngine._parse_done(inner,line)
            def generate(inner,ids,max_new,sampling,cancel,embeddings=None):
                seen.append({'ids':list(ids),'cap':max_new,'sampling':dict(sampling),'images':bool(embeddings)})
                block=inner.block_next;inner.block_next=False;thread=None
                if block:
                    def prefill():
                        entered.set();inner.lines.put('PP 1 %d 1 1000\n'%len(ids))
                        if not cancel.wait(10):
                            inner.lines.put('ERR synthetic prefill cancellation not observed\n');return
                        cancel_seen.set();inner.lines.put('DONE 0 %d 1.0 0.0 cancel 0 0 0 0 0\n'%len(ids))
                    thread=threading.Thread(target=prefill,daemon=True);threads.append(thread);thread.start()
                else:
                    inner.lines.put(STAT)
                    for token in inner.script:inner.lines.put('T %d\n'%token)
                    inner.lines.put(STAT)
                    inner.lines.put('DONE %d %d 1.0 2.0 stop 3 5 0 4 8\n'%(len(inner.script),len(ids)))
                try:yield from api.StrataEngine.generate(inner,ids,max_new,sampling,cancel,embeddings)
                finally:
                    if thread is not None:thread.join(2)
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory).resolve();engine=c.stat_trace_class(observer.trace_class(Engine,folder),folder)()
            original_queue=engine.lines
            vision=support.ds4_vision.Vision(support.ds4_vision.Geometry(),folder,api.Vision.load)
            svc=api.Service(engine,tok,api.ChatTemplate(support.dsml.pick_template(fixtures.V/'tokenizer/chat_template.jinja')[0]),
                            model_name=fixtures.POLICY['model'],vision=vision,fit_max_tokens=False)
            svc.set_family('deepseek41');svc.answer_room=False;svc.reasoning_budget_configured=True
            svc.reasoning_budget_tokens=0;svc.reasoning_loop_recovery=False;svc.repeat_stop_tokens=0
            http=api.serve(svc,'127.0.0.1',0);http_errors=[];original_handle_error=http.handle_error
            def handle_error(request,address):
                http_errors.append(traceback.format_exc());original_handle_error(request,address)
            http.handle_error=handle_error
            server_thread=threading.Thread(target=http.serve_forever,daemon=True);server_thread.start()
            base='http://127.0.0.1:'+str(http.server_port);streams=[]
            case=json.loads(r.encoded_path('prose','A').read_text())['lifecycle_cases'][3]
            def work():return protocol.json_get(base,'/v1/telemetry')['work']
            def idle():protocol.wait_for(lambda:all(work()[k]==0 for k in ('active','queued','admission_reserved')),5,'CPU API not released')
            def start():
                stream=protocol.Stream(base,case['request']).start();streams.append(stream);return stream
            try:
                result=start().result(5);idle()
                self.assertEqual(result['content'],case['expected']);self.assertTrue(result['done'])
                first=json.loads((folder/'native-000/stat-receipt.json').read_text())
                self.assertTrue(first['complete']);self.assertEqual(first['samples'],2)
                before=work()['client_disconnect_cancels'];engine.block_next=True
                own=start();self.assertTrue(entered.wait(3));self.assertTrue(watchdog_seen.wait(3));self.assertFalse(own.first_delta.is_set())
                own.cancel();idle();self.assertTrue(cancel_seen.is_set())
                self.assertEqual(work()['client_disconnect_cancels'],before+1)
                self.assertEqual(own.result(1)['content'],'');self.assertFalse(own.result(1)['done'])
                middle=json.loads((folder/'native-001/stat-receipt.json').read_text())
                self.assertTrue(middle['complete']);self.assertEqual(middle['samples'],0)
                self.assertEqual(json.loads((folder/'native-001/native-statistics.json').read_text())['generated'],0)
                result=start().result(5);idle()
                self.assertEqual(result['content'],case['expected']);self.assertTrue(result['done'])
                self.assertTrue(json.loads((folder/'native-002/stat-receipt.json').read_text())['complete'])
                self.assertEqual(len(seen),3);self.assertTrue(all(x['cap']==32768 and x['ids']==case['prompt_ids'] and not x['images'] for x in seen))
                self.assertIs(engine.lines,original_queue)
                self.assertGreater(engine.activity_reads,0);engine.proc.kill.assert_not_called();engine.proc.wait.assert_not_called()
                self.assertTrue(all(not t.is_alive() for t in threads));self.assertNotIn('torch',r.sys.modules)
            finally:
                for stream in streams:
                    if stream.thread.is_alive():stream.cancel()
                http.shutdown();http.server_close();server_thread.join(2);vision.shutdown()
                for thread in threads:thread.join(2)
                self.assertEqual(http_errors,[],'Actual HTTP handler exception: '+repr(http_errors))


def sample():
    case = {'id': 'new', 'kind': 'json', 'request': {'max_tokens': 32768},
            'expected': {'n': 3}, 'expected_reuse': 'zero', 'prompt_tokens': 7000}
    response = {'status': 200, 'done': True, 'finish_reason': 'stop', 'content': '{"n":3}'}
    proof = {'observed_tokens': 5, 'native': {'finish': 'stop', 'generated': 5, 'reused': 0,
             'drafts_offered': 9, 'drafts_accepted': 4, 'prompt_ms': 1000., 'decode_ms': 100.}}
    return case, response, proof


class ScoreTests(unittest.TestCase):
    def test_natural_exact_known_answer(self):
        case, response, proof = sample(); out = c.score(case, response, proof, quality=True)
        self.assertTrue(out['passed']); self.assertEqual(out['native_decode_tokens_per_second'], 50.)
        self.assertFalse(out['general_quality_or_equivalence_claim'])

    def test_wrong_json_type(self):
        case, response, proof = sample(); response['content'] = '{"n":3.0}'
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)

    def test_duplicate_key(self):
        case, response, proof = sample(); response['content'] = '{"n":2,"n":3}'
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)

    def test_nonfinite_json(self):
        case, response, proof = sample(); response['content'] = '{"n":NaN}'
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)

    def test_cap_is_not_speed_result(self):
        case, response, proof = sample(); response['finish_reason'] = 'length'
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)

    def test_wrong_native_finish(self):
        case, response, proof = sample(); proof['native']['finish'] = 'cancel'
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)

    def test_no_DONE(self):
        case, response, proof = sample(); response['done'] = False
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)

    def test_budget_partial(self):
        case, response, proof = sample(); response['intentional_budget_stop'] = True
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)

    def test_zero_output(self):
        case, response, proof = sample(); proof['observed_tokens'] = proof['native']['generated'] = 0
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)

    def test_fullcap_even_with_stop(self):
        case, response, proof = sample(); proof['observed_tokens'] = proof['native']['generated'] = 32768
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)

    def test_warm_reuse(self):
        case, response, proof = sample(); case['expected_reuse'] = 'prompt-minus-one'; proof['native']['reused'] = 6999
        self.assertTrue(c.score(case, response, proof, quality=False)['passed'])

    def test_bad_warm_reuse(self):
        case, response, proof = sample(); case['expected_reuse'] = 'prompt-minus-one'
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)

    def test_actual_drafter_required_quality(self):
        case, response, proof = sample(); proof['native']['drafts_accepted'] = 0
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=True)

    def test_draft_overacceptance_fault(self):
        case, response, proof = sample(); proof['native']['drafts_accepted'] = 10
        with self.assertRaises(ValueError): c.score(case, response, proof, quality=False)

    def test_nonfinite_timing_fault(self):
        case, response, proof = sample(); proof['native']['decode_ms'] = float('nan')
        with self.assertRaises(ValueError): c.score(case, response, proof, quality=False)

    def test_prose_manual_pending(self):
        case, response, proof = sample(); case['kind'] = 'prose'
        self.assertTrue(c.score(case, response, proof, quality=False)['manual_review_pending'])

    def test_unmatched_native_count_fault(self):
        case, response, proof = sample(); proof['native']['generated'] = 6
        with self.assertRaises(ValueError): c.score(case, response, proof, quality=False)

    def test_required_prose_ending(self):
        case, response, proof = sample(); case.update(kind='prose', expected_last_sentence='Required end.')
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)


class TokenTests(unittest.TestCase):
    def check(self, rows, n=2):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'tokens'; p.write_text(''.join(json.dumps(x) + '\n' for x in rows))
            return c.token_contract(p, n)

    def test_complete_source_ids(self):
        out = self.check([{'token': 0, 'seconds': .1}, {'token': 129279, 'seconds': .1}])
        self.assertEqual(out['count'], 2); self.assertEqual(len(out['ordered_ids_sha256']), 64)

    def test_invalid_vocabulary(self):
        with self.assertRaises(ValueError): self.check([{'token': 129280, 'seconds': .1}], 1)

    def test_bool_token(self):
        with self.assertRaises(ValueError): self.check([{'token': True, 'seconds': .1}], 1)

    def test_clock_regression(self):
        with self.assertRaises(ValueError): self.check([{'token': 1, 'seconds': 2}, {'token': 2, 'seconds': 1}])

    def test_nonfinite_clock(self):
        with self.assertRaises(ValueError): self.check([{'token': 1, 'seconds': float('inf')}], 1)

    def test_missing_row(self):
        with self.assertRaises(ValueError): self.check([{'token': 1, 'seconds': 1}], 2)


class FenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.group = self.root / 'user.slice/strata-deepseek-window.service'
        self.group.mkdir(parents=True); self.proc = self.root / 'proc-cgroup'
        self.proc.write_text('0::/user.slice/strata-deepseek-window.service\n')
        self.output = self.root / 'output'; self.output.mkdir()
        self.transient = self.root / 'transient'; self.transient.mkdir()
        self.fragment = self.transient / c.UNIT; self.fragment.write_text('owned')
        self.unit = {'InvocationID': 'a' * 32, 'Transient': 'yes',
                     'ControlGroup': '/user.slice/strata-deepseek-window.service',
                     'MemoryMax': 'infinity', 'MemorySwapMax': 'infinity',
                     'FragmentPath': str(self.fragment), 'DropInPaths': '', 'LoadState': 'loaded'}
        for name, value in {'memory.max': 'max', 'memory.swap.max': 'max', 'memory.current': '1024',
                            'memory.events': 'low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\n'}.items():
            (self.group / name).write_text(value)
        self.commands = []; self.write_readback = True; self.partial_failure = False

    def command(self, argv, **kwargs):
        self.commands.append(argv)
        if 'show' in argv:
            return types.SimpleNamespace(returncode=0, stdout=''.join(k + '=' + self.unit[k] + '\n' for k in c.FENCE_FIELDS))
        self.assertEqual(argv[:5], ['systemctl', '--user', 'set-property', '--runtime', c.UNIT])
        for arg in argv[5:]:
            key, value = arg.split('=', 1); self.unit[key] = value
            if self.write_readback:
                filename = 'memory.max' if key == 'MemoryMax' else 'memory.swap.max'
                (self.group / filename).write_text(c.limit_value(value))
            if self.partial_failure:
                self.partial_failure = False; raise RuntimeError('partial set-property failure')
        return types.SimpleNamespace(returncode=0, stdout='')

    def install(self):
        with patch.object(r, 'memory_available', return_value=r.HOST_MARGIN):
            return c.install_private_fence(self.output, command=self.command, proc=self.proc,
                                          root=self.root, transient_root=self.transient)

    def writes(self): return [x for x in self.commands if 'set-property' in x]

    def test_exact_invocation_property_install_restore(self):
        fence = self.install()
        self.assertEqual(fence['prior_properties'], {'MemoryMax': 'max', 'MemorySwapMax': 'max'})
        self.assertTrue(c.fence_terminal(fence)['passed'])
        value = c.restore_private_fence(fence, children_closed=True, command=self.command)
        self.assertTrue(value['passed']); self.assertEqual(value['restored_properties'], fence['prior_properties'])
        self.assertEqual((self.group / 'memory.max').read_text(), 'max')
        self.assertEqual(len(self.writes()), 2)
        self.assertNotIn('revert', str(self.commands))

    def test_finite_prior_properties_and_zero_swap_restored(self):
        self.unit.update(MemoryMax=str(r.MEMORY_MAX + 1024), MemorySwapMax='0')
        (self.group / 'memory.max').write_text(self.unit['MemoryMax']); (self.group / 'memory.swap.max').write_text('0')
        fence = self.install(); c.restore_private_fence(fence, children_closed=True, command=self.command)
        self.assertEqual((self.group / 'memory.max').read_text(), str(r.MEMORY_MAX + 1024))
        self.assertEqual((self.group / 'memory.swap.max').read_text(), '0')

    def test_infinity_normalized(self):
        self.assertEqual([c.limit_value(x) for x in ('infinity', 'max', str(2**64 - 1))], ['max'] * 3)

    def test_boolean_property_rejected(self):
        with self.assertRaises(ValueError): c.limit_value(True)

    def test_production_cgroup_no_commands(self):
        self.proc.write_text('0::/user.slice/deepseek-hosted.service\n')
        with self.assertRaises(ValueError): self.install()
        self.assertEqual(self.commands, [])

    def test_nontransient_no_mutation(self):
        self.unit['Transient'] = 'no'
        with self.assertRaises(ValueError): self.install()
        self.assertEqual(self.writes(), [])

    def test_foreign_fragment_no_mutation(self):
        self.unit['FragmentPath'] = '/etc/systemd/user/other.service'
        with self.assertRaises(ValueError): self.install()
        self.assertEqual(self.writes(), [])

    def test_stricter_prior_limit_never_relaxed(self):
        self.unit['MemoryMax'] = '1024'; (self.group / 'memory.max').write_text('1024')
        with self.assertRaises(ValueError): self.install()
        self.assertEqual(self.writes(), [])

    def test_prior_cgroup_disagreement_no_write(self):
        (self.group / 'memory.swap.max').write_text('1234')
        with self.assertRaises(ValueError): self.install()
        self.assertEqual(self.writes(), [])

    def test_partial_set_failure_restores_prior_properties(self):
        self.partial_failure = True
        with self.assertRaisesRegex(RuntimeError, 'partial set-property'): self.install()
        record = json.loads((self.output / 'private-memory-fence-restored.json').read_text())
        self.assertTrue(record['passed']); self.assertEqual(c.memory_properties(self.unit), {'MemoryMax': 'max', 'MemorySwapMax': 'max'})

    def test_readback_fault_preserves_first_and_restores(self):
        self.write_readback = False
        with self.assertRaisesRegex(ValueError, 'readback'): self.install()
        self.assertTrue(json.loads((self.output / 'private-memory-fence-restored.json').read_text())['passed'])

    def test_margin_missing_restores_prior(self):
        with patch.object(r, 'memory_available', return_value=0):
            with self.assertRaises(ValueError):
                c.install_private_fence(self.output, command=self.command, proc=self.proc,
                                        root=self.root, transient_root=self.transient)
        self.assertTrue(json.loads((self.output / 'private-memory-fence-restored.json').read_text())['passed'])

    def test_live_child_prevents_relaxation(self):
        fence = self.install(); before = len(self.writes())
        with self.assertRaises(ValueError): c.restore_private_fence(fence, children_closed=False, command=self.command)
        self.assertEqual(len(self.writes()), before)
        self.assertFalse(json.loads((self.output / 'private-memory-fence-restored.json').read_text())['passed'])

    def test_foreign_invocation_never_written(self):
        fence = self.install(); before = len(self.writes()); self.unit['InvocationID'] = 'b' * 32
        with self.assertRaises(ValueError): c.restore_private_fence(fence, children_closed=True, command=self.command)
        self.assertEqual(len(self.writes()), before)

    def test_foreign_property_never_overwritten(self):
        fence = self.install(); before = len(self.writes()); self.unit['MemorySwapMax'] = '77'
        with self.assertRaises(ValueError): c.restore_private_fence(fence, children_closed=True, command=self.command)
        self.assertEqual(len(self.writes()), before)

    def test_collection_requires_unit_gone_and_files_absent(self):
        self.install(); self.unit.update(InvocationID='', LoadState='not-found'); self.fragment.unlink()
        out = c.fence_collected(self.output, self.root, command=self.command)
        self.assertTrue(out['unit_collected']); self.assertTrue(out['dropins_absent'])

    def test_surviving_dropin_blocks_collection(self):
        self.install(); self.unit.update(InvocationID='', LoadState='not-found'); self.fragment.unlink()
        Path(str(self.fragment) + '.d').mkdir()
        with self.assertRaises(ValueError): c.fence_collected(self.output, self.root, command=self.command)

    def test_new_invocation_blocks_collection(self):
        self.install(); self.unit['InvocationID'] = 'b' * 32
        with self.assertRaises(ValueError): c.fence_collected(self.output, self.root, command=self.command)

    def test_collection_timeout_no_write(self):
        self.install(); clock = Mock(side_effect=[0, 31])
        with self.assertRaisesRegex(RuntimeError, 'collection'):
            c.fence_collected(self.output, self.root, command=self.command, clock=clock, pause=Mock())
        self.assertFalse((self.root / 'private-memory-fence-collected.json').exists())

    def test_missing_start_receipt_does_not_hide_live_API(self):
        handle = types.SimpleNamespace(poll=lambda: None); command = Mock()
        self.assertFalse(c.private_children_closed(self.output, [handle], command=command))
        command.assert_not_called()

    def test_dead_API_without_ready_requires_GPU_empty(self):
        handle = types.SimpleNamespace(poll=lambda: 1)
        command = Mock(return_value=types.SimpleNamespace(stdout='1234\n'))
        self.assertFalse(c.private_children_closed(self.output, [handle], command=command))

    def test_prelaunch_empty_GPU_allows_original_limit_restore(self):
        command = Mock(return_value=types.SimpleNamespace(stdout=''))
        self.assertTrue(c.private_children_closed(self.output, [], command=command))

    def test_ready_native_still_present_blocks(self):
        (self.output / 'native-ready.json').write_text('{"pid": 91}')
        (self.root / '91').mkdir(); command = Mock()
        self.assertFalse(c.private_children_closed(self.output, [], command=command, proc=self.root))
        command.assert_not_called()

    def test_GPU_query_error_not_empty(self):
        command = Mock(side_effect=RuntimeError('query failed'))
        with self.assertRaises(RuntimeError): c.private_children_closed(self.output, [], command=command)

    def test_fenced_body_error_retains_primary_and_cleanup_note(self):
        with patch.object(c, 'install_private_fence', return_value={}), patch.object(c, 'private_children_closed', return_value=False), \
             patch.object(c, 'restore_private_fence', side_effect=RuntimeError('cleanup failed')):
            error = RuntimeError('body first')
            with self.assertRaisesRegex(RuntimeError, 'body first'):
                with c.fenced_phase(self.output): raise error
        self.assertIn('cleanup failed', str(error.__notes__))

    def test_fenced_cleanup_error_fails_successful_body(self):
        with patch.object(c, 'install_private_fence', return_value={}), patch.object(c, 'private_children_closed', return_value=False), \
             patch.object(c, 'restore_private_fence', side_effect=RuntimeError('unsafe children')):
            with self.assertRaisesRegex(RuntimeError, 'unsafe children'):
                with c.fenced_phase(self.output): pass

    def test_restore_receipt_failure_does_not_mask_primary(self):
        fence=self.install();self.unit['InvocationID']='b'*32
        with patch.object(r,'emit',side_effect=OSError('receipt failed')):
            with self.assertRaisesRegex(ValueError,'Foreign private invocation') as caught:
                c.restore_private_fence(fence,children_closed=True,command=self.command)
        self.assertIn('receipt failed',str(caught.exception.__notes__))

    def test_collection_query_uses_remaining_deadline(self):
        self.install();self.unit.update(InvocationID='',LoadState='not-found');self.fragment.unlink()
        command=Mock(side_effect=self.command)
        c.fence_collected(self.output,self.root,command=command,clock=Mock(side_effect=[0,25,26]))
        self.assertEqual(command.call_args.kwargs['timeout'],5)

    def test_memory_events_oom_blocks(self):
        before = {'cgroup': str(self.group), 'events_before': c.memory_events(self.group)}
        (self.group / 'memory.events').write_text('low 0\nhigh 0\nmax 0\noom 1\noom_kill 0\n')
        with self.assertRaises(ValueError): c.fence_terminal(before)

    def test_event_regression(self):
        with self.assertRaises(ValueError): c.fence_terminal({'cgroup': str(self.group), 'events_before': {'oom': 1, 'oom_kill': 0}})

    def test_path_traversal(self):
        with self.assertRaises(ValueError): c.private_cgroup('0::/x/../strata-deepseek-window.service', self.root)

    def test_memory_counter_malformed(self):
        (self.group / 'memory.events').write_text('oom -1\noom_kill 0\n')
        with self.assertRaises(ValueError): c.memory_events(self.group)


class PlacementTests(unittest.TestCase):
    def log(self, cut=19):
        return ('ds4: CUDA0 layers [0, 42]: weights 3.31 GB, experts 58.32 GB (5746 of 7680 in VRAM), caches 0.58 GB, 2026 MiB free\n'
                'ds4: CUDA1 layers [%d, 39] + head: weights 3.31 GB, experts 58.86 GB (5953 of 8064 in VRAM), caches 0.54 GB, 2030 MiB free' % cut)

    def test_baseline_automatic_observed(self):
        self.assertEqual(c.placement(self.log(), [19, 20])['trunk_split'], [19, 21])

    def test_alternate_frozen_automatic_split(self):
        self.assertEqual(c.placement(self.log(20), [19, 20])['trunk_split'], [20, 20])

    def test_unreviewed_split_rejected(self):
        with self.assertRaises(ValueError): c.placement(self.log(21), [19, 20])

    def test_missing_GPU_rejected(self):
        with self.assertRaises(ValueError): c.placement(self.log().splitlines()[0], [19])

    def test_head_wrong_device(self):
        with self.assertRaises(ValueError): c.placement(self.log().replace(' + head:', ':'), [19])

    def test_unknown_format_rejected(self):
        with self.assertRaises(ValueError): c.placement(self.log().replace('MiB free', 'MB free'), [19])


class RequestTests(unittest.TestCase):
    def perform(self, *, deadline=100, immediate=True, dump='OK', storage='OK', margin=True,
                result_error=None, advance=0):
        clock = types.SimpleNamespace(value=0.)
        objects = []
        class FakeStream:
            def __init__(self, base, body, timeout):
                self.base, self.body, self.timeout = base, body, timeout
                self.cancel = Mock(); self.thread = types.SimpleNamespace(is_alive=lambda: False)
                self.finished = types.SimpleNamespace(wait=self.wait); objects.append(self)
            def start(self): return self
            def wait(self, timeout): clock.value += advance; return immediate
            def result(self, timeout):
                if result_error: raise result_error
                return {'status': 200, 'done': True, 'finish_reason': 'stop', 'content': 'ok'}
        def wait_for(fn, timeout, why):
            if not fn(): raise RuntimeError(why)
        with patch.object(r, 'memory_available', return_value=r.HOST_MARGIN if margin else 0):
            out = c.bounded_request('http://127.0.0.1:18041', {'max_tokens': 32768}, deadline, Path('/unused'), True,
                    stream_class=FakeStream, observe=lambda *a: {'work': {'active': 0, 'queued': 0, 'admission_reserved': 0}},
                    wait_for=wait_for, dump_snapshot=lambda *a: {'status': dump},
                    storage_snapshot=lambda *a: {'status': storage}, clock=lambda: clock.value)
        return out, objects

    def test_no_budget_no_request(self):
        out, objects = self.perform(deadline=9); self.assertTrue(out['budget_not_started']); self.assertFalse(objects)

    def test_complete_without_retry(self):
        out, objects = self.perform(); self.assertTrue(out['done']); self.assertEqual(len(objects), 1)
        self.assertEqual(objects[0].timeout, 1200); objects[0].cancel.assert_not_called()

    def test_deadline_owned_cancel(self):
        out, objects = self.perform(deadline=11, immediate=False, advance=12)
        self.assertEqual(out['incomplete_reason'], 'UNCHANGED_SOFT_DEADLINE'); objects[0].cancel.assert_called_once()

    def test_dump_limit_owned_cancel(self):
        out, objects = self.perform(immediate=False, dump='INCOMPLETE_HOLD')
        self.assertEqual(out['incomplete_reason'], 'FINITE_DUMP_LIMIT'); objects[0].cancel.assert_called_once()

    def test_storage_limit_owned_cancel(self):
        out, objects = self.perform(immediate=False, storage='INCOMPLETE_HOLD')
        self.assertEqual(out['incomplete_reason'], 'PRIVATE_STORAGE_LIMIT'); objects[0].cancel.assert_called_once()

    def test_physical_margin_owned_cancel(self):
        out, objects = self.perform(immediate=False, margin=False)
        self.assertEqual(out['incomplete_reason'], 'PHYSICAL_HOST_MARGIN'); objects[0].cancel.assert_called_once()

    def test_terminal_storage_partial_not_passed(self):
        out, objects = self.perform(storage='INCOMPLETE_HOLD')
        self.assertTrue(out['intentional_budget_stop']); self.assertFalse(out['retry']); self.assertEqual(len(objects), 1)

    def test_transport_fault_raw_preserved(self):
        error = RuntimeError('transport')
        with self.assertRaisesRegex(RuntimeError, 'transport'): self.perform(result_error=error)
        self.assertIsInstance(error.raw_transport, dict)


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.f=r.original_module('ms_fixtures')
        self.m=json.loads(r.encoded_path('prose','B').read_text());self.calls=[];self.saved=[]

    def natural(self,case,*args):
        self.calls.append((case['id'],args[-1],copy.deepcopy(case['request'])))
        response={'status':200,'done':True,'finish_reason':'stop','cancelled':False,'reasoning':'synthetic'}
        if case['kind']=='tool':response.update(self.f.synthetic_call('actual-provider-731'));response['content']=''
        elif case['kind']=='prose':response['content']='Synthetic prose. '+case['expected_last_sentence']
        elif case['kind']=='code':response['content']='def coalesce_ranges(ranges):\n    return []\n'
        elif case['kind']=='literal':response['content']=case['expected']
        else:response['content']=json.dumps(case['expected'])
        n={'generated':7,'prompt_tokens':case['prompt_tokens'],'finish':'stop',
           'reused':case['prompt_tokens']-1 if case.get('expected_reuse')=='prompt-minus-one' else 0,
           'drafts_offered':4,'drafts_accepted':3,'prompt_ms':1.,'decode_ms':2.}
        return response,{'native':n,'observed_tokens':7,'client_full_s':.03,'emitted_token_contract':{'count':7}}

    def cancelled(self,case,*args):
        self.calls.append((case['id'],args[-1],copy.deepcopy(case['request'])))
        result={'passed':True,'classification':'confirmed_prefill_cancel','replay':False,'recovery_required':True,
                'client_disconnect_cancels_delta':1,'observed_before_cancel':{'state':'reading','read':4096,
                    'total':case['prompt_tokens'],'first_delta':False},
                'transport':{'cancelled':True,'content':'','reasoning':'','tool_calls':[]}}
        return result,{'native':{'generated':0,'finish':'cancel'},'observed_tokens':0,'cancelled_control_or_budget':True}

    def run_panel(self,arm='B1',issue=None,cancel=None):
        return c.run_panel(self.m,'prose',arm,Path('/synthetic'),71,1000,
            issue=issue or self.natural,cancel=cancel or self.cancelled,fixtures=self.f,
            save_progress=lambda value:self.saved.append(copy.deepcopy(value)))

    def test_nine_cases_order_same_clock_call_ID_and_separate_rates(self):
        result=self.run_panel();self.assertTrue(result['complete']);self.assertFalse(result['performance_accepted'])
        self.assertEqual([x[0] for x in self.calls],[c['id'] for c in self.m['cases']+self.m['lifecycle_cases']])
        self.assertEqual({x[1] for x in self.calls},{1000});self.assertEqual(len(result['rows']),5)
        self.assertEqual(len(result['lifecycle']['rows']),4)
        self.assertEqual(result['lifecycle']['scores'][2]['status'],'CONFIRMED_PREFILL_CANCEL_PASSED')
        actual=self.calls[6][2];self.assertEqual(actual['messages'][-1]['tool_call_id'],'actual-provider-731')
        self.assertEqual(actual['messages'][-2]['tool_calls'][0]['id'],'actual-provider-731')
        self.assertNotEqual(actual,self.m['lifecycle_cases'][1]['request'])

    def test_no_reversed_policy_arms(self):
        for arm in ('B2','A2'):
            with self.assertRaises(ValueError):self.run_panel(arm)
        self.assertEqual(self.calls,[])

    def test_no_coding_family_admitted(self):
        with self.assertRaises(ValueError):
            c.run_panel(self.m,'coding','A1',Path('/synthetic'),71,1000,issue=self.natural,
                        cancel=self.cancelled,fixtures=self.f)
        self.assertEqual(self.calls,[])

    def test_wrong_tool_blocks_followup_cancel_recovery(self):
        def issue(case,*args):
            response,proof=self.natural(case,*args)
            if case['kind']=='tool':response['tool_calls'][0]['function']['arguments']='{"sku":"wrong","quantity":6}'
            return response,proof
        result=self.run_panel(issue=issue);self.assertFalse(result['complete']);self.assertEqual(len(self.calls),6)
        self.assertEqual(len(result['unrun_ids']),3)

    def test_each_budget_stop_preserves_remaining_without_retry(self):
        for stop in range(9):
            self.calls=[];counter=[0]
            def issued(case,*args):
                i=counter[0];counter[0]+=1
                if i==stop:raise c.Incomplete('same soft deadline')
                return (self.cancelled if case['kind']=='prefill-cancel' else self.natural)(case,*args)
            result=self.run_panel(issue=issued,cancel=issued)
            self.assertFalse(result['complete']);self.assertEqual(counter[0],stop+1)
            self.assertEqual(len(result['unrun_ids']),8-stop)

    def test_execution_fault_preserves_scores_no_following_calls(self):
        with self.assertRaisesRegex(RuntimeError,'fault'):
            self.run_panel(issue=Mock(side_effect=RuntimeError('fault')))
        self.assertEqual(self.saved[-1]['scores'][0]['status'],'EXECUTION_FAULT_HOLD')
        self.assertFalse(self.saved[-1]['complete'])

    def test_no_draft_main_blocks_before_lifecycle(self):
        def issue(case,*args):
            response,proof=self.natural(case,*args);proof['native']['drafts_accepted']=0;return response,proof
        result=self.run_panel(issue=issue);self.assertFalse(result['complete']);self.assertEqual(len(self.calls),1)

    def test_cancel_decode_token_not_accepted_as_prefill(self):
        case=self.m['lifecycle_cases'][2];result,proof=self.cancelled(case,1000);proof['native']['generated']=1
        with self.assertRaises(ValueError):c.cancel_score(case,result,proof)

    def test_cancel_reading_counters_release_and_visible_output_guards(self):
        case=self.m['lifecycle_cases'][2]
        for key,value in [('passed',False),('classification','not_exercised'),('cleanup_error','busy'),
                          ('client_disconnect_cancels_delta',True),('client_disconnect_cancels_delta',0),('replay',True)]:
            result,proof=self.cancelled(case,1000);result[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):c.cancel_score(case,result,proof)
        for key,value in [('read',0),('total',1),('first_delta',True),('state','decoding')]:
            result,proof=self.cancelled(case,1000);result['observed_before_cancel'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):c.cancel_score(case,result,proof)
        result,proof=self.cancelled(case,1000);result['transport']['content']='one token'
        with self.assertRaises(ValueError):c.cancel_score(case,result,proof)

    def test_followup_only_actualID_may_change(self):
        case=self.m['lifecycle_cases'][1];response=self.f.synthetic_call('provider-x')
        self.assertEqual(c.followup_case(case,response,self.f)['prompt_ids'],case['prompt_ids'])
        bad=copy.deepcopy(case);bad['request']['messages'][-1]['content']='foreign result'
        with self.assertRaises(ValueError):c.followup_case(bad,response,self.f)

    def test_recovery_literal_wrong_blocks_complete(self):
        def issue(case,*args):
            response,proof=self.natural(case,*args)
            if case['kind']=='literal':response['content']='WRONG'
            return response,proof
        result=self.run_panel(issue=issue);self.assertFalse(result['complete']);self.assertEqual(len(self.calls),9)


if __name__=='__main__':unittest.main()
