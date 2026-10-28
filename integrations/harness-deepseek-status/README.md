# DeepSeek status for Harness

This local Harness plugin adds a shared-server activity strip in the existing
`shell.bottom` seat. It reads only the existing loopback model router's `/metrics`.
It never changes a model request, sampling, images, reasoning, timeouts, retries,
model selection or serving configuration. No additional listener or service runs.

The Host uses Harness's existing authenticated `connection.fetch` route registry;
the browser uses the shell's normal Fetch carrier. There is no CORS exception,
application-bundle patch or credential copy. Idle is explicitly labeled. Unavailable
metadata is explicitly unavailable, never reported as idle or a native fault.
Prompt position includes cache reuse and is not an estimate of work remaining.

A bounded in-memory diagnostic (32 active and 16 completed calls) records counts,
numeric usage, outcomes and salted, process-local opaque session tags. It never
records text, tool arguments, images, attachment identifiers, URLs or file paths.
It disappears when the plugin is unloaded. This helps distinguish image-bearing
interleaving from prefix changes without examining conversation content. The
progress indicator describes the shared server, not an assumed selected session.

The code targets the installed Harness 0.2.1-rc.3 public plugin interfaces. Test
with `node --test test.mjs`. Installation and live UI validation are separate from
these CPU tests. Recheck the plugin interfaces after a Harness upgrade.
