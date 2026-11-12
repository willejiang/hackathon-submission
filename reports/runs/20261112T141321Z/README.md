# Case 4–6 recorded Harness run

- `manifest.json`: runtime versions and configuration.
- Per case, `session-trace.jsonl`: lossless durable session events, with receipt timestamps and monotonic clocks. Provider-returned reasoning, assistant messages, tool arguments and results are retained. Private reasoning unavailable from the API cannot be recorded.
- `events.jsonl`: Harness CLI event projection (long content may be truncated; use raw trace for full content).
- `stderr.log`: runtime diagnostics.
- `metrics.json`: case duration, model-step count, build calls, per-step duration, provider-reported token buckets and completeness.
- `rounds.csv`: per-round timing and usage.
- `trace.md`: readable conversation/tool trace; binary images remain in raw JSONL.

A round is one Harness step, including its model generation and tool execution. `cad_build` calls are a separate count. Round durations exclude startup/shutdown overhead included in case duration. For DeepSeek, cached input is recorded separately from uncached input; totalTokens is the reported aggregate. Missing reasoning-token breakdown is unknown, not zero. Background title requests are visible in the raw event log but their usage may not be exposed by the step-usage API. This is not a provider billing statement.

This directory is a local experiment record. No API key is intentionally stored. Existing cases 1–3 are not rerun or overwritten.
