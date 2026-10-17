"""Am I affected? Checks a running Ollama server in a few seconds.

    OLLAMA_URL=http://127.0.0.1:11434 python3 detect.py [model]

Reports, for each model (or the one given):
  - the context the server will actually use (loaded: from /api/ps;
    not loaded: the model's num_ctx parameter, else the server default)
  - the context the model was trained for (from /api/show model_info)
and flags models whose working context is far below what they support.

It also prints the server's VRAM-based default, read by loading the model
with a 1-token request and reading /api/ps.
"""

from __future__ import annotations

import sys

from common import get, post


def trained_context(info: dict) -> int | None:
    for key, val in (info.get("model_info") or {}).items():
        if key.endswith(".context_length"):
            return int(val)
    return None


def model_num_ctx(info: dict) -> int | None:
    for line in (info.get("parameters") or "").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "num_ctx":
            return int(parts[1])
    return None


def check(model: str) -> str:
    info = post("/api/show", {"model": model})[1]
    trained = trained_context(info)
    pinned = model_num_ctx(info)
    # Load it the way a /v1 client would (no options), then read what was allocated.
    post("/v1/chat/completions", {"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1})
    want = model if ":" in model else model + ":latest"
    loaded = next((m for m in get("/api/ps")["models"] if m["name"] == want), {})
    working = loaded.get("context_length")
    flag = "AT RISK" if trained and working and working < trained // 4 else "ok"
    return (f"{model:28} working={working} trained={trained} "
            f"modelfile_num_ctx={pinned or '-'}  {flag}")


def main() -> None:
    models = sys.argv[1:] or [m["name"] for m in get("/api/tags")["models"]]
    for m in models:
        print(check(m))
    print("AT RISK = /v1 clients get the working context; longer conversations lose their start silently.")


if __name__ == "__main__":
    main()
