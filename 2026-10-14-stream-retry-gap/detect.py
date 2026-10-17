"""Am I affected? A one-minute check for the LiteLLM stream-retry gap.

    python3 detect.py [path ...]

For each path (a LiteLLM proxy config, a Python file, or a directory) it reports:

- the installed litellm version (if any) and what the measured runs say about it;
- whether a config sets num_retries (the setting that does NOT cover a stream
  that drops before its first event) and whether it has fallbacks (which do
  rescue /chat/completions and /v1/messages, not Gemini streamGenerateContent);
- streaming call sites in Python code that are not wrapped in a first-chunk guard.

Exit code 1 means "at risk: act", 0 means "nothing found". Stdlib only.
"""

from __future__ import annotations

import re
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

# Measured with litellm_probe.py / proxy_probe.py on 2026-10-14 (see OUTPUTS.txt).
MEASURED = {
    "1.104.0": "no route retries a pre-first-event drop",
    "1.105.1": "no route retries a pre-first-event drop (latest stable on 2026-10-14)",
    "1.106.0rc2": "/v1/messages retries; /chat/completions and streamGenerateContent do not",
}

STREAM_CALL = re.compile(
    r"(stream\s*=\s*True|agenerate_content_stream|streamGenerateContent|aanthropic_messages\([^)]*stream)",
)
GUARD = re.compile(r"first_chunk_retry|retry_until_first_event")


def _scan_config(text: str) -> list[str]:
    notes = []
    has_retries = re.search(r"^\s*num_retries\s*:\s*[1-9]", text, re.M)
    has_fallbacks = re.search(r"^\s*fallbacks\s*:", text, re.M)
    uses_gemini = re.search(r"model\s*:\s*(gemini|vertex_ai)/", text)
    if has_retries and not has_fallbacks:
        notes.append("num_retries is set but there are no fallbacks: a stream dropped before "
                     "its first event gets ONE upstream attempt")
    if has_fallbacks and uses_gemini:
        notes.append("fallbacks are set, but they did not rescue Gemini streamGenerateContent in "
                     "the measured runs (LiteLLM #45457 is open)")
    return notes


def _scan_python(text: str) -> list[str]:
    notes = []
    if GUARD.search(text):
        return notes
    for n, line in enumerate(text.splitlines(), 1):
        if STREAM_CALL.search(line):
            notes.append(f"line {n}: streaming call with no first-chunk retry: {line.strip()[:80]}")
    return notes


def scan(paths: list[Path]) -> list[str]:
    findings = []
    for root in paths:
        files = [root] if root.is_file() else sorted(
            p for p in root.rglob("*") if p.suffix in {".py", ".yaml", ".yml"} and ".venv" not in p.parts)
        for f in files:
            text = f.read_text(errors="replace")
            notes = _scan_config(text) if f.suffix in {".yaml", ".yml"} else _scan_python(text)
            findings += [f"{f}: {n}" for n in notes]
    return findings


def main(argv: list[str]) -> int:
    at_risk = False
    try:
        v = version("litellm")
        status = MEASURED.get(v, "not measured here; run litellm_probe.py in this environment")
        print(f"litellm {v} installed: {status}")
        at_risk = True  # no release measured here retries all three routes yet
    except PackageNotFoundError:
        print("litellm not installed in this interpreter (scanning files only)")
    findings = scan([Path(a) for a in argv]) if argv else []
    for f in findings:
        print("  AT RISK  " + f)
    if not findings and argv:
        print("  no unguarded streaming calls or retry-only configs found")
    return 1 if (findings or at_risk) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
