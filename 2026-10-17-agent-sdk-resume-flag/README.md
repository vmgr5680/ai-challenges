# Claude Agent SDK: a session ID that becomes a CLI flag (CVE-2026-96620, GHSA-h4mw-j7qp-8mwm)

The Claude Agent SDK runs the Claude Code CLI as a subprocess. Before the fix, the Python SDK passed the `resume` option as two argv tokens, `["--resume", value]`. The CLI declares `-r, --resume [value]` with an *optional* value, so when the value starts with `-` the parser does not bind it to `--resume`; it reads it as a separate flag. Any application that forwards an untrusted session ID (a "resume my chat" endpoint, a queue message, a URL parameter) let the caller add CLI flags. The advisory describes the worst case: a flag that loads an MCP server configuration whose stdio server is a command, run at CLI startup outside the SDK's permission controls. No shell is involved; it is argument injection (CWE-88).

The fix passes `--resume=<value>` and `--session-id=<value>` as single tokens, so the CLI binds the value and rejects a dash-leading one as an invalid session ID. Upgrading does not check *whose* session a caller asks for: the CLI accepts any session ID or session title it can find in its config directory, so an app that resumes sessions for several users still needs an ownership check (`safe_resume_id()` in `fix.py`).

## Versions and dates

| | Python `claude-agent-sdk` | TypeScript `@anthropic-ai/claude-agent-sdk` |
|---|---|---|
| Affected | all releases `< 0.2.121` (0.0.23 … 0.2.120) | releases `< 0.3.208` (per the fix PR; no advisory) |
| Fixed | 0.2.121, published to PyPI 2026-07-17 (PR #1123, commit 347a1cb) | 0.3.208, published to npm 2026-07-13 |
| Follow-up | 0.2.124 (2026-07-20): dash-leading `extra_args` values bound with `=`; `resume`/`session_id` with cmd.exe metacharacters rejected on Windows; `.bat`/`.cmd` CLI spawning refused on Windows (PR #1127) | — |
| Advisory | repository advisory published 2026-09-12; GitHub-reviewed into the global database, CVE assigned and OSV record created 2026-10-16 | none in OSV as of 2026-10-17 |
| Severity | Critical, CVSS 4.0 9.2 (`AV:N/AC:L/AT:P/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N`) | — |

Measured here: SDK 0.2.120 bundles CLI 2.1.211; SDK 0.2.121 bundles CLI 2.1.212. Latest at the time of writing: Python 0.2.168, TypeScript 0.3.302.

## Run

```bash
./setup_venvs.sh                 # two pinned venvs, ~280 MB each (the wheel bundles the CLI)
python3 reproduce.py             # BEFORE: 0.2.120 emits ['--resume', '--version']; the bundled CLI prints its version
python3 fix.py                   # AFTER: 0.2.121 emits ['--resume=--version']; the CLI rejects it; then the ownership guard
python3 detect.py /path/to/your/project
python3 -m unittest discover -s tests -v
```

Real outputs are in `OUTPUTS.txt`.

Safety: the reproduction never calls a model. `sdk_argv()` only calls the SDK's `_build_command()`. The bundled CLI runs with an empty temporary `HOME` and an invalid API key, and the injected value is `--version`, the same harmless flag the maintainers used in the fix PR. No MCP configuration or command payload is included.

## Files

- `common.py`: `sdk_argv()` (the real SDK's argv for a resume value, built inside a pinned venv), `run_bundled_cli()` (isolated CLI run).
- `reproduce.py`: `show_argv()`, `show_cli_parse()` (BEFORE).
- `fix.py`: `show_fixed_argv()` (AFTER), `safe_resume_id()` (UUID + ownership guard), `show_guard()`.
- `detect.py`: finds affected Python and npm installs and the call sites that pass a non-literal `resume` / `session_id` / `extra_args` (`resume` / `sessionId` / `extraArgs` in TypeScript).
- `examples/`: the risky pattern in Python and TypeScript (sketches, not run).
- `tests/`: 11 tests (5 against the real releases, skipped without the venvs).

## Options compared

| Option | Fixes | Effort | Trade-off |
|---|---|---|---|
| Upgrade the SDK (latest) | flag injection via `resume`/`session_id`; `extra_args` from 0.2.124 | one line | does not check session ownership; TypeScript users get no scanner alert |
| `safe_resume_id()`: canonical UUID + owner lookup | flag injection on any release, cross-user resume, resume-by-title | ~15 lines + a session table | you must record which user created each session |
| Opaque handle: give clients your own ID, map to the SDK session server-side | same as above, and the SDK session ID never leaves the server | a lookup table | one more table to keep |
| Separate CLI config directory per tenant | limits what a resumed ID can reach | deployment change | does not stop flag injection on old releases |
| `--` end-of-options marker | nothing here: the value belongs to an option, not a positional argument | — | does not apply |

## Links

- Advisory: https://github.com/anthropics/claude-agent-sdk-python/security/advisories/GHSA-h4mw-j7qp-8mwm
- OSV: https://osv.dev/vulnerability/GHSA-h4mw-j7qp-8mwm
- Fix PR #1123: https://github.com/anthropics/claude-agent-sdk-python/pull/1123
- Changelog (0.2.121, 0.2.124): https://github.com/anthropics/claude-agent-sdk-python/blob/main/CHANGELOG.md
- TypeScript changelog (0.3.208): https://github.com/anthropics/claude-agent-sdk-typescript/blob/main/CHANGELOG.md
- Same bug class in agents: Trail of Bits, "Prompt injection to RCE in AI agents" (2025-10-22): https://blog.trailofbits.com/2025/10/22/prompt-injection-to-rce-in-ai-agents/
