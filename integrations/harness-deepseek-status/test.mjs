import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {sanitizeMetrics, createStatusReader, METRICS_URL} from './status.mjs';
import {apply, requestMetadata} from './index.mjs';

const MODEL = 'deepseek-v4.1-flash-iq2-xs';
const metric = (live = {}) => ({engine: {model: MODEL}, live: {state: 'reading', queued: 0,
  prompt_read: 12000, prompt_total: 32000, generated: null, elapsed_s: 25,
  prefill_tok_s_mean: 480, tok_s: null, ...live}});
const response = value => Response.json(value);
const tick = () => new Promise(resolve => setImmediate(resolve));

function client(react = {}, transport) {
  let plugin;
  const context = {AbortController, AbortSignal, setTimeout, clearTimeout,
    __DSH_TRANSPORT__: transport,
    window: {__ModuleLoader__: {load(spec) { plugin = spec.factory(name => {
      assert.equal(name, 'react'); return react;
    }); }}}};
  vm.runInNewContext(readFileSync(new URL('./client.js', import.meta.url), 'utf8'), context);
  return plugin;
}
function host() {
  let route, middleware, dispose;
  const calls = [];
  const prior = globalThis.fetch;
  globalThis.fetch = async (url, options) => { calls.push([url, options]); return response(metric()); };
  try {
    apply({effect(callback) { dispose = callback(); },
      connection: {fetch: {register(value) { route = value; }}},
      on(event, callback) { assert.equal(event, 'llm/stream'); middleware = callback; }});
  } finally { globalThis.fetch = prior; }
  return {calls, route, middleware, dispose,
    async snapshot() { return (await route.fetch(new Request('http://harness.invalid/api/deepseek-status'))).json(); }};
}

test('package declares its supported profile layer and matching browser module', () => {
  const pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8'));
  assert.equal(pkg.name, '@alex/harness-deepseek-status');
  assert.equal(pkg.dsh.bundle.patch, './cordis.patch.yml');
  assert.equal(pkg.exports['./client'], './client.js');
  assert.equal(pkg.dsh.client.platform, 'web');
  const layer = readFileSync(new URL('./cordis.patch.yml', import.meta.url), 'utf8');
  assert.equal(layer, '- insert:\n    - id: local-deepseek-status\n      name: "@alex/harness-deepseek-status"\n');
});

