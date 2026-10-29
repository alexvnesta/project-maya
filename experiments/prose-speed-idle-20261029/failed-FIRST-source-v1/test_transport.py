"""CPU-only parser and real loopback socket tests. No production endpoint used."""
import copy
import http.server
import json
import socket
import threading
import time
import unittest
from unittest import mock

import transport as t


def event(content='', *, finish=None, **kwargs):
    value = {'id': 'chat-own', 'model': 'selected', 'choices': [
        {'index': 0, 'delta': {'content': content}, 'finish_reason': finish}]}
    value.update(kwargs)
    return b'data: ' + json.dumps(value).encode() + b'\n'


def completed():
    return [event('READ'), event('Y', finish='stop'), b'data: [DONE]\n', b'\n']


class ParserTests(unittest.TestCase):
    def test_fragmented_ready_and_comment(self):
        p = t.Parser()
        for line in [b': heartbeat\n', *completed()]:
            p.feed(line, .1)
        row = p.result(.5)
        self.assertEqual(row['content'], 'READY')
        self.assertFalse(row['first_visible_is_TTFT'])

    def test_missing_done_length_and_tool_finish_refused(self):
        for finish, done in [('stop', False), ('length', True), ('tool_calls', True)]:
            with self.subTest(finish=finish):
                p = t.Parser(); p.feed(event('x', finish=finish), 0)
                if done: p.feed(b'data: [DONE]\n', 0)
                with self.assertRaises(t.TransportError): p.result(1)

    def test_premature_duplicate_done_and_text_after_finish(self):
        sequences = [[b'data: [DONE]\n'], [*completed(), b'data: [DONE]\n'],
                     [event('x', finish='stop'), event('again')]]
        for sequence in sequences:
            with self.subTest(sequence=sequence):
                with self.assertRaises(t.TransportError):
                    p = t.Parser()
                    for row in sequence: p.feed(row, 0)

    def test_mixed_identity_choice_role_and_server_errors(self):
        for change in ({'id': 'foreign'}, {'model': 'other'}, {'error': {'message': 'fail'}},
                       {'choices': [{'index': True, 'delta': {}}]}, {'choices': [{} , {}]},
                       {'choices': [{'index': 0, 'delta': {'role': 'user'}}]},
                       {'choices': [{'index': 0, 'delta': {'tool_calls': [{}]}}]}):
            with self.subTest(change=change):
                p = t.Parser(); p.feed(event('x'), 0)
                with self.assertRaises(t.TransportError): p.feed(event(**change), 0)

    def test_malformed_utf8_json_and_oversize(self):
        for line in (b'\xff\n', b'data: {bad\n', b'wrongfield\n', b'x' * (t.MAX_LINE + 1)):
            with self.subTest(line=line[:30]):
                with self.assertRaises((ValueError, t.TransportError, UnicodeError)):
                    t.Parser().feed(line, 0)
        with mock.patch.object(t, 'MAX_RESPONSE', 1):
            with self.assertRaises(t.TransportError): t.Parser().feed(event('x'), 0)

    def test_observation_endpoint_allowlist_before_connection(self):
        factory = mock.Mock()
        for port, path in [(18141, '/api/requests'), (18141, '/stop'), (80, '/health'), (8012, '/settings')]:
            with self.assertRaises(t.TransportError): t.get_json(port, path, connection=factory)
        factory.assert_not_called()


