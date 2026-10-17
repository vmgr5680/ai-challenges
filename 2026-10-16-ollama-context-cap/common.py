"""Shared helpers: the test conversation and a tiny stdlib HTTP client.

The conversation is the running example from the article: a release
assistant gets its task (codename BLUE-HERON, "never deploy on Fridays")
in the first user turn, then six batches of pasted logs, then a question
that only the first turn can answer.

Environment:
    OLLAMA_URL    base URL of the Ollama server (default http://127.0.0.1:11434)
    OLLAMA_MODEL  model tag (default qwen2.5:1.5b)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BASE_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b")
CODENAME = "BLUE-HERON"
BIG_CTX = 16384


def log_batch(k: int, lines: int = 25) -> str:
    """Deterministic fake service logs, roughly 35 tokens per line."""
    rows = (
        f"line {i}: service=checkout status=200 latency_ms={(i * 37 + k) % 500} "
        f"region=eu-west-1 trace={(i + 1) * 7919 + k:08x}"
        for i in range(lines)
    )
    return f"Log batch {k}:\n" + "\n".join(rows)


def build_conversation(batches: int = 6) -> list[dict]:
    msgs = [
        {"role": "system", "content": "You are a release assistant. Answer briefly."},
        {"role": "user", "content": (
            f"Task: the release codename is {CODENAME}. Never deploy on Fridays. "
            "I will paste logs next; just acknowledge each batch."
        )},
        {"role": "assistant", "content": "Understood."},
    ]
    for k in range(batches):
        msgs.append({"role": "user", "content": log_batch(k)})
        msgs.append({"role": "assistant", "content": f"Received batch {k}."})
    msgs.append({"role": "user", "content": "What is the release codename? Reply with the codename only."})
    return msgs


def post(path: str, body: dict, base_url: str | None = None, timeout: int = 600) -> tuple[int, dict]:
    url = (base_url or BASE_URL) + path
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as err:
        raw = err.read().decode()
        err.close()
        try:
            return err.code, json.loads(raw)
        except json.JSONDecodeError:
            return err.code, {"error": raw}


def get(path: str, base_url: str | None = None) -> dict:
    with urllib.request.urlopen((base_url or BASE_URL) + path, timeout=30) as resp:
        return json.load(resp)


def full_prompt_tokens(msgs: list[dict], model: str = MODEL, base_url: str | None = None) -> int:
    """Size of the whole conversation, measured by the server with a big window."""
    status, body = post("/api/chat", {
        "model": model, "messages": msgs, "stream": False,
        "options": {"num_ctx": BIG_CTX, "num_predict": 1, "temperature": 0},
    }, base_url)
    if status != 200:
        raise RuntimeError(body)
    return body["prompt_eval_count"]


def v1_chat(msgs: list[dict], model: str = MODEL, base_url: str | None = None, **extra) -> tuple[int, dict]:
    """OpenAI-compatible call. `extra` is merged into the JSON body, the same
    thing the OpenAI SDK's extra_body does."""
    return post("/v1/chat/completions", {"model": model, "messages": msgs, "temperature": 0, **extra}, base_url)