test('whitelists metadata and omits all request history and model content', () => {
  const raw = {...metric(), requests: [{input: 'private', output: 'private'}], secret: 'private'};
  assert.deepEqual(sanitizeMetrics(raw), {state: 'reading', queued: 0, prompt_read: 12000,
    prompt_total: 32000, generated: null, elapsed_s: 25, prefill_tok_s: 480, decode_tok_s: null});
  assert.ok(!JSON.stringify(sanitizeMetrics(raw)).includes('private'));
});
test('rejects missing model, unknown states and impossible progress', () => {
  for (const raw of [null, {}, {engine: {}}, metric({state: 'mystery'}), metric({prompt_read: 33000})])
    assert.throws(() => sanitizeMetrics(raw));
});
test('rejects boolean, negative, nonfinite, fractional and unsafe token counts', () => {
  for (const value of [true, false, -1, NaN, Infinity, 0.5, 2 ** 53]) {
    const s = sanitizeMetrics(metric({prompt_read: value, queued: value}));
    assert.equal(s.prompt_read, null); assert.equal(s.queued, null);
  }
  for (const value of [true, -1, Infinity, NaN]) assert.equal(sanitizeMetrics(metric({elapsed_s: value})).elapsed_s, null);
});
test('idle drops old progress and generation values; another model exposes no data', () => {
  const idle = sanitizeMetrics(metric({state: 'idle', generated: 50}));
  assert.equal(idle.prompt_read, null); assert.equal(idle.prompt_total, null); assert.equal(idle.generated, null);
  assert.deepEqual(sanitizeMetrics({engine: {model: 'qwen'}, live: metric().live}), {state: 'other-model'});
  assert.equal(sanitizeMetrics(metric({state: 'unloaded'})).state, 'unloaded');
});
test('reader uses only fixed GET, forbids redirects and coalesces concurrent views', async () => {
  let calls = 0, time = 0;
  const reader = createStatusReader({now: () => time, fetchMetrics: async (url, options) => {
    assert.equal(url, METRICS_URL); assert.equal(options.method, 'GET'); assert.equal(options.redirect, 'error');
    assert.equal(options.body, undefined); assert.equal(options.headers, undefined); calls++;
    await tick(); return response(metric());
  }});
  const [a, b] = await Promise.all([reader.read(), reader.read()]);
  assert.deepEqual(a, b); assert.equal(calls, 1);
  await reader.read(); assert.equal(calls, 1);
  time = 1501; await reader.read(); assert.equal(calls, 2); reader.dispose();
});
test('reader bounds body and hides HTTP, parse and transport failures', async () => {
  for (const fetchMetrics of [async () => new Response('x', {status: 503}),
    async () => new Response('not json'), async () => response({huge: 'x'.repeat(131073)}),
    async () => { throw new Error('secret URL and credentials'); }]) {
    const reader = createStatusReader({fetchMetrics});
    assert.deepEqual(await reader.read(), {state: 'unavailable'}); reader.dispose();
  }
});
test('reader disposal aborts pending metadata fetch and prevents another fetch', async () => {
  let signal, calls = 0;
  const reader = createStatusReader({fetchMetrics: async (_url, options) => {
    calls++; signal = options.signal;
    return new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new Error('abort')), {once: true}));
  }});
  const pending = reader.read(); reader.dispose();
  assert.equal(signal.aborted, true); assert.deepEqual(await pending, {state: 'unavailable'});
  assert.deepEqual(await reader.read(), {state: 'unavailable'}); assert.equal(calls, 1);
});
test('metadata counts retained input images without touching text, bytes or references', () => {
  const image = {type: 'image'};
  for (const key of ['attachment', 'text', 'url', 'bytes']) Object.defineProperty(image, key, {get() { throw new Error('private access'); }});
  const options = {sessionId: 'private-session', messages: [
    {role: 'user', content: [image, {type: 'image', offloaded: true}]},
    {role: 'tool', content: [image]}, {role: 'assistant', content: [image]},
    {role: 'user', content: [{type: 'text', text: 'private'}]},
  ]};
  const a = requestMetadata(options, Buffer.from('one'));
  const b = requestMetadata(options, Buffer.from('two'));
  assert.equal(a.images, 2); assert.equal(a.messages, 4); assert.match(a.session, /^[a-f0-9]{16}$/);
  assert.notEqual(a.session, b.session); assert.ok(!JSON.stringify(a).includes('private'));
  assert.equal(requestMetadata({}, Buffer.from('one')).session, null);
});
test('host installs an exact GET route on the existing Connection carrier', async () => {
  const h = host();
  assert.equal(h.route.path, '/api/deepseek-status'); assert.deepEqual(h.route.methods, ['GET']);
  assert.equal(h.route.requestBody, 'buffered');
  const bad = await h.route.fetch(new Request('http://harness.invalid/api/deepseek-status?url=http://foreign'));
  assert.equal(bad.status, 400); assert.equal(h.calls.length, 0);
  const good = await h.route.fetch(new Request('http://harness.invalid/api/deepseek-status'));
  assert.equal(good.headers.get('cache-control'), 'no-store'); assert.equal(h.calls.length, 1);
  h.dispose();
});
test('middleware preserves every request option and exact response chunk identity', async () => {
  const h = host();
  const options = Object.freeze({model: MODEL, temperature: 1, maxTokens: 262144, sessionId: 'private',
    messages: Object.freeze([]), signal: new AbortController().signal});
  const chunks = [{type: 'text-delta', text: 'private output'},
    {type: 'usage', usage: {inputTokens: 20, cacheReadTokens: 18, outputTokens: 2, totalTokens: 40, secret: 'private'}},
    {type: 'finish', reason: {kind: 'stop'}}];
  let dispatched = 0;
  const stream = h.middleware(options, () => { dispatched++; return (async function* () { yield* chunks; })(); });
  let i = 0;
  for await (const chunk of stream) assert.equal(chunk, chunks[i++]);
  assert.equal(i, 3); assert.equal(dispatched, 1); assert.equal(options.maxTokens, 262144);
  const snapshot = await h.snapshot();
  assert.equal(snapshot.harness.active.length, 0); assert.equal(snapshot.harness.recent[0].outcome, 'stop');
  assert.deepEqual(snapshot.harness.recent[0].usage, {inputTokens: 20, cacheReadTokens: 18, outputTokens: 2, totalTokens: 40});
  assert.ok(!JSON.stringify(snapshot).includes('private')); h.dispose();
});
test('other models bypass instrumentation and retain the original stream', () => {
  const h = host(), sentinel = {};
  assert.equal(h.middleware({model: 'qwen'}, () => sentinel), sentinel); h.dispose();
});
test('consumer cancellation closes the original iterator without retries', async () => {
  const h = host(); let closes = 0, calls = 0;
  const control = new AbortController();
  const stream = h.middleware({model: MODEL, signal: control.signal}, () => {
    calls++; return (async function* () { try { yield {type: 'text-delta'}; yield {type: 'text-delta'}; } finally { closes++; } })();
  });
  await stream.next(); control.abort(); await stream.return();
  const data = await h.snapshot(); assert.equal(data.harness.recent[0].outcome, 'aborted');
  assert.equal(closes, 1); assert.equal(calls, 1); h.dispose();
});
test('provider failure propagates unchanged and never stores error text', async () => {
  const h = host(), failure = new Error('private failure');
  const stream = h.middleware({model: MODEL}, () => (async function* () { throw failure; })());
  await assert.rejects(stream.next(), error => error === failure);
  const data = await h.snapshot(); assert.equal(data.harness.recent[0].outcome, 'error');
  assert.ok(!JSON.stringify(data).includes('private')); h.dispose();
});
test('lazy concurrent streams keep 32 active and 16 completed diagnostic records', async () => {
  const h = host(), streams = [];
  for (let i = 0; i < 40; i++) streams.push(h.middleware({model: MODEL}, () => (async function* () { yield {type: 'text-delta'}; })()));
  await Promise.all(streams.map(s => s.next()));
  assert.equal((await h.snapshot()).harness.active.length, 32);
  await Promise.all(streams.map(s => s.return()));
  const data = await h.snapshot(); assert.equal(data.harness.active.length, 0); assert.equal(data.harness.recent.length, 16);
  h.dispose();
});
test('client labels shared prompt position, not generated tokens or completion ETA', () => {
  const ui = client();
  const text = ui.description({state: 'reading', prompt_read: 12000, prompt_total: 32000, prefill_tok_s: 480, elapsed_s: 65, queued: 1});
  assert.match(text, /DeepSeek server: reading/); assert.match(text, /12,000 \/ 32,000/);
  assert.match(text, /480 new tokens\/s/); assert.match(text, /1m 5s elapsed/); assert.match(text, /1 queued/);
  assert.ok(!text.includes('ETA')); assert.ok(!text.includes('generated'));
});
test('client waits for real progress and distinguishes idle from unavailable', () => {
  const ui = client();
  assert.match(ui.description({state: 'reading'}), /waiting for prompt progress/);
  assert.equal(ui.description({state: 'idle', queued: 0}), 'DeepSeek server: idle');
  assert.equal(ui.description({state: 'other-model'}), null);
  assert.match(ui.description({state: 'idle', queued: 2}), /2 queued/);
  assert.match(ui.description({state: 'unavailable'}), /unavailable/);
  assert.match(ui.description({state: 'unloaded'}), /unloaded/);
});
test('client polling only reads status and never overlaps requests', async () => {
  const ui = client(); let next, calls = 0; const seen = [];
  const stop = ui.watch(async (path, options) => {
    assert.equal(path, 'api/deepseek-status'); assert.equal(options.method, 'GET'); assert.equal(options.body, undefined);
    calls++; return response({server: {state: 'reading'}});
  }, data => seen.push(data), (fn, ms) => { assert.equal(ms, 2000); next = fn; return 1; }, () => {});
  await tick(); assert.equal(calls, 1); assert.equal(seen.length, 1);
  await next(); assert.equal(calls, 2); stop();
});
test('client unmount cancels pending status without publishing late data', async () => {
  const ui = client(); let resolve, signal, scheduled = 0, published = 0;
  const stop = ui.watch((_path, options) => { signal = options.signal; return new Promise(r => { resolve = r; }); },
    () => published++, () => scheduled++, () => {});
  stop(); resolve(response({server: {state: 'reading'}})); await tick();
  assert.equal(signal.aborted, true); assert.equal(published, 0); assert.equal(scheduled, 0);
});
test('client transport failure displays unavailable instead of stale idle', async () => {
  const ui = client(); let value;
  const stop = ui.watch(async () => { throw new Error('offline'); }, data => { value = data; }, () => 1, () => {});
  await tick(); assert.equal(value.server.state, 'unavailable'); stop();
});
test('client uses the native shell Fetch carrier and existing bottom seat', async () => {
  let component, effect, fetches = 0, cleanup;
  const ui = client({useState: () => [{server: {state: 'reading', prompt_read: 1, prompt_total: 10}}, () => {}],
    useEffect: fn => { effect = fn; }, createElement: (type, props, text) => ({type, props, text})},
    {fetch: async path => { assert.equal(path, 'api/deepseek-status'); fetches++; return response({server: {state: 'idle'}}); }});
  ui.apply({slots: {inject(name, fn) { assert.equal(name, 'shell.bottom'); fn(); },
    register(options, view) { assert.equal(options.name, 'shell.bottom'); component = view; }}});
  const view = component(); assert.equal(view.props['data-deepseek-status'], true);
  assert.match(view.props.title, /including other clients/);
  cleanup = effect(); await tick(); assert.equal(fetches, 1); cleanup();
});
