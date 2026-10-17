# 2026-10-09: Web pages can drive the Pydantic AI local chat UI

Pydantic AI's development chat UI (`Agent.to_web()`, `clai web`) listens on `127.0.0.1:7932`. Before the August 2026 fixes, its chat endpoint accepted a JSON body sent under any content type, so any website open in the developer's browser could start an agent run with a cross-site "simple request" (`Content-Type: text/plain`, no CORS preflight). It also answered to any `Host` header, so a website could use DNS rebinding to look same-origin and send whatever it liked. Either way, the served agent ran and executed its tools with the developer's local privileges and credentials. Tools marked `requires_approval=True` were not protected, because the endpoint trusts approval decisions relayed by the client.

The fixes require `Content-Type: application/json` (415 otherwise) and validate the `Host` header against IP literals, `localhost`, `*.localhost` and an explicit `allowed_hosts` list (421 otherwise). This folder reproduces both holes against the real releases, shows the official fix, and adds `LocalOnlyGuard`, a standard-library ASGI middleware that applies the same two checks to any local dev server.

## Affected and fixed versions

| Advisory | Affected | Fixed |
|---|---|---|
| [GHSA-h4xc-3qfq-jf93](https://github.com/advisories/GHSA-h4xc-3qfq-jf93) / CVE-2026-107295 (content type, High) | `pydantic-ai`, `pydantic-ai-slim` >= 1.34.0, < 1.107.4 and >= 2.0.0b1, < 2.28.0 | 1.107.4 (2026-08-12), 2.28.0 (2026-08-12) |
| [GHSA-q2xc-rrxj-58x9](https://github.com/advisories/GHSA-q2xc-rrxj-58x9) / CVE-2026-107292 (Host header, Moderate) | >= 1.34.0, < 1.107.5 and >= 2.0.0b1, < 2.30.0 | 1.107.5 (2026-08-14), 2.30.0 (2026-08-14) |

First affected release, 1.34.0, was published 2025-12-17. Both advisories were published to the GitHub Advisory Database on 2026-10-08. Fix PRs: [#7382](https://github.com/pydantic/pydantic-ai/pull/7382) / [#7383](https://github.com/pydantic/pydantic-ai/pull/7383) (content type), [#7437](https://github.com/pydantic/pydantic-ai/pull/7437) / [#7438](https://github.com/pydantic/pydantic-ai/pull/7438) (Host).

## Run it

Python 3.13 was used. Each release lives in its own venv:

```bash
for v in 2.27.1 2.28.0 2.30.0; do
  python3 -m venv .venv-$v && .venv-$v/bin/pip install -q "pydantic-ai-slim[web]==$v"
done

.venv-2.27.1/bin/python reproduce.py        # BEFORE: last release before either fix
.venv-2.28.0/bin/python reproduce.py        # first fix only: rebinding still open
.venv-2.30.0/bin/python fix.py              # AFTER: official fix
.venv-2.27.1/bin/python fix.py --guard      # AFTER: LocalOnlyGuard on the vulnerable release
python3 -m unittest discover -s tests -v    # 8 tests
```

Check your own environment or a server you are running (standard library only):

```bash
python3 detect.py
python3 detect.py --probe http://127.0.0.1:7932
```

## What the reproduction does and does not show

- No browser is involved. `scenarios.py` sends each request in-process through Starlette's `TestClient`, with exactly the headers a browser would be *allowed* to send in that situation: a cross-site page can send `text/plain` with no preflight; a rebound page looks same-origin, so it can send JSON, but its `Host` header still carries the attacker's name.
- The model is Pydantic AI's offline `TestModel`, which calls every registered tool. The tool writes a real file to a temporary directory, and "TOOL RAN" means that file exists.
- It does not demonstrate a DNS rebinding server, a malicious page, or anything aimed at a real host.

## Files

- `scenarios.py`: `build_agent()`, `build_app()`, `run_scenarios()`, `print_report()`
- `reproduce.py`: BEFORE output
- `fix.py`: AFTER output (upgrade, or `--guard`)
- `local_guard.py`: `LocalOnlyGuard`, `host_is_local()`, `content_type_is_json()`
- `detect.py`: `check_installed()`, `probe()`
- `tests/test_issue.py`: bug reproduces on 2.27.1 and 2.28.0; fix works on 2.30.0 and with the guard
- `requirements.txt`: the pinned versions used
