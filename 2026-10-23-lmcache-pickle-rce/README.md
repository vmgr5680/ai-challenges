# LMCache multiprocess-transport RCE (CVE-2026-105192)

LMCache is a KV-cache layer used to speed up LLM serving (most commonly in
front of vLLM). Its **multiprocess / distributed mode** opens an
**unauthenticated ZeroMQ ROUTER** so sibling processes can register and share
KV-cache blocks. Device IPC descriptors arriving on that socket were decoded
with `pickle.loads` *before* any handler ran, so a single crafted message to
the transport port (default 5555) ran arbitrary code as the LMCache process
user. Official container images ran that process as root. CVSS 3.1 **9.8**
(CWE-306, missing authentication).

The transport binds to **localhost by default**; it is reachable off-box only
when the operator sets a routable address with `--host` (what multi-node
setups do). The project's example Kubernetes deployment bound all interfaces,
so deployments based on it should be treated as exposed.

**Affected:** `>= 0.3.9, < 0.5.6` (including the `0.5.6` release candidates).
**Fixed:** `0.5.6` (PyPI upload 15 Oct 2026). The fix replaces pickle with
versioned, typed MessagePack descriptors validated against a fixed allowlist,
binds the example deployment to localhost (PR #5684), and ships non-root images
(PR #5685). **The wire format changed: upgrade all workers and servers
together.** RPC authentication is planned for a later release.

**Timeline:** JFrog (Yuval Moravchick) disclosed publicly 7 Oct 2026
(JFSA-2026-001694382); fix merged to `dev` 12 Oct; `0.5.6` published 15 Oct;
GitHub reviewed GHSA-w5f2-9q9c-ff4h into its global advisory database 16 Oct
(when Dependabot alerts begin). OSV carries it; it has a CVE.

## Files

- `detect.py` - read-only exposure check: is an affected release installed,
  and is anything listening on a routable address on the transport port?
  Sends nothing, connects to nothing.
- `reproduce.py` - a **safe, self-contained toy** showing the *class* of bug:
  a server that unpickles client bytes runs whatever the client sent, before
  its type check. The payload is benign (it writes a marker file). This is
  **not** an LMCache exploit and does not touch any network service.
- `fix.py` - the fix pattern: typed, allowlisted decoding that never calls
  pickle, so hostile messages are refused before any object is built.
- `tests/test_all.py` - proves the toy side effect runs, proves the fix
  refuses it, and checks the version-range logic (including rc builds).

## Run

```bash
python3 -I reproduce.py        # BEFORE: side effect runs during decode
python3 -I fix.py              # AFTER:  hostile message refused
python3 -I detect.py           # check this environment (port 5555)

python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python3 -I -m pytest -q        # 6 passed
```

## Responsible-use note

This folder deliberately contains **no working exploit**. The real transport
frame and the public proof of concept are in the advisory
(GHSA-w5f2-9q9c-ff4h / the JFrog write-up); reproduce only against a sandbox
you own. Lead with detection and the upgrade.

## Fix / mitigate

1. Upgrade to the fixed release (`0.5.6`); upgrade all peers together.
2. Keep the transport on localhost or a trusted cluster network; never bind a
   routable address unless you must, and firewall port 5555 if you do.
3. Run LMCache as a non-root user.
4. If the port was ever reachable from an untrusted network, treat the host as
   potentially compromised: exploitation happens before the message is
   processed, so a rejected request in the logs does not prove it failed.
