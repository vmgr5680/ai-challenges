# 2026-10-14: LiteLLM's `num_retries` does not cover a stream that drops before its first event

When an upstream model provider answers a streaming request with `200 OK` and then closes the connection before the first server-sent event, LiteLLM's Router makes **one** upstream attempt, however `num_retries` is set. The Router's retry loop wraps the call that *opens* the stream, and that call has already returned successfully when the body read fails. The error then surfaces while the caller iterates: as an exception in the SDK, or as an HTTP 500 from the proxy (the reporter of #45457 saw an HTTP 200 carrying an in-stream error event, which this repo did not reproduce). Reported on three routes: chat completions with a Vertex 429 (#29808, June 2026, open), `/v1/messages` (#44238, fixed by PR #44276, closed 2026-10-05) and Google GenAI `streamGenerateContent` (#45457, opened 2026-10-08, open).

Measured here against a local fake upstream: on the latest stable release (1.105.1, published 2026-10-14) none of the three routes retries; the release candidate 1.106.0rc2 (2026-10-13) retries `/v1/messages` only. A fallback model group rescues chat completions and `/v1/messages` on stable, but not `streamGenerateContent`. A caller-side guard that reads the first chunk inside its own retry loop (`stream_guard.first_chunk_retry`) fixes all three routes on every release tested.

## Affected and fixed versions (as measured, 2026-10-14)

| Release | Published | `/chat/completions` | `/v1/messages` | `streamGenerateContent` |
|---|---|---|---|---|
| 1.104.0 | 2026-10-03 | not retried | not retried | not retried |
| 1.105.1 (latest stable) | 2026-10-14 | not retried | not retried | not retried |
| 1.106.0rc2 | 2026-10-13 | not retried | **retried** (PR #44276) | not retried |

Only these three releases were measured. Issue reports cover 1.85.1 (#29808), 1.100.0 (#44238) and 1.104.0 (#45457). Avoid litellm 1.82.7 and 1.82.8 entirely: they were the compromised PyPI uploads (#24518) and were removed.

Links: [#45457](https://github.com/BerriAI/litellm/issues/45457) · [#44238](https://github.com/BerriAI/litellm/issues/44238) · [PR #44276](https://github.com/BerriAI/litellm/pull/44276) · [#29808](https://github.com/BerriAI/litellm/issues/29808) · [PR #45076](https://github.com/BerriAI/litellm/pull/45076) (draft, `/v1/responses`)

## What is here

| File | What it does |
|---|---|
| `pattern.py` | Stdlib toy of the bug class: `retry_open_only()` (pre-fix shape) vs `retry_until_first_event()` (fix). |
| `reproduce.py` / `fix.py` | BEFORE / AFTER on the toy model. |
| `stream_guard.py` | The copyable caller-side fix: `first_chunk_retry(open_stream, retries)` for any async stream. |
| `fake_upstream.py` | Local fake provider (OpenAI, Anthropic and Gemini SSE) that drops the first N streams after `200 OK`, before the first event. Reusable as a CI fault injector. |
| `litellm_probe.py` | Real LiteLLM Router, `num_retries=2`, three routes: counts upstream attempts. |
| `litellm_guarded.py` | Same calls wrapped in `first_chunk_retry`. |
| `proxy_probe.py` | Real `litellm --config` proxy: what a raw HTTP client and the OpenAI SDK see. |
| `alternatives/fallbacks_probe.py` | Does a fallback model group help? Also shows the error arrives *while iterating*. |
| `detect.py` | One-minute check: installed version, configs with `num_retries` but no fallbacks, unguarded streaming call sites. Exit 1 = act. |
| `samples/` | Files for `detect.py` to scan. Never run. |
| `tests/` | 10 tests: toy bug and fix, guard behaviour (retries only before the first chunk, never on client errors), detector, and three pinned-release checks (skipped if venvs are missing). |
| `OUTPUTS.txt` | The real outputs quoted in the article. |

Everything binds to 127.0.0.1 and talks only to the fake upstream. No API keys.

## Run it

```bash
python3 reproduce.py && python3 fix.py           # toy model, stdlib
python3 detect.py path/to/your/app               # exit 1 = at risk

# pinned releases (Python 3.13 used)
for v in 1.104.0 1.105.1 1.106.0rc2; do
  python3.13 -m venv .venv-$v && .venv-$v/bin/pip install -q "litellm[proxy]==$v"
done
.venv-1.105.1/bin/python litellm_probe.py
.venv-1.105.1/bin/python litellm_guarded.py
.venv-1.105.1/bin/python alternatives/fallbacks_probe.py
.venv-1.105.1/bin/python proxy_probe.py

python3 -m unittest discover -s tests -v         # 10 tests
```

## The guard, in your code

```python
from stream_guard import first_chunk_retry

async def open_stream():
    return await router.acompletion(model="chat", messages=msgs, stream=True)

async for chunk in await first_chunk_retry(open_stream, retries=2):
    ...
```

It retries only failures that happen before the first chunk (nothing has reached your user yet) and only transport-type errors. After the first chunk the stream is committed and errors propagate. If an upstream layer also retries, attempts multiply: budget them together.

## A CI test for any gateway

Point your gateway at `FakeUpstream(drops=1)` and assert the upstream saw at least two requests for one streaming call. That one assertion would have caught every report above.
