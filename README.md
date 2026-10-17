# ai-issues

Companion code for the "AI issues" Medium articles: one real, current problem in the AI ecosystem per folder, reproduced locally, with a fix, a detection check and tests. Everything runs without API keys; most folders run fully offline (2026-10-16 needs a local Ollama server for the live runs, its tests run offline). Security issues are covered only after an advisory or fix is public, and reproductions run in-process against a fake model, never against real services.

| Date | Folder | Issue | Status |
|---|---|---|---|
| 2026-10-09 | [`2026-10-09-localhost-agent-ui/`](2026-10-09-localhost-agent-ui/) | Web pages can drive the Pydantic AI local chat UI (cross-site simple requests + DNS rebinding; GHSA-h4xc-3qfq-jf93, GHSA-q2xc-rrxj-58x9) | fixed (Aug 2026), advisories public 2026-10-08 |
| 2026-10-12 | [`2026-10-12-mcp-oauth-issuer/`](2026-10-12-mcp-oauth-issuer/) | MCP Python SDK OAuth client could send credentials to a server-chosen authorization server; upgrading alone leaves pre-provisioned providers unbound (GHSA-qx49-fqc8-xw99) | fixed 2026-09-07, advisory 2026-09-28; follow-up steps needed |
| 2026-10-14 | [`2026-10-14-stream-retry-gap/`](2026-10-14-stream-retry-gap/) | LiteLLM Router `num_retries` does not cover a stream that drops after `200 OK` but before its first event (#45457, #44238, #29808) | open on 2 of 3 routes; `/v1/messages` fixed in 1.106.0rc2 |
| 2026-10-15 | [`2026-10-15-loom-idp-bypass/`](2026-10-15-loom-idp-bypass/) | Loom for AWS served every request as super-admin when no IdP was configured; the first fix was spoofable via `X-Forwarded-For` when `FORWARDED_ALLOW_IPS` was widened (CVE-2026-103956, GHSA-vgmj-998f-r8mp) | fixed 2026-08-04 + hardening 2026-10-06 |
| 2026-10-16 | [`2026-10-16-ollama-context-cap/`](2026-10-16-ollama-context-cap/) | Ollama's OpenAI-compatible endpoint ignores `num_ctx`; with the VRAM-based default (4,096 below 24 GiB) long conversations are truncated from the front with HTTP 200 (PR #16825, hermes-agent#43900) | open / by design; workarounds available |

Each folder has its own `README.md` with exact affected and fixed versions, `reproduce.py` (BEFORE), `fix.py` (AFTER), `detect.py`, and `tests/`.
