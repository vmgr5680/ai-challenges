# 2026-10-26 — LLM gateways that silently drop `cache_control`

Anthropic prompt caching is opt-in per request: the client puts `cache_control` on a content block (or at the top level of the body for automatic caching), and later requests that share that prefix are billed at 0.1x the base input price instead of 1x. Many teams send Claude traffic through an LLM gateway (an AI or LLM proxy that offers one API in front of many providers). Several gateways parse each request into their own typed model and write a new provider request from it. When that model has no field for `cache_control`, the marker is discarded during parsing. The request still succeeds, the answer is the same, and the only sign is `cache_read_input_tokens: 0` in the usage object and a larger bill.

The same root cause shows up in at least four independent projects in 2026: a pydantic model left at its default `extra="ignore"` (MLflow AI Gateway), Go structs without the field (Bifrost), an internal representation without a cache field (argo-proxy via llm-rosetta), and a Responses-to-Chat bridge that did not copy the field (LiteLLM). This folder reproduces the pattern offline with a simulated provider, shows the fix (carry unknown fields through) and the alternative (same-format passthrough), and gives a detector and a CI guard.

## Affected and fixed (as of 2026-10-26)

| Project | Where | Affected | Status | Source |
|---|---|---|---|---|
| MLflow AI Gateway | normalized `/chat/completions` route to Anthropic, Vertex Claude, Bedrock Claude | reported on 3.16.1; `TextContentPart` on `master` still has no `model_config` (checked 2026-10-26) | **open**, labelled Acknowledged + ready; no linked PR | [mlflow#26477](https://github.com/mlflow/mlflow/issues/26477) (opened 2026-10-06) |
| Bifrost | message-level `cache_control` on chat messages (block-level survives) | transports v2.3.0 (core v1.12.0), `dev` 1813de533 | **open**; fix PR [#8713](https://github.com/maximhq/bifrost/pull/8713) open, awaiting maintainer review | [bifrost#8712](https://github.com/maximhq/bifrost/issues/8712) (opened 2026-10-19) |
| LiteLLM | `/v1/responses` → chat-completions bridge (Anthropic, Bedrock) | reported on v1.91.0 | **fixed on `main`** by [#32511](https://github.com/BerriAI/litellm/pull/32511), merged 2026-10-14 (d03923e6); present in v1.107.0-rc.2; **not** in stable v1.106.4 / v1.105.5 / v1.104.7 / v1.103.9 (published 2026-10-25), checked by searching for `_with_cache_control_on_last_block` | [litellm#33687](https://github.com/BerriAI/litellm/issues/33687) (opened 2026-07-17, closed 2026-10-14) |
| argo-proxy | Anthropic → IR → Anthropic round trip | 3.1.x (passthrough removed in 3.1.0, commit 8eee6f7) | **fixed**: llm-rosetta ≥ 0.7.3 (`cache_hint` on IR parts), passthrough restored in llm-rosetta 0.8.1; closed 2026-08-18 | [argo-proxy#140](https://github.com/Oaklight/argo-proxy/issues/140) |

## Run

```bash
python3 reproduce.py                      # BEFORE: direct vs typed gateway, 10-turn session
python3 fix.py                            # AFTER: preserving gateway, passthrough, round-trip guard
python3 -m unittest discover -s tests -v  # 10 tests
python3 servers.py &                      # local provider :8701, buggy gateway :8702, fixed :8703
python3 detect.py probe --url http://127.0.0.1:8702/v1/messages
python3 detect.py scan usage.jsonl        # your exported usage records, one JSON object per line
```

Standard library only (Python 3.10+). No API keys, no network except localhost.

## Files

- `fake_anthropic.py` — **simulated** provider with prompt-cache accounting (breakpoints, 20-block lookback, minimum length, usage fields). Tokens are counted as words.
- `gateway.py` — `translate_typed()` (bug), `translate_preserving()` (fix), `passthrough()` (alternative).
- `session.py` — 10-turn agent session with two breakpoints per turn; cost in base-input units (write 1.25x, read 0.1x).
- `roundtrip_guard.py` — `lost_fields(sent, forwarded)`: every key path the gateway dropped. Put it in your gateway's CI.
- `detect.py` — `probe` (two identical calls, second must read from cache) and `scan` (usage log has big prompts but zero cache reads).
- `servers.py` — the local HTTP servers used by the tests.

## Limits

- The provider is simulated; real token counts, minimums (512–4,096 tokens by model) and prices differ. The 4.6x figure is this session's ratio under the documented multipliers, not a measured bill. The Bifrost report's real measurement was $0.727 vs $0.268 for five sessions.
- `detect.py probe --format openai` builds the request most gateways document for Claude on their chat route, but it was only tested against the local Anthropic-format servers.
- A probe can also show zero reads when the gateway spreads calls across different provider accounts, regions or keys (caches are not shared between them), or when the prompt is under the model minimum. Run it twice and check the gateway's routing before concluding the marker is dropped; `roundtrip_guard.py` against a recording upstream tells you for sure.
