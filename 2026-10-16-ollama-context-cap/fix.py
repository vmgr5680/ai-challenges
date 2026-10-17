"""AFTER: four ways to make the context size stick, or fail loudly.

    OLLAMA_URL=http://127.0.0.1:11434 python3 fix.py
    OLLAMA_URL=<server started with OLLAMA_CONTEXT_LENGTH=16384> python3 fix.py --server-env

A. Native /api/chat with options.num_ctx       (per request)
B. Derived model with PARAMETER num_ctx        (per model; /v1 clients work unchanged)
C. Server-wide OLLAMA_CONTEXT_LENGTH           (per server; run with --server-env)
D. Native /api/chat with truncate: false       (fail closed: 400 instead of silent cut)
"""

from __future__ import annotations

import sys

from common import BIG_CTX, MODEL, build_conversation, post, v1_chat
from guard import ContextTruncated, TruncationGuard

DERIVED = "qwen-ctx16k"


def native(msgs, **body):
    return post("/api/chat", {"model": MODEL, "messages": msgs, "stream": False, **body})


def main() -> None:
    msgs = build_conversation()

    if "--server-env" in sys.argv:
        status, body = v1_chat(msgs)
        print(f"C. /v1, server OLLAMA_CONTEXT_LENGTH : HTTP {status}, "
              f"prompt_tokens={body['usage']['prompt_tokens']}, "
              f"answer={body['choices'][0]['message']['content'].strip()!r}")
        return

    status, body = native(msgs, options={"num_ctx": BIG_CTX, "temperature": 0})
    print(f"A. /api/chat + options.num_ctx      : HTTP {status}, "
          f"prompt_eval_count={body['prompt_eval_count']}, answer={body['message']['content'].strip()!r}")

    status, body = post("/api/create", {"model": DERIVED, "from": MODEL, "parameters": {"num_ctx": BIG_CTX}, "stream": False})
    status, body = v1_chat(msgs, model=DERIVED)
    print(f"B. /v1 + derived model (num_ctx)    : HTTP {status}, "
          f"prompt_tokens={body['usage']['prompt_tokens']}, "
          f"answer={body['choices'][0]['message']['content'].strip()!r}")

    status, body = native(msgs, truncate=False, options={"temperature": 0})
    print(f"D. /api/chat + truncate:false       : HTTP {status}, {body.get('error', body.get('message'))}")

    # E. The guard turns the silent /v1 cut into an exception on the client side.
    guard = TruncationGuard()
    for batches in range(0, 7):
        turn = build_conversation(batches)
        _, body = v1_chat(turn)
        try:
            guard.check(turn, body["usage"]["prompt_tokens"])
        except ContextTruncated as err:
            print(f"E. guard on default /v1, turn {batches}   : ContextTruncated: {err}")
            break
    else:
        print("E. guard on default /v1             : no truncation seen")


if __name__ == "__main__":
    main()
