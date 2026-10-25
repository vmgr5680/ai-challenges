"""BEFORE: a hooked wheel runs its code on every Python start, without being imported.

1. Build the toy wheels (toywheel.py) into a local folder that acts as the index.
2. Create a fresh venv and run an UNPINNED `pip install toy-hook`, the way an
   unpinned `pip install litellm` picked up 1.107.0 during the 21 Oct window.
3. Start that venv's Python four ways, never importing toy_hook, and count the
   lines the toy payload appends to <venv>/MARKER.log.

    python3 reproduce.py           (builds .demo/, about 10 seconds)
"""
import os
import shutil
import subprocess
import sys

import toywheel

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.join(HERE, ".demo")


def make_venv(path):
    shutil.rmtree(path, ignore_errors=True)
    subprocess.run([sys.executable, "-m", "venv", path], check=True)
    return os.path.join(path, "bin", "python")


def pip_install(py, *args):
    r = subprocess.run([py, "-m", "pip", "install", "-q", "--no-index",
                        "--find-links", os.path.join(DEMO, "wheels"), "--disable-pip-version-check", *args],
                       capture_output=True, text=True)
    return r


def marker_count(venv):
    p = os.path.join(venv, "MARKER.log")
    return sum(1 for _ in open(p)) if os.path.exists(p) else 0


RUNS = [
    ("python -c pass", ["-c", "pass"]),
    ("python -m pip --version", ["-m", "pip", "--version", "--disable-pip-version-check"]),
    ("python -I -c pass", ["-I", "-c", "pass"]),
    ("python -S -c pass", ["-S", "-c", "pass"]),
    ("pip uninstall -y toy-hook", ["-m", "pip", "uninstall", "-y", "toy-hook", "--disable-pip-version-check"]),
]


def run_starts(py, venv):
    results = []
    for label, args in RUNS:
        before = marker_count(venv)
        subprocess.run([py, *args], capture_output=True, check=True)
        results.append((label, marker_count(venv) - before))
    return results


def setup_hooked(name="venv-unpinned"):
    os.makedirs(DEMO, exist_ok=True)
    toywheel.build_all(os.path.join(DEMO, "wheels"))
    venv = os.path.join(DEMO, name)
    py = make_venv(venv)
    pip_install(py, "toy-hook")            # unpinned: newest wins
    return venv, py


def installed_version(py):
    r = subprocess.run([py, "-S", "-c",
                        "import sys,glob,os; sys.path[:0]=glob.glob(os.path.join(sys.prefix,'lib','python3*','site-packages'));"
                        "import importlib.metadata as m; print(m.version('toy-hook'))"],
                       capture_output=True, text=True)
    return r.stdout.strip()


def main():
    venv, py = setup_hooked()
    print(f"unpinned install picked toy-hook {installed_version(py)}")
    print("start command                 hook ran")
    for label, n in run_starts(py, venv):
        print(f"  {label:<28}{'yes' if n else 'no'}")
    print("toy_hook was never imported. The uninstall ran the hook before removing it.")


if __name__ == "__main__":
    main()
