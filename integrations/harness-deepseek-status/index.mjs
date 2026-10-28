import {createHash, randomBytes} from 'node:crypto';
import {createStatusReader} from './status.mjs';

export const name = 'harness-deepseek-status';
export const inject = ['connection', 'llm'];

// Only counts and an ephemeral opaque session tag. Never inspect text, image
// pixels, attachment references, tool arguments, or model content.
export function requestMetadata(options, salt) {
  let images = 0, messages = 0;
  for (const message of options.messages ?? []) {
    messages += 1;
    if (message.role !== 'user' && message.role !== 'tool') continue;
    for (const block of message.content ?? []) if (block.type === 'image' && block.offloaded !== true) images += 1;
  }
  const session = options.sessionId === undefined ? null
    : createHash('sha256').update(salt).update(String(options.sessionId)).digest('hex').slice(0, 16);
  return {session, images, messages};
}

export function apply(ctx) {
  const reader = createStatusReader();
  const salt = randomBytes(32);
  let nextId = 0;
  const active = new Map(), recent = [];
  ctx.effect(() => () => reader.dispose(), 'deepseek-status: metadata reader');
  ctx.connection.fetch.register({
    path: '/api/deepseek-status', methods: ['GET'], requestBody: 'buffered',
    async fetch(request) {
      if (new URL(request.url).search) return new Response('No query parameters', {status: 400});
      return Response.json({server: await reader.read(), harness: {active: [...active.values()], recent: [...recent]}},
        {headers: {'cache-control': 'no-store'}});
    },
  });
  ctx.on('llm/stream', (options, next) => {
    if (options.model !== 'deepseek-v4.1-flash-iq2-xs') return next();
    const id = ++nextId;
    const metadata = requestMetadata(options, salt);
    return (async function* () {
      // Check at iteration time, including streams constructed before any run.
      if (active.size >= 32) { yield* next(); return; }
      const row = {id, ...metadata, started_at: Date.now()};
      active.set(id, row);
      let outcome = 'consumer-closed';
      let usage;
      try {
        for await (const chunk of next()) {
          if (chunk.type === 'usage') {
            // The adapter's usage chunk is metadata; whitelist rather than copy.
            const value = chunk.usage ?? chunk;
            usage = {};
            for (const key of ['inputTokens', 'outputTokens', 'cacheReadTokens', 'totalTokens'])
              if (Number.isSafeInteger(value[key]) && value[key] >= 0) usage[key] = value[key];
          }
          if (chunk.type === 'finish') outcome = ['stop', 'length', 'aborted', 'error', 'tool-calls'].includes(chunk.reason?.kind)
            ? chunk.reason.kind : 'finished';
          yield chunk; // No request, response, timeout, cancellation or retry changes.
        }
      } catch (error) { outcome = 'error'; throw error; }
      finally {
        active.delete(id);
        recent.push({...row, ended_at: Date.now(), outcome: options.signal?.aborted ? 'aborted' : outcome,
          ...(usage === undefined ? {} : {usage})});
        if (recent.length > 16) recent.shift();
      }
    })();
  });
}