class SocketTests(unittest.TestCase):
    def setUp(self):
        self.entered = threading.Event()
        self.disconnected = threading.Event()
        self.user_done = threading.Event()
        owner = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if request.get('wait'):
                    owner.entered.set()
                    self.connection.settimeout(3)
                    try:
                        if self.connection.recv(1) == b'': owner.disconnected.set()
                    except OSError:
                        owner.disconnected.set()
                    return
                self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
                for row in completed(): self.wfile.write(row)
                self.wfile.flush()
                if request.get('user'): owner.user_done.set()
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addresses = []
        def connect(address, timeout):
            self.addresses.append(address)
            return socket.create_connection(self.server.server_address, timeout=timeout)
        self.connect = connect

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(3)

    def test_real_loopback_natural_response_fixed_production_address(self):
        stream = t.Stream({'stream': True}, connect=self.connect).start()
        self.assertTrue(stream.finished.wait(3))
        self.assertEqual(stream.result()['content'], 'READY')
        self.assertEqual(self.addresses, [('127.0.0.1', 18141)])
        with self.assertRaises(t.TransportError): stream.start()

    def test_cancel_owned_queued_socket_only_user_and_recovery_complete(self):
        own = t.Stream({'stream': True, 'wait': True}, connect=self.connect).start()
        self.assertTrue(self.entered.wait(3))
        user = t.Stream({'stream': True, 'user': True}, connect=self.connect).start()
        own.cancel()
        self.assertTrue(self.disconnected.wait(3))
        self.assertTrue(user.finished.wait(3)); self.assertTrue(self.user_done.is_set())
        self.assertEqual(user.result()['content'], 'READY')
        self.assertTrue(own.partial()['cancelled'])
        recovery = t.Stream({'stream': True}, connect=self.connect).start()
        self.assertTrue(recovery.finished.wait(3)); self.assertEqual(recovery.result()['content'], 'READY')

    def test_cancel_before_connect_returns_never_sends(self):
        release = threading.Event()
        def delayed(address, timeout):
            release.wait(1)
            return self.connect(address, timeout)
        stream = t.Stream({'stream': True}, connect=delayed)
        stream.cancel(); release.set(); stream.start()
        self.assertTrue(stream.finished.wait(3)); self.assertFalse(stream.sent.is_set())


