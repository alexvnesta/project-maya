"""Exact b1 API with CPU MockEngine and new four-state requests. No native/GPU."""
import copy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

import ms_controls as controls
import ms_fixtures as fixtures
import ms_runtime as runtime


class ActualAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.support=fixtures.load_support();cls.api=cls.support.server;cls.tok=cls.support.tokenizer()
        path=fixtures.E/'prefill-v2/protocol.py';sys.path.insert(0,str(path.parent))
        cls.protocol=importlib.import_module('protocol')
        if Path(cls.protocol.__file__)!=path:raise ValueError('Foreign private transport')

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.manifest=json.loads((Path(__file__).parent/'quality-fixtures-A.json').read_text())
        fixtures.validate_encoded(self.manifest['cases'],'quality')
        owner=self;api=self.api;tok=self.tok;self.seen=[];self.cancel_seen=threading.Event()
        self.entered=threading.Event();self.release=threading.Event()
        class Engine(api.MockEngine):
            def __init__(inner):
                answers=['</think>\n\n'+json.dumps(c['expected']) for c in owner.manifest['cases']]
                super().__init__(tok,answers,max_context=1048576)
                inner.scripts=[tok.encode(answer)+[1] for answer in answers];inner.script=inner.scripts[0]
                inner.proc=types.SimpleNamespace(pid=321);inner.info={};inner.can_stop=True
                inner.batch=0;inner.last={};inner.block_next=False
            def _parse_done(inner,line):return api.StrataEngine._parse_done(inner,line)
            def generate(inner,ids,max_new,sampling,cancel,embeddings=None):
                owner.seen.append({'ids':list(ids),'max_new':max_new,'images':bool(embeddings),'sampling':sampling})
                block=inner.block_next;inner.block_next=False;count=0
                try:
                    if block:
                        owner.entered.set();end=time.monotonic()+10
                        while not owner.release.is_set() and not cancel.is_set():
                            if time.monotonic()>=end:raise AssertionError('Synthetic prefill never released')
                            yield None;time.sleep(.005)
                        if cancel.is_set():return
                    for token in super().generate(ids,max_new,sampling,cancel,embeddings):
                        count+=1;yield token
                finally:
                    if cancel.is_set():owner.cancel_seen.set()
                    finish='cancel' if cancel.is_set() else 'stop'
                    inner._parse_done(f'DONE {count} {len(ids)} 1.0 2.0 {finish} 3 5 0 0 0')
        self.engine=Engine()
        self.vision=self.support.ds4_vision.Vision(self.support.ds4_vision.Geometry(),Path(self.tmp.name),api.Vision.load)
        self.svc=api.Service(self.engine,self.tok,api.ChatTemplate(self.support.dsml.pick_template(fixtures.V/'tokenizer/chat_template.jinja')[0]),
                             model_name=fixtures.POLICY['model'],vision=self.vision,fit_max_tokens=False)
        self.svc.set_family('deepseek41');self.svc.answer_room=False;self.svc.reasoning_budget_configured=True
        self.svc.reasoning_budget_tokens=0;self.svc.reasoning_loop_recovery=False;self.svc.repeat_stop_tokens=0
        self.http=api.serve(self.svc,'127.0.0.1',0);self.thread=threading.Thread(target=self.http.serve_forever,daemon=True)
        self.thread.start();self.base='http://127.0.0.1:'+str(self.http.server_port);self.streams=[]

    def tearDown(self):
        self.release.set()
        for stream in self.streams:
            if stream.thread.is_alive():stream.cancel()
        self.http.shutdown();self.http.server_close();self.thread.join(2);self.vision.shutdown()

    def wait_idle(self):
        self.protocol.wait_for(lambda:not any(self.protocol.json_get(self.base,'/v1/telemetry')['work'][k]
                               for k in ('active','queued','admission_reserved')),5,'CPU mock API retained admission')

    def test_new_four_state_requests_through_actual_API_and_transport(self):
        for i,case in enumerate(self.manifest['cases']):
            with patch.object(runtime,'memory_available',return_value=runtime.HOST_MARGIN):
                response=controls.bounded_request(self.base,case['request'],time.monotonic()+20,Path(self.tmp.name),True,
                    stream_class=self.protocol.Stream,observe=self.protocol.json_get,wait_for=self.protocol.wait_for,
                    dump_snapshot=lambda *args:{'status':'WITHIN_BUDGET'},storage_snapshot=lambda *args:{'status':'WITHIN_BUDGET'})
            self.wait_idle()
            self.assertEqual(json.loads(response['content']),case['expected']);self.assertTrue(response['done'])
            self.assertEqual(response['finish_reason'],'stop');self.assertEqual(self.seen[i]['ids'],case['prompt_ids'])
            self.assertEqual(self.seen[i]['max_new'],32768);self.assertEqual(self.seen[i]['images'],i==2)
            self.assertEqual(response['usage']['prompt_tokens'],case['prompt_tokens'])
            self.assertEqual(response['timings']['draft_n'],5)
        self.assertEqual(len(self.seen),4);self.assertNotIn('torch',sys.modules)

    def test_actual_prefill_cancel_before_first_delta_releases_then_recovers(self):
        self.engine.block_next=True
        own=self.protocol.Stream(self.base,self.manifest['cases'][0]['request']).start();self.streams.append(own)
        self.assertTrue(self.entered.wait(3));self.assertFalse(own.first_delta.is_set())
        own.cancel();self.wait_idle();self.assertTrue(self.cancel_seen.is_set())
        self.assertEqual(own.result(1)['content'],'');self.assertFalse(own.result(1)['done'])
        # The cancelled scripted turn never advances; recovery uses the same full
        # cap and unchanged request, without attempting any model or native retry.
        recovery=self.protocol.Stream(self.base,self.manifest['cases'][0]['request']).start();self.streams.append(recovery)
        result=recovery.result(5);self.wait_idle()
        self.assertEqual(json.loads(result['content']),self.manifest['cases'][0]['expected'])
        self.assertTrue(result['done']);self.assertEqual(len(self.seen),2)
        self.assertEqual([s['max_new'] for s in self.seen],[32768,32768]);self.assertNotIn('torch',sys.modules)


if __name__=='__main__':unittest.main()
