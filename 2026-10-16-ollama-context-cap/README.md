# Ollama: `/v1` ignores `num_ctx`, and long conversations lose their start silently

Ollama's OpenAI-compatible endpoint (`/v1/chat/completions`) has no field for context size. A `num_ctx` sent through the OpenAI SDK's `extra_body` (`"options": {"num_ctx": ...}`) is dropped while the request is decoded. With nothing set on the request, the model or the server, Ollama uses its VRAM-based default: 4,096 tokens below 24 GiB, 32,768 up to 48 GiB, 262,144 above. When the conversation doesn't fit, `chatPrompt()` (`server/prompt.go`) removes whole messages from the front until it does, keeping system messages and the newest message. The reply is HTTP 200 with `finish_reason: stop`, and the only trace is a DEBUG-level log line: `truncating input messages which exceed context length`.

The result is wrong answers with a success code. In the run below, a 5,415-token conversation was read as 3,612 tokens, the user's first instruction was dropped, and the model invented the codename. Fixes: set `OLLAMA_CONTEXT_LENGTH` on the server, publish a derived model with `PARAMETER num_ctx`, use the native `/api/chat` with `options.num_ctx`, or send `truncate: false` on the native API to get an error instead of a silent cut. Whichever you choose, add a client-side guard that alerts when `prompt_tokens` stops growing.

## Versions and status (as of 2026-10-16)

- Measured on **Ollama v0.40.5** (released 2026-10-14, latest), macOS arm64 release tarball, model `qwen2.5:1.5b` (Q4_K_M), Apple M1 Max 32 GB (server log: `total_vram="21.3 GiB" default_num_ctx=4096`).
- `/v1` has ignored `num_ctx` since OpenAI compatibility was added (v0.1.24, 2024-02-08). Requests: #5356 (closed 2025-04-16 in favour of the env var) and #7063 (open). PR #16825 (forward `num_ctx` on `/v1`) has been open since 2026-06-20.
- Defaults: 2,048 → 4,096 in v0.6.7 (2025-04-26), VRAM tiers since v0.15.5 (2026-02-03). `OLLAMA_CONTEXT_LENGTH` since v0.5.13 (2025-02-27). `truncate` since v0.3.4 (2024-08-06). A single message larger than the window errors since v0.30.9 (2026-06-15).
- Status: **open / by design**. No fixed release.

Links: <https://docs.ollama.com/context-length>, <https://docs.ollama.com/api/openai-compatibility>, <https://github.com/ollama/ollama/pull/16825>, <https://github.com/NousResearch/hermes-agent/issues/43900>.

## Run

No dependencies (Python standard library). Needs a running Ollama server with its default context and the model pulled:

```bash
ollama pull qwen2.5:1.5b
export OLLAMA_URL=http://127.0.0.1:11434   # default
python3 reproduce.py          # BEFORE: one call + per-turn trace (trace_turns)
python3 fix.py                # AFTER: A native num_ctx, B derived model, D truncate:false, E guard
OLLAMA_CONTEXT_LENGTH=16384 ollama serve   # in another terminal / port, then:
python3 fix.py --server-env   # C: server-wide setting
python3 detect.py             # every model: working vs trained context
python3 -m unittest discover -s tests -v   # 9 offline tests (+3 live with OLLAMA_TEST_URL)
```

`fix.py` creates a model tag `qwen-ctx16k`. Remove it with `ollama rm qwen-ctx16k`.

## Files

- `common.py`: the running-example conversation (codename BLUE-HERON + six log batches) and a stdlib HTTP client.
- `reproduce.py`: `one_call()` and `trace_turns()` (BEFORE).
- `fix.py`: options A–E (AFTER).
- `detect.py`: `check(model)` reads `/api/show` and `/api/ps` and flags models whose working context is below a quarter of their trained context.
- `guard.py`: `TruncationGuard` raises `ContextTruncated` when `prompt_tokens` doesn't grow while messages do, and warns above 75% of a known window. A `characters / 4` size estimate was tried and dropped: these logs run at about 2.4 characters per token, so the estimate (3,226) came in *below* what the server read (3,612) and missed the cut.
- `fake_ollama.py`: a **simulated** server (no model) mimicking the measured behaviour, for offline tests.
- `OUTPUTS.txt`: the real outputs quoted in the article.

## Notes

- Which messages survive (turn 6): system, then everything from the acknowledgement after log batch 1 onwards. Dropped: task, "Understood.", log 0, ack 0, log 1 (1,803 tokens). Measured by sizing `[system] + messages[i:]`.
- Some models use Ollama's native chat-template path (`prepareNativeChatRequest`) rather than `chatPrompt()`. This run went through `chatPrompt()` (log `source=prompt.go:77`); other models were not measured.
