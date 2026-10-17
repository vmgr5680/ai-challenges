"""BEFORE: Ollama's OpenAI-compatible endpoint drops the start of a long
conversation and still answers 200 OK.

    OLLAMA_URL=http://127.0.0.1:11434 python3 reproduce.py

Runs against a real Ollama server with its default context (no
OLLAMA_CONTEXT_LENGTH, no num_ctx in the Modelfile).

Part 1, one call: the full conversation through /v1, plain and with
options.num_ctx in the body (what OpenAI SDK users send via extra_body).
Part 2, turn by turn: the same conversation grown one log batch at a time,
printing tokens sent vs tokens the server processed (`trace_turns()`).
"""

from __future__ import annotations

from common import BASE_URL, BIG_CTX, MODEL, build_conversation, full_prompt_tokens, get, v1_chat


def one_call() -> None:
    msgs = build_conversation()
    full = full_prompt_tokens(msgs)
    print(f"server   : {BASE_URL}  model: {MODEL}")
    print(f"sent     : {len(msgs)} messages, {full} prompt tokens (measured)")
    for label, extra in [
        ("v1 plain", {}),
        ("v1 + options.num_ctx", {"options": {"num_ctx": BIG_CTX}}),
    ]:
        status, body = v1_chat(msgs, **extra)
        usage = body["usage"]
        answer = body["choices"][0]["message"]["content"].strip()
        reason = body["choices"][0]["finish_reason"]
        print(f"{label:22}: HTTP {status}, prompt_tokens={usage['prompt_tokens']}, "
              f"finish_reason={reason}, answer={answer!r}")
    loaded = [m for m in get("/api/ps")["models"] if m["name"].split(":")[0] == MODEL.split(":")[0]]
    if loaded:
        print(f"api/ps   : {loaded[0]['name']} loaded with context_length={loaded[0].get('context_length')}")


def trace_turns() -> list[tuple[int, int, int, str]]:
    print("\nturn  sent_tokens  processed_tokens  answer")
    rows = []
    for batches in range(0, 7):
        msgs = build_conversation(batches)
        sent = full_prompt_tokens(msgs)
        _, body = v1_chat(msgs)
        got = body["usage"]["prompt_tokens"]
        answer = body["choices"][0]["message"]["content"].strip()
        rows.append((batches, sent, got, answer))
        print(f"{batches:>4}  {sent:>11}  {got:>16}  {answer!r}")
    return rows


if __name__ == "__main__":
    one_call()
    trace_turns()
