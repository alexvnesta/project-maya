"""Fixed hosted loopback transport. Only the socket created by Stream is cancellable.

The private protocol module is intentionally neither imported nor modified.
A constructor-injected connection factory is a CPU-test seam, not a CLI option.
"""
import http.client
import json
import math
import socket
import threading
import time

HOST = '127.0.0.1'
PORT = 18141
MAX_RESPONSE = 64 * 2**20
MAX_LINE = 2**20


class TransportError(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise TransportError(message)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def get_json(port, path, *, connection=http.client.HTTPConnection):
    require((port, path) in {(18141, '/v1/telemetry'), (18141, '/health'),
                            (18141, '/metrics'), (8012, '/health')}, 'Unexpected observation endpoint')
    conn = connection(HOST, port, timeout=.75)
    try:
        conn.request('GET', path, headers={'Accept': 'application/json', 'Connection': 'close'})
        response = conn.getresponse()
        require(response.status == 200, 'Observation unavailable')
        require(response.getheader('Content-Type', '').split(';')[0] == 'application/json', 'Not JSON')
        data = response.read(2**21 + 1)
        require(len(data) <= 2**21, 'Observation oversized')
        value = json.loads(data)
        require(type(value) is dict, 'Observation shape')
        return value
    finally:
        conn.close()


class Parser:
    """One chat completion. Preserve own synthetic SSE only; no shared history."""
    def __init__(self):
        self.raw = []
        self.content = self.reasoning = ''
        self.finish = None
        self.done = False
        self.identity = None
        self.usage = self.timings = None
        self.bytes = 0
        self.first_visible = None

    def feed(self, line, elapsed):
        require(type(line) is bytes and len(line) <= MAX_LINE, 'Invalid/oversized SSE line')
        self.bytes += len(line)
        require(self.bytes <= MAX_RESPONSE, 'Owned response budget exceeded')
        text = line.decode('utf-8')
        self.raw.append({'seconds': elapsed, 'line': text})
        if not text.startswith('data:'):
            require(not text.strip() or text.startswith(':'), 'Unexpected SSE field')
            return
        require(not self.done, 'Data after DONE')
        payload = text[5:].strip()
        if payload == '[DONE]':
            require(self.finish is not None, 'Premature DONE')
            self.done = True
            return
        event = json.loads(payload)
        require(type(event) is dict and 'error' not in event, 'SSE error')
        identity = (event.get('id'), event.get('model'))
        require(all(type(x) is str and x for x in identity), 'Missing completion identity')
        if self.identity is None:
            self.identity = identity
        require(identity == self.identity, 'Mixed completion identity')
        if event.get('usage') is not None:
            require(type(event['usage']) is dict, 'Usage shape')
            self.usage = event['usage']
        if event.get('timings') is not None:
            require(type(event['timings']) is dict, 'Timing shape')
            self.timings = event['timings']
        choices = event.get('choices')
        require(type(choices) is list and len(choices) <= 1, 'Multiple/malformed choices')
        for choice in choices:
            require(type(choice) is dict and type(choice.get('index')) is int and choice['index'] == 0,
                    'Choice identity')
            delta = choice.get('delta')
            require(type(delta) is dict and not delta.get('tool_calls'), 'Non-prose delta')
            require(delta.get('role') in (None, 'assistant'), 'Unexpected role')
            content, reason = delta.get('content'), delta.get('reasoning_content')
            require(content is None or type(content) is str, 'Nontext content delta')
            require(reason is None or type(reason) is str, 'Nontext reasoning delta')
            content, reason = content or '', reason or ''
            require(self.finish is None or not (content or reason), 'Text after finish')
            if content and self.first_visible is None:
                self.first_visible = elapsed
            self.content += content
            self.reasoning += reason
            finish = choice.get('finish_reason')
            if finish is not None:
                require(self.finish is None and finish in ('stop', 'length', 'tool_calls'), 'Duplicate/bad finish')
                self.finish = finish

    def result(self, elapsed):
        require(self.done and self.finish == 'stop' and self.content.strip(), 'Missing natural prose completion')
        return {'content': self.content, 'reasoning': self.reasoning, 'raw_sse': self.raw,
                'finish_reason': self.finish, 'done': self.done, 'usage': self.usage, 'timings': self.timings,
                'completion_id': self.identity[0], 'model': self.identity[1],
                'client_full_seconds': elapsed, 'buffered_first_visible_seconds': self.first_visible,
                'first_visible_is_TTFT': False}


class Stream:
    def __init__(self, body, *, connect=socket.create_connection, clock=time.monotonic):
        self.body = json.loads(json.dumps(body, allow_nan=False))
        require(self.body.get('stream') is True, 'Streaming required')
        self.connect, self.clock = connect, clock
        self.parser = Parser()
        self.lock = threading.Lock()
        self.cancelled = threading.Event()
        self.finished = threading.Event()
        self.sent = threading.Event()
        self.sock = None
        self.error = None
        self.started = self.ended = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        require(self.started is None, 'No transport replay')
        self.started = self.clock()
        self.thread.start()
        return self

    def _run(self):
        response = None
        sock = None
        try:
            sock = self.connect((HOST, PORT), timeout=2)
            sock.settimeout(1200)
            with self.lock:
                self.sock = sock
            if self.cancelled.is_set():
                return
            body = json.dumps(self.body, allow_nan=False).encode()
            header = (f'POST /v1/chat/completions HTTP/1.1\r\nHost: {HOST}:{PORT}\r\n'
                      'Content-Type: application/json\r\nAccept: text/event-stream\r\n'
                      f'Content-Length: {len(body)}\r\nConnection: close\r\n\r\n').encode()
            sock.sendall(header + body)
            self.sent.set()
            response = http.client.HTTPResponse(sock)
            response.begin()
            require(response.status == 200, 'Hosted request HTTP status')
            require(response.getheader('Content-Type', '').split(';')[0] == 'text/event-stream', 'Not SSE')
            while not self.cancelled.is_set():
                line = response.readline(MAX_LINE + 1)
                if not line:
                    break
                self.parser.feed(line, self.clock() - self.started)
            if not self.cancelled.is_set():
                self.parser.result(self.clock() - self.started)
        except BaseException as exc:
            self.error = repr(exc)
        finally:
            try:
                if response is not None:
                    response.close()
            finally:
                if sock is not None:
                    sock.close()
                self.ended = self.clock()
                self.finished.set()

    def cancel(self, timeout=3):
        self.cancelled.set()
        with self.lock:
            sock = self.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
        if self.started is not None:
            self.thread.join(timeout)
            require(not self.thread.is_alive(), 'Own reader release unverified')

    def result(self):
        require(self.finished.is_set(), 'Reader not terminal')
        require(not self.cancelled.is_set() and self.error is None, 'Partial/cancelled/error response')
        return self.parser.result(self.ended - self.started)

    def partial(self):
        return {'content': self.parser.content, 'reasoning': self.parser.reasoning,
                'raw_sse': self.parser.raw, 'error': self.error,
                'cancelled': self.cancelled.is_set(), 'reader_finished': self.finished.is_set()}
