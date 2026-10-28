// Observe the existing backend. This module never selects a model or generates.
export const METRICS_URL = 'http://127.0.0.1:18012/metrics';
const integer = value => Number.isSafeInteger(value) && value >= 0 ? value : null;
const number = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;

export function sanitizeMetrics(raw) {
  if (!raw || typeof raw !== 'object') throw new Error('Invalid metrics');
  if (typeof raw.engine?.model !== 'string') throw new Error('Missing model');
  if (raw.engine.model !== 'deepseek-v4.1-flash-iq2-xs') return {state: 'other-model'};
  const live = raw.live;
  if (!live || !['idle', 'unloaded', 'loading', 'reading', 'generating', 'queued'].includes(live.state)) throw new Error('Unknown state');
  const read = integer(live.prompt_read), total = integer(live.prompt_total);
  if (read !== null && total !== null && read > total) throw new Error('Invalid progress');
  return {
    state: live.state, queued: integer(live.queued),
    prompt_read: live.state === 'reading' ? read : null, prompt_total: live.state === 'reading' ? total : null,
    generated: live.state === 'generating' ? integer(live.generated) : null, elapsed_s: number(live.elapsed_s),
    prefill_tok_s: live.state === 'reading' ? number(live.prefill_tok_s_mean) : null,
    decode_tok_s: live.state === 'generating' ? number(live.tok_s) : null,
  };
}

export function createStatusReader({fetchMetrics = globalThis.fetch, now = Date.now} = {}) {
  const lifetime = new AbortController();
  let last, lastAt = -Infinity, pending;
  return {
    async read() {
      if (lifetime.signal.aborted) return {state: 'unavailable'};
      if (last && now() - lastAt < 1500) return last;
      if (pending) return pending;
      pending = (async () => {
        try {
          const response = await fetchMetrics(METRICS_URL, {
            method: 'GET', redirect: 'error', cache: 'no-store',
            signal: AbortSignal.any([lifetime.signal, AbortSignal.timeout(3000)]),
          });
          if (!response.ok || !response.body) throw new Error('Metrics unavailable');
          // Read a bounded metadata response, then discard the request history.
          const reader = response.body.getReader();
          const parts = [];
          let bytes = 0;
          try {
            while (true) {
              const row = await reader.read();
              if (row.done) break;
              bytes += row.value.byteLength;
              if (bytes > 131072) throw new Error('Metrics too large');
              parts.push(row.value);
            }
          } finally {
            await reader.cancel().catch(() => {});
          }
          const body = new Uint8Array(bytes);
          let offset = 0;
          for (const part of parts) { body.set(part, offset); offset += part.byteLength; }
          last = lifetime.signal.aborted ? {state: 'unavailable'} : sanitizeMetrics(JSON.parse(new TextDecoder().decode(body)));
        } catch {
          last = {state: 'unavailable'}; // An unavailable sample never means idle.
        }
        lastAt = now();
        return last;
      })();
      try { return await pending; } finally { pending = undefined; }
    },
    dispose() { lifetime.abort(); last = undefined; },
  };
}
