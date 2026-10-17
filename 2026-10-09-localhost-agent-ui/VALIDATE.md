# Validate the issue and the fixes

Run everything from this folder. The three venvs from the README must exist (`.venv-2.27.1`, `.venv-2.28.0`, `.venv-2.30.0`). Nothing here uses a real model, API key or browser, and nothing leaves `127.0.0.1`.

Last run: 2026-10-17. Every result below matched `OUTPUTS.txt` and the article.

## 1. Confirm each venv has the right release

```bash
for v in 2.27.1 2.28.0 2.30.0; do .venv-$v/bin/pip show pydantic-ai-slim | grep Version; done
```

Expected: `2.27.1`, `2.28.0`, `2.30.0`.

## 2. Reproduce the bug (in-process, no server)

```bash
.venv-2.27.1/bin/python reproduce.py   # before both fixes
.venv-2.28.0/bin/python reproduce.py   # content-type fix only
```

Expected:

```text
2.27.1   B. simple request  HTTP 200  TOOL RAN    C. DNS rebinding  HTTP 200  TOOL RAN
2.28.0   B. simple request  HTTP 415  blocked     C. DNS rebinding  HTTP 200  TOOL RAN
```

"TOOL RAN" means the agent's `write_note` tool really wrote a file to a temp folder. Line A (your own chat tab) should be `200 TOOL RAN` in every run, which shows the fix doesn't break normal use.

## 3. Check the fixes

```bash
.venv-2.30.0/bin/python fix.py           # official fix
.venv-2.27.1/bin/python fix.py --guard   # LocalOnlyGuard on the unfixed release
```

Expected in both: B `HTTP 415 blocked`, C `HTTP 421 blocked`, A still `200 TOOL RAN`.

## 4. Run the tests

```bash
python3 -m unittest discover -s tests -v
```

Expected: `Ran 8 tests ... OK`. Each test runs inside the venv for its release, so a missing venv shows up as a skipped test, not a pass.

## 5. Check installed versions

```bash
.venv-2.27.1/bin/python detect.py   # AFFECTED (web pages can POST to it, DNS rebinding)
.venv-2.28.0/bin/python detect.py   # AFFECTED (DNS rebinding)
.venv-2.30.0/bin/python detect.py   # not affected
```

Plain `python3 detect.py` checks your system Python, which normally says "pydantic-ai is not installed".

## 6. Live check against a real server (the article's curl commands)

Terminal 1: start the real chat UI on `127.0.0.1:7932` with the offline test agent. Use `2.27.1` first, then repeat with `2.30.0`:

```bash
.venv-2.27.1/bin/python -c "
import tempfile, pathlib, uvicorn
from scenarios import build_agent, build_app
uvicorn.run(build_app(build_agent(pathlib.Path(tempfile.mkdtemp()))), host='127.0.0.1', port=7932)"
```

Terminal 2: send the two checks from the article, then the probe:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: rebind-check.invalid' http://127.0.0.1:7932/api/health
curl -s -o /dev/null -w '%{http_code}\n' -X POST -H 'Content-Type: text/plain' --data '{}' http://127.0.0.1:7932/api/chat
python3 detect.py --probe http://127.0.0.1:7932
```

Expected:

```text
2.27.1   200, 500   probe: EXPOSED to DNS rebinding / EXPOSED: parsed a text/plain body
2.30.0   421, 415   probe: ok, refused / ok, refused
```

On `2.27.1`, terminal 1 prints a traceback for the second request ending in `validate_json ... ValidationError`. **That traceback is the evidence:** the server parsed a `text/plain` body as JSON. The `{}` body isn't a valid chat message, so it fails before any agent run starts. A real attack would send a valid message instead. Stop the server with Ctrl+C before starting the next release on the same port.

## If a result differs

- Wrong version in step 1: recreate that venv with the README's install loop.
- Step 6 says "connection refused": the server hasn't started yet, or another process is using port 7932 (`lsof -i :7932`).
- Any other mismatch: compare with `OUTPUTS.txt` and re-check the advisory pages, since a new release or advisory may have changed the behaviour.