class ActualSelectedAPITests(unittest.TestCase):
    def test_actual_fullcap_API_natural_cancel_user_queue_and_recovery(self):
        # Real selected b1 API/template/watcher; only the token engine is scripted.
        import importlib
        from pathlib import Path
        import sys
        import tempfile
        from types import SimpleNamespace
        E = Path(__file__).resolve().parents[2]
        helper = E / 'decode-optimization-20261028/model-v1'
        sys.path.insert(0, str(helper))
        f = importlib.import_module('imma_fixtures')
        self.assertEqual(Path(f.__file__).resolve(), helper / 'imma_fixtures.py')
        support = f.load_support(); api = support.server; tok = support.tokenizer()
        seen = []
        class Engine(api.MockEngine):
            def __init__(inner):
                super().__init__(tok, ['</think>\n\nREADY'], max_context=1048576)
                inner.scripts = [tok.encode('</think>\n\nREADY') + [1]] * 8
                inner.script = inner.scripts[0]
                inner.proc = SimpleNamespace(pid=321)
                inner.info = {}; inner.can_stop = True; inner.batch = 0; inner.last = {}
                inner.block_next = False; inner.entered = threading.Event(); inner.gate = threading.Event()
                inner.cancel_seen = threading.Event()
            def _parse_done(inner, line): return api.StrataEngine._parse_done(inner, line)
            def generate(inner, ids, max_new, sampling, cancel, embeddings=None):
                seen.append((max_new, bool(embeddings)))
                blocking = inner.block_next; inner.block_next = False; count = 0
                try:
                    if blocking:
                        inner.entered.set(); limit = time.monotonic() + 20
                        while not inner.gate.is_set() and not cancel.is_set():
                            if time.monotonic() >= limit: raise AssertionError('CPU scripted request never released')
                            yield None; time.sleep(.005)
                        if cancel.is_set():
                            inner.cancel_seen.set(); return
                    for token in super().generate(ids, max_new, sampling, cancel, embeddings):
                        count += 1; yield token
                finally:
                    finish = 'cancel' if cancel.is_set() else 'stop'
                    inner._parse_done(f'DONE {count} {len(ids)} 1.0 2.0 {finish} 3 5 0 0 0')
        with tempfile.TemporaryDirectory() as tmp:
            engine = Engine()
            vision = support.ds4_vision.Vision(support.ds4_vision.Geometry(), Path(tmp), api.Vision.load)
            svc = api.Service(engine, tok, api.ChatTemplate(support.dsml.pick_template(
                E / 'native-vision-v2/tokenizer/chat_template.jinja')[0]),
                model_name='deepseek-v4.1-flash-iq2-xs', vision=vision, fit_max_tokens=False)
            svc.set_family('deepseek41'); svc.answer_room = False; svc.reasoning_budget_configured = True
            svc.reasoning_budget_tokens = 0; svc.reasoning_loop_recovery = False; svc.repeat_stop_tokens = 0
            http = api.serve(svc, '127.0.0.1', 0)
            thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
            def connect(address, timeout):
                self.assertEqual(address, ('127.0.0.1', 18141))
                return socket.create_connection(('127.0.0.1', http.server_port), timeout)
            def work():
                conn = __import__('http.client', fromlist=['HTTPConnection']).HTTPConnection('127.0.0.1', http.server_port, timeout=2)
                try:
                    conn.request('GET', '/v1/telemetry'); response = conn.getresponse()
                    self.assertEqual(response.status, 200)
                    return json.loads(response.read())['work']
                finally: conn.close()
            def wait(predicate, timeout=5):
                until = time.monotonic() + timeout
                while time.monotonic() < until:
                    value = predicate()
                    if value: return value
                    time.sleep(.01)
                self.fail('Actual CPU API condition timed out')
            body = json.loads((Path(__file__).parent / 'prose-fixtures.json').read_text())['cases'][0]['request']
            streams = []
            def new():
                stream = t.Stream(body, connect=connect); streams.append(stream); return stream.start()
            try:
                natural = new(); self.assertTrue(natural.finished.wait(5))
                self.assertEqual(natural.result()['content'], 'READY')
                self.assertEqual(natural.result()['timings']['draft_n'], 5)
                wait(lambda: work()['admission_reserved'] == 0)
                engine.block_next = True; engine.entered.clear(); engine.gate.clear(); engine.cancel_seen.clear()
                before = work()['client_disconnect_cancels']
                own = new(); self.assertTrue(engine.entered.wait(3))
                self.assertIsNone(own.parser.first_visible)
                own.cancel(); wait(lambda: work()['admission_reserved'] == 0)
                self.assertTrue(engine.cancel_seen.is_set())
                self.assertEqual(work()['client_disconnect_cancels'], before + 1)
                # Existing user holds engine first. Cancel our queued socket only.
                engine.block_next = True; engine.entered.clear(); engine.gate.clear(); engine.cancel_seen.clear()
                user = new(); self.assertTrue(engine.entered.wait(3))
                queued = new(); wait(lambda: work()['queued'] == 1 and work()['admission_reserved'] == 2)
                queued.cancel()
                wait(lambda: work()['queued'] == 0 and work()['admission_reserved'] == 1, timeout=15)
                self.assertFalse(engine.cancel_seen.is_set()); self.assertFalse(user.cancelled.is_set())
                engine.gate.set(); self.assertTrue(user.finished.wait(5))
                self.assertEqual(user.result()['content'], 'READY')
                wait(lambda: work()['admission_reserved'] == 0)
                recovery = new(); self.assertTrue(recovery.finished.wait(5))
                self.assertEqual(recovery.result()['content'], 'READY')
                wait(lambda: work()['admission_reserved'] == 0)
                self.assertEqual(seen, [(32768, False)] * 4)  # queued cancelled request never entered engine
                self.assertNotIn('torch', sys.modules)
            finally:
                engine.gate.set()
                for stream in streams:
                    if not stream.finished.is_set(): stream.cancel()
                http.shutdown(); http.server_close(); thread.join(2); vision.shutdown()


if __name__ == '__main__':
    unittest.main()
