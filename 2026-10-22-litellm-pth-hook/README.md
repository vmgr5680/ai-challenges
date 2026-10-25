# LiteLLM poisoned release: a .pth file that runs at every Python start (MAL-2026-2144)

On 21 October 2026 LiteLLM's release pipeline was compromised and `litellm==1.107.0` was published to PyPI (seven wheels, live 11:39:51 to 13:23 UTC) and to Docker Hub / GHCR (`v1.107.0`, `latest`, `main-latest`, `main-stable`, 11:46:56 to 14:20 UTC, GHCR unavailable by 13:51). The wheels were built from the lookalike repository `Berri-AI/litellm`; the official `v1.107.0` git tag is clean. Each wheel carried `cook.pth` (12 bytes: `import cook`), `cook.py` (credential stealer) and `sitecustomize.py` (hourly remote code loader on Linux/macOS) under `litellm-1.107.0.data/purelib/`, which pip installs at the top of site-packages. Python's `site` module executes `.pth` lines that start with `import` at every interpreter start, so the payload ran without `import litellm`, including inside `pip`. March 2026 releases 1.82.7 and 1.82.8 (GHSA-5mg7-485q-xm76) used the same mechanism with `litellm_init.pth`.

Status on 22 October 2026: contained, investigation ongoing; initial access unconfirmed. PyPI's latest is 1.106.2 (uploaded 2026-10-21 10:44 UTC); LiteLLM says pin 1.106.2 or any earlier explicit version. OSV MAL-2026-2144 lists 1.82.7, 1.82.8 and 1.107.0; the GitHub Advisory Database had no entry for 1.107.0 when checked on 22 October (so Dependabot does not alert).

## Affected

| Artifact | Affected | Window (UTC, 21 Oct 2026) |
|---|---|---|
| PyPI `litellm` | 1.107.0 (all 7 wheels); 1.82.7, 1.82.8 (March) | 11:39:51 to 13:23 |
| Docker Hub `litellm/litellm` | `v1.107.0`, `latest`, `main-latest`, `main-stable` (index sha256:1bbcb1443bc9…339e) | 11:46:56 to 14:20 |
| GHCR `berriai/litellm`, `litellm-database`, `litellm-non_root` | same tags | 11:46:56 to 13:51 |

Not affected (per LiteLLM): the private enterprise release; 1.106.2; 1.107.0rc1/rc2 (per OSV).

## Run

```bash
sh check.sh                       # quick host check (file names, dist-info, /tmp markers)
python3 reproduce.py              # BEFORE: toy hooked wheel runs at every start (builds .demo/)
python3 fix.py                    # AFTER: outside cleanup, hash-pinned rebuild, baseline guard, swapped-file refusal
python3 -I -S detect.py PATH ...  # startup-hook inventory of venvs / site-packages, without starting them
python3 -I -S detect.py PATH --write-baseline hooks.json   # then in CI: --baseline hooks.json (exit 2 on a new hook)
python3 -I -S detect.py --lock requirements.txt uv.lock    # pins of the malicious releases
python3 -m unittest discover -s tests -v                   # 12 tests
```

Standard library only (Python 3.10+). `reproduce.py` and `fix.py` install toy wheels from a local folder with `--no-index`; nothing is downloaded. See `OUTPUTS.txt` for a real run.

## Files

- `toywheel.py`: `build()` makes `toy-hook` 0.0.1 (clean) and 0.0.2 (adds `toy_cook.pth` = `import toy_cook` and `toy_cook.py`, whose only action is appending a line to `<venv>/MARKER.log`), in the same `.data/purelib/` layout as the real wheels. NOT LiteLLM.
- `reproduce.py`: unpinned install, then five start commands; counts hook runs.
- `fix.py`: `step1_cleanup()` (delete from a trusted `-S` interpreter), `step2_pinned()` (`==` + `--hash`, `--require-hashes`), `step3_guard()` (baseline diff), `step4_swapped()` (pip refuses a different file under a pinned version).
- `detect.py`: `.pth` import lines, `sitecustomize.py`, `usercustomize.py`, `*.start`; owner from dist-info `RECORD`; known file names, OSV SHA-256 hashes and versions; `/tmp` markers; lock-file pins. Exit 0 / 1 (known bad) / 2 (not in baseline). A clean result is not proof.
- `check.sh`: the three-line host check quoted in the article.

## Indicators (from LiteLLM and OSV)

- Files in site-packages: `cook.pth` (sha256 7f191632…2bdb), `cook.py` (9dd0a392…be25), `sitecustomize.py` (34bef04f…05fa), `litellm-1.107.0.dist-info`, matching `__pycache__` files; March: `litellm_init.pth`.
- `/tmp/.pc_once_72129118c59f5636c0bb` (written after successful exfiltration), `/tmp/remote_code_loader.lock` (loader daemon).
- Exfiltration to `litellm[.]dev/healthcheck`; OSV indicator data also lists `litellm[.]cloud` and `models.litellm[.]cloud`.

## Links

- https://docs.litellm.ai/blog/security-incident-oct-21-2026
- https://github.com/BerriAI/litellm/issues/47826
- https://osv.dev/vulnerability/MAL-2026-2144
- https://github.com/advisories/GHSA-5mg7-485q-xm76
- https://docs.python.org/3/library/site.html
- https://www.stepsecurity.io/blog/litellm-1-107-0-compromised-pypi-backdoored-wheels-credential-stealer
- https://www.wiz.io/blog/litellm-compromised-steals-credentials
