"""Build two toy wheels that mirror the shape of the poisoned LiteLLM release.

NOT LiteLLM, and nothing here steals or sends anything.

    toy-hook 0.0.1  clean: one module, toy_hook/__init__.py
    toy-hook 0.0.2  "hooked": same module, plus two files under
                    toy_hook-0.0.2.data/purelib/ (the same place the real
                    1.107.0 wheels carried cook.pth and cook.py):
                      toy_cook.pth   one line: "import toy_cook"
                      toy_cook.py    appends one line to <venv>/MARKER.log

pip copies .data/purelib/ files to the top of site-packages, so the .pth lands
next to every other package and Python's `site` module runs it at each start.

    python3 toywheel.py [OUT_DIR]     default: ./wheels
"""
import base64
import hashlib
import io
import os
import sys
import zipfile

NAME = "toy_hook"

HOOK_PTH = "import toy_cook\n"
HOOK_PY = '''\
# Toy payload: record that Python started, and how. Nothing else.
import os, sys
with open(os.path.join(sys.prefix, "MARKER.log"), "a") as f:
    f.write("ran: " + " ".join(sys.argv[:2]) + "\\n")
'''


def _record_line(path, data):
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"{path},sha256={digest},{len(data)}"


def build(version, hooked, out_dir):
    files = {
        f"{NAME}/__init__.py": f'__version__ = "{version}"\n'.encode(),
        f"{NAME}-{version}.dist-info/METADATA": (
            f"Metadata-Version: 2.1\nName: toy-hook\nVersion: {version}\n"
            "Summary: toy package for the .pth startup-hook demo\n"
        ).encode(),
        f"{NAME}-{version}.dist-info/WHEEL": (
            "Wheel-Version: 1.0\nGenerator: toywheel\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        ).encode(),
    }
    if hooked:
        files[f"{NAME}-{version}.data/purelib/toy_cook.pth"] = HOOK_PTH.encode()
        files[f"{NAME}-{version}.data/purelib/toy_cook.py"] = HOOK_PY.encode()
    record_path = f"{NAME}-{version}.dist-info/RECORD"
    record = "\n".join(_record_line(p, d) for p, d in files.items()) + f"\n{record_path},,\n"
    files[record_path] = record.encode()

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{NAME}-{version}-py3-none-any.whl")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p, d in files.items():
            info = zipfile.ZipInfo(p, date_time=(2026, 10, 22, 0, 0, 0))
            z.writestr(info, d)
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    return path


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def build_all(out_dir):
    return build("0.0.1", False, out_dir), build("0.0.2", True, out_dir)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "wheels")
    for p in build_all(out):
        print(f"{os.path.basename(p)}  sha256={sha256_file(p)}")
