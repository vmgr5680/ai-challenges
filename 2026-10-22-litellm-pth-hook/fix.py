"""AFTER: clean up from outside, rebuild pinned with hashes, and guard the startup hooks.

1. Clean up the hooked venv WITHOUT starting its Python: a trusted interpreter
   with -S finds the hook and deletes it, then the venv starts without running it.
2. Rebuild from a hash-pinned requirements file (exact version + --require-hashes).
3. Record a baseline of startup hooks; a later dependency change that adds one
   fails the check (exit 2), the CI guard.
4. Same version, different file: pip --require-hashes refuses a swapped artifact.

    python3 fix.py
"""
import os
import shutil
import subprocess
import sys

import detect
import reproduce as r
import toywheel

WHEELS = os.path.join(r.DEMO, "wheels")


def detect_quiet(*argv):
    """Run detect.py as a trusted outside interpreter with -I -S, return (exit, stdout)."""
    p = subprocess.run([sys.executable, "-I", "-S", os.path.join(r.HERE, "detect.py"), *argv],
                       capture_output=True, text=True)
    return p.returncode, p.stdout


def step1_cleanup():
    venv, py = r.setup_hooked()
    hooks = []
    for sp in detect.site_dirs(venv):
        found, _ = detect.scan(sp)
        for h in found:
            hooks.append(h["file"])
            os.remove(os.path.join(sp, h["file"]))
            mod = os.path.join(sp, h["file"].replace(".pth", ".py"))
            if os.path.exists(mod):
                os.remove(mod)
    before = r.marker_count(venv)
    subprocess.run([py, "-c", "pass"], check=True)
    print(f"1. removed from outside: {', '.join(hooks)}; next start ran the hook: "
          f"{'yes' if r.marker_count(venv) > before else 'no'}")


def write_reqs(path, version, wheel):
    with open(path, "w") as f:
        f.write(f"toy-hook=={version} --hash=sha256:{toywheel.sha256_file(wheel)}\n")


def step2_pinned():
    clean, _ = toywheel.build_all(WHEELS)
    reqs = os.path.join(r.DEMO, "requirements.lock.txt")
    write_reqs(reqs, "0.0.1", clean)
    venv = os.path.join(r.DEMO, "venv-pinned")
    py = r.make_venv(venv)
    p = r.pip_install(py, "--require-hashes", "-r", reqs)
    assert p.returncode == 0, p.stderr
    subprocess.run([py, "-c", "pass"], check=True)
    print(f"2. pinned + hashed install: toy-hook {r.installed_version(py)}, "
          f"hook ran: {'yes' if r.marker_count(venv) else 'no'}")
    return venv, py, reqs


def step3_guard(venv, py):
    base = os.path.join(r.DEMO, "startup-hooks.json")
    code, out = detect_quiet(venv, "--write-baseline", base)
    print(f"3. baseline written ({out.strip().splitlines()[-2]})")
    r.pip_install(py, "--upgrade", "toy-hook")      # an unpinned bump, as in a dependency update
    code, out = detect_quiet(venv, "--baseline", base)
    for line in out.splitlines():
        if line.strip().startswith(("NEW", "result")):
            print(f"   {line.strip()}")
    print(f"   detect.py exit status: {code}")
    return code


def step4_swapped(reqs):
    # Rebuild a hooked wheel that claims to be 0.0.1 and put it where the clean one was.
    swap_dir = os.path.join(r.DEMO, "wheels-swapped")
    shutil.rmtree(swap_dir, ignore_errors=True)
    toywheel.build("0.0.1", True, swap_dir)
    venv = os.path.join(r.DEMO, "venv-swapped")
    py = r.make_venv(venv)
    p = subprocess.run([py, "-m", "pip", "install", "-q", "--no-index", "--find-links", swap_dir,
                        "--disable-pip-version-check", "--require-hashes", "-r", reqs],
                       capture_output=True, text=True)
    first = next((l for l in p.stderr.splitlines() if "HASHES" in l), p.stderr.strip()[:120])
    print(f"4. same version, swapped file: pip exit {p.returncode}: {first.strip()}")
    return p.returncode


def main():
    step1_cleanup()
    venv, py, reqs = step2_pinned()
    step3_guard(venv, py)
    step4_swapped(reqs)


if __name__ == "__main__":
    main()
