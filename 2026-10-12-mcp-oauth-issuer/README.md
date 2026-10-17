# 2026-10-12: MCP Python SDK OAuth client could send credentials to a server-chosen authorization server

The official MCP (Model Context Protocol) Python SDK's OAuth client (`mcp.client.auth`) did not validate the authorization server's `issuer` on every discovery path, and did not bind stored or pre-provisioned credentials to the authorization server they belong to. The issuer check only ran when the first discovery step (protected resource metadata) named an authorization server. When that step found nothing and the client took the legacy fallback path, there was no expected value to compare against, so the check was skipped. A malicious or compromised MCP server could therefore steer where the client sent its client secret, authorization code, PKCE (Proof Key for Code Exchange) verifier or signed client assertion. No exploitation has been reported (advisory and Cycode, as of 2026-10-12).

The fixed releases compute the expected issuer up front: the advertised authorization server, or on the legacy path the MCP server's own origin. They also bind stored credentials to an issuer. **Upgrading alone is not the whole fix.** `ClientCredentialsOAuthProvider` and `PrivateKeyJWTOAuthProvider` keep following whatever discovery yields until you pass `issuer=`. On the 1.x line the deprecation warning for a missing `issuer=` is a `DeprecationWarning`, which Python hides by default. Registrations stored before the fix stay unbound until you clear them once. `RFC7523OAuthClientProvider` has no `issuer` option and must be migrated.

## Affected and fixed versions

| Advisory | Affected | Fixed |
|---|---|---|
| [GHSA-qx49-fqc8-xw99](https://github.com/modelcontextprotocol/python-sdk/security/advisories/GHSA-qx49-fqc8-xw99) (High, CVSS 7.5; 6.5 for the interactive `OAuthClientProvider`; no CVE as of 2026-10-12) | `mcp` >= 1.9.1, < 1.30.0 and >= 2.0.0a1, < 2.2.0 | 1.30.0 and 2.2.0 (both published to PyPI 2026-09-07) |

Dates: first affected release 1.9.1 published 2025-05-22. Fixed releases 2026-09-07. Advisory and the [Cycode write-up](https://cycode.com/blog/mcp-python-sdk-oauth-account-takeover/) published 2026-09-28. Last affected releases: 1.29.1 (2026-08-24) and 2.1.1 (2026-08-25). The latest release on 2026-10-12 is 2.3.0.

Not affected (per the advisory): MCP servers built with the SDK, stdio clients, and clients that attach their own tokens or headers.

## What is here

| File | What it does |
|---|---|
| `pattern.py` | A toy, offline model of the bug class: `choose_issuer_conditional()` (pre-fix shape) vs `choose_issuer_fail_closed()` (fixed shape). It is **not** the SDK and sends nothing. |
| `reproduce.py` | BEFORE: the check is skipped when discovery returns nothing. |
| `fix.py` | AFTER: the expected issuer is derived up front, so the check always runs. |
| `detect.py` | Checks the installed `mcp` version against the advisory ranges, and scans your code for providers that still need `issuer=`, migration, or a one-time storage clear. |
| `warn_check.py` | Run in each pinned venv. Shows what upgrading changes for a provider without `issuer=`, whether the warning is visible by default, and whether the CI guard catches it. |
| `samples/` | Two small client files for `detect.py` to scan. They are never run. |
| `tests/` | 9 tests: the bug reproduces, the fix holds, version ranges, the source scan, and three pinned-release checks (skipped if venvs are missing). |
| `OUTPUTS.txt` | The real outputs quoted in the article. |

No exploit is included. The reproduction never builds an OAuth flow, an attacker server or a credential request. It shows the decision logic only, which the advisory and the Cycode write-up already describe publicly.

## Run it

```bash
python3 reproduce.py                          # BEFORE (toy model)
python3 fix.py                                # AFTER (toy model)
python3 detect.py path/to/your/agent          # version + source check (exit 1 = action needed)

# pinned releases for warn_check.py (Python 3.13 was used)
for v in 2.1.1 2.2.0 1.30.0; do python3 -m venv .venv-$v && .venv-$v/bin/pip install -q "mcp==$v"; done
.venv-2.1.1/bin/python  warn_check.py "last affected, Aug 2026"
.venv-2.2.0/bin/python  warn_check.py "fixed, current line, 7 Sep 2026"
.venv-1.30.0/bin/python warn_check.py "fixed, older line, 7 Sep 2026"

python3 -m unittest discover -s tests -v      # 9 tests
```

## The CI guard

Turn the "missing `issuer=`" warning into a failure on both fixed lines by matching the message, not the category:

```bash
python -W "error:Omitting \`issuer\`" -m pytest
```

`-W error::mcp.shared.exceptions.MCPDeprecationWarning` does **not** work. Python resolves `-W` categories at startup, before `mcp` is imported, so it ignores the filter. On the 2.x line `MCPDeprecationWarning` subclasses `UserWarning`, not `DeprecationWarning`.
