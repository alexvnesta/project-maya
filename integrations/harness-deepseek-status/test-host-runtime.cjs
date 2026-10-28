// CPU-only check using the actual installed Cordis/Connection implementation.
// Run with the installed Electron binary in ELECTRON_RUN_AS_NODE mode.
const assert = require('node:assert/strict');
const {createRequire} = require('node:module');
const {pathToFileURL} = require('node:url');
const path = require('node:path');
const installed = createRequire('/Applications/DeepSeek Harness.app/Contents/Resources/app.asar/dsh/package.json');

(async () => {
  const {Context} = installed('@deepseek-ai/cordis');
  const {createScope} = installed('@deepseek-ai/dsh-scope');
  const {HostConnectionService} = installed('@deepseek-ai/dsh-client-connection');
  const {apply} = await import(pathToFileURL(path.join(__dirname, 'index.mjs')));
  const scope = createScope(new Context(), {});
  const ctx = scope.ctx;
  const connection = new HostConnectionService(ctx, ['localhost'], {});
  const oldFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async (url, options) => {
    assert.equal(url, 'http://127.0.0.1:18012/metrics');
    assert.equal(options.method, 'GET'); calls++;
    return Response.json({engine: {model: 'deepseek-v4.1-flash-iq2-xs'},
      live: {state: 'reading', queued: 1, prompt_read: 1024, prompt_total: 8192, elapsed_s: 2}});
  };
  try {
    apply(ctx);
    const handler = connection.createSharedFetchHandler('/api');
    const get = () => new Request('http://harness.invalid/api/deepseek-status');
    const owner = {principal: {kind: 'owner'}};
    let response = await handler.fetch(get(), owner);
    assert.equal(response.status, 200);
    const data = await response.json();
    assert.equal(data.server.state, 'reading'); assert.equal(data.server.prompt_read, 1024);
    assert.equal(data.server.prompt_total, 8192); assert.equal(calls, 1);
    assert.equal((await handler.fetch(get(), {principal: {kind: 'api'}})).status, 403);
    assert.equal(calls, 1);
    assert.equal((await handler.fetch(new Request('http://harness.invalid/api/deepseek-status', {method: 'POST'}), owner)).status, 404);
    assert.equal((await handler.fetch(new Request('http://harness.invalid/api/deepseek-status?url=foreign'), owner)).status, 400);
    assert.equal(calls, 1);
    await scope.dispose();
    assert.equal((await handler.fetch(get(), owner)).status, 404);
    console.log(JSON.stringify({passed: true, controls: [
      'actual Connection dispatches fixed GET and sanitized prompt progress',
      'actual Connection rejects non-owner peer before fetching',
      'actual Connection rejects POST and route refuses query override',
      'actual Context disposal withdraws route',
    ], real_model_requests: 0, listener_started: false}));
  } finally {
    globalThis.fetch = oldFetch;
    await scope.dispose();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
