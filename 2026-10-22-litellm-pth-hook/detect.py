"""List every file that runs code when a Python environment starts, without starting it.

Run it with a DIFFERENT, trusted interpreter and -S, so no .pth file runs while
you look:

    python3 -I -S detect.py PATH [PATH ...]      venvs or site-packages dirs
    python3 -I -S detect.py                      this interpreter's own site dirs
    python3 -I -S detect.py PATH --write-baseline hooks.json
    python3 -I -S detect.py PATH --baseline hooks.json    (CI guard)
    python3 -I -S detect.py --lock requirements.txt uv.lock ...

What it reports per site-packages directory:
  * startup hooks: .pth files with executable "import" lines, sitecustomize.py,
    usercustomize.py, and *.start files (the newer entry-point form);
  * the installed distribution that owns each hook (from dist-info RECORD), or
    "UNOWNED" when no RECORD lists it;
  * known-bad indicators for the LiteLLM releases 1.82.7, 1.82.8 (March 2026)
    and 1.107.0 (21 Oct 2026): file names, SHA-256 hashes, dist-info versions.

Exit status: 0 clean, 1 known-bad indicator found, 2 hook not in the baseline.
Finding nothing does not prove a host is clean (files can be deleted, and a
container may have run the payload already).
"""
import argparse
import glob
import hashlib
import json
import os
import re
import site
import sys

BAD_LITELLM = {"1.82.7", "1.82.8", "1.107.0"}
# SHA-256 of the 1.107.0 payload files, from OSV MAL-2026-2144.
BAD_SHA256 = {
    "7f191632e7320705d154b85204f1ae546b543acbd7e8861229b76f5042b92bdb": "cook.pth (litellm 1.107.0)",
    "9dd0a3926f96a37eb86cf1ee2310d9be93139cc4ebef3ef9e2efe9531390be25": "cook.py (litellm 1.107.0)",
    "34bef04fe88ac9d0aae0475630b1738681d15b94f233ac8aa46eacf5968305fa": "sitecustomize.py (litellm 1.107.0)",
}
BAD_NAMES = {"cook.pth", "cook.py", "litellm_init.pth"}
BAD_TMP = ["/tmp/.pc_once_72129118c59f5636c0bb", "/tmp/remote_code_loader.lock"]
CUSTOMIZE = ("sitecustomize.py", "usercustomize.py")


def _home(p):
    h = os.path.expanduser("~")
    return "~" + p[len(h):] if p.startswith(h) else p


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def site_dirs(path):
    """A venv root, a site-packages dir, or a parent of several venvs."""
    path = os.path.abspath(path)
    if os.path.basename(path) in ("site-packages", "dist-packages"):
        return [path]
    found = glob.glob(os.path.join(path, "lib", "python3*", "site-packages"))
    found += glob.glob(os.path.join(path, "Lib", "site-packages"))  # Windows venv
    return sorted(found)


def owners(sp):
    """Map file name at the top of site-packages -> 'dist version'."""
    own, dists = {}, {}
    for rec in glob.glob(os.path.join(sp, "*.dist-info", "RECORD")):
        info = os.path.basename(os.path.dirname(rec))[: -len(".dist-info")]
        name, _, version = info.partition("-")
        dists[name.lower().replace("_", "-")] = version
        with open(rec, encoding="utf-8", errors="replace") as f:
            for line in f:
                p = line.split(",", 1)[0]
                if "/" not in p:
                    own[p] = f"{name} {version}"
    return own, dists


def executable_lines(pth):
    with open(pth, encoding="utf-8", errors="replace") as f:
        return [l.rstrip("\n") for l in f if re.match(r"import[ \t]", l)]


def scan(sp):
    own, dists = owners(sp)
    hooks, bad = [], []
    for name in sorted(os.listdir(sp)):
        full = os.path.join(sp, name)
        if not os.path.isfile(full):
            continue
        kind = None
        if name.endswith(".pth") and executable_lines(full):
            kind = "pth-import"
        elif name in CUSTOMIZE:
            kind = name[:-3]
        elif name.endswith(".start"):
            kind = "start-file"
        digest = sha256(full) if (kind or name in BAD_NAMES) else None
        if kind:
            hooks.append({"file": name, "kind": kind, "owner": own.get(name, "UNOWNED"), "sha256": digest})
        if digest in BAD_SHA256:
            bad.append(f"{name}: hash matches {BAD_SHA256[digest]}")
        elif name in BAD_NAMES:
            bad.append(f"{name}: file name used by a malicious litellm release")
    if dists.get("litellm") in BAD_LITELLM:
        bad.append(f"litellm {dists['litellm']} installed (malicious release)")
    return hooks, bad


def scan_locks(paths):
    bad = []
    pat = re.compile(r'litellm["\']?\s*(?:==|=|version\s*=\s*)\s*["\']?(1\.82\.7|1\.82\.8|1\.107\.0)\b', re.I)
    loose = re.compile(r'^\s*litellm(\[[^\]]*\])?\s*(>=|~=|$|;|#)', re.I | re.M)
    for p in paths:
        with open(p, encoding="utf-8", errors="replace") as f:
            text = f.read()
        for m in pat.finditer(text):
            bad.append(f"{_home(p)}: pins litellm {m.group(1)} (malicious release)")
        if os.path.basename(p).endswith(".txt") and loose.search(text):
            print(f"  note  {_home(p)}: litellm is not pinned to one version")
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--baseline")
    ap.add_argument("--write-baseline")
    ap.add_argument("--lock", nargs="+", default=[])
    a = ap.parse_args(argv)

    if "site" in sys.modules and not sys.flags.no_site:
        print("  warn  run with -S so this interpreter's own .pth files do not run")
    dirs = []
    for p in a.paths:
        dirs += site_dirs(p)
    if not a.paths and not a.lock:
        dirs = [d for d in site.getsitepackages() + [site.getusersitepackages()] if os.path.isdir(d)]

    all_hooks, all_bad = {}, []
    for sp in dirs:
        hooks, bad = scan(sp)
        print(f"scan  {_home(sp)}")
        for h in hooks:
            print(f"  hook  {h['file']:<26} {h['kind']:<11} owner: {h['owner']}")
        for b in bad:
            print(f"  BAD   {b}")
        all_hooks[sp] = hooks
        all_bad += bad
    all_bad += scan_locks(a.lock)
    for t in BAD_TMP:
        if os.path.exists(t):
            all_bad.append(f"{t} exists (payload marker or loader lock)")
            print(f"  BAD   {t} exists")

    flat = {f"{h['file']} {h['sha256']}" for hs in all_hooks.values() for h in hs}
    if a.write_baseline:
        with open(a.write_baseline, "w") as f:
            json.dump(sorted(flat), f, indent=1)
        print(f"wrote baseline: {len(flat)} hooks")
    new = []
    if a.baseline:
        with open(a.baseline) as f:
            known = set(json.load(f))
        new = sorted(flat - known)
        for n in new:
            print(f"  NEW   {n.split()[0]} is not in the baseline")

    n = sum(len(h) for h in all_hooks.values())
    print(f"result: {n} startup hooks, {len(all_bad)} known-bad, {len(new)} new")
    return 1 if all_bad else 2 if new else 0


if __name__ == "__main__":
    sys.exit(main())
