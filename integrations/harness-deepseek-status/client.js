// Native Harness browser-plugin format; no application bundle patch or build.
window.__ModuleLoader__.load({id: '@alex/harness-deepseek-status', factory: require => {
  const React = require('react');
  const numeric = n => typeof n === 'number' && Number.isFinite(n) && n >= 0;
  const count = n => numeric(n) ? Math.floor(n).toLocaleString('en-US') : '?';
  function description(server) {
    if (!server || server.state === 'unavailable') return 'DeepSeek server status unavailable';
    if (server.state === 'other-model') return null;
    const queued = server.queued ? ` · ${count(server.queued)} queued` : '';
    const elapsed = numeric(server.elapsed_s) ? ` · ${Math.floor(server.elapsed_s / 60)}m ${Math.floor(server.elapsed_s % 60)}s elapsed` : '';
    if (server.state === 'reading') {
      const position = numeric(server.prompt_read) && numeric(server.prompt_total) && server.prompt_total > 0
        ? ` · prompt position ${count(server.prompt_read)} / ${count(server.prompt_total)}` : ' · waiting for prompt progress';
      const rate = numeric(server.prefill_tok_s) && server.prefill_tok_s > 0 ? ` · ${Math.round(server.prefill_tok_s)} new tokens/s` : '';
      return `DeepSeek server: reading${position}${rate}${elapsed}${queued}`;
    }
    if (server.state === 'generating') return `DeepSeek server: generating · ${count(server.generated)} tokens${elapsed}${queued}`;
    return `DeepSeek server: ${server.state}${elapsed}${queued}`;
  }
  function watch(fetchHost, receive, schedule = setTimeout, unschedule = clearTimeout) {
    let stopped = false, timer;
    const lifetime = new AbortController();
    async function poll() {
      try {
        const response = await fetchHost('api/deepseek-status', {
          method: 'GET', cache: 'no-store', signal: AbortSignal.any([lifetime.signal, AbortSignal.timeout(4000)]),
        });
        if (!response.ok) throw new Error('Status unavailable');
        const data = await response.json();
        if (!stopped) receive(data);
      } catch { if (!stopped) receive({server: {state: 'unavailable'}}); }
      finally { if (!stopped) timer = schedule(poll, 2000); }
    }
    poll();
    return () => { stopped = true; lifetime.abort(); if (timer !== undefined) unschedule(timer); };
  }
  function Status() {
    const [snapshot, setSnapshot] = React.useState(null);
    React.useEffect(() => {
      const transport = globalThis.__DSH_TRANSPORT__;
      const fetchHost = transport?.fetch ? transport.fetch.bind(transport) : globalThis.fetch.bind(globalThis);
      return watch(fetchHost, setSnapshot);
    }, []);
    if (snapshot === null) return null;
    const text = description(snapshot.server);
    if (text === null) return null;
    return React.createElement('div', {
      role: 'status', 'data-deepseek-status': true,
      title: 'Shared DeepSeek server activity, including other clients. Prompt position includes reused tokens; this is not a completion ETA.',
      style: {padding: '5px 14px', fontSize: '12px', opacity: 0.8, borderTop: '1px solid #80808040'},
    }, text);
  }
  function apply(ctx) {
    ctx.slots.inject('shell.bottom', () => ctx.slots.register({name: 'shell.bottom'}, Status));
  }
  return {apply, inject: ['slots', 'connection'], description, watch};
}});
