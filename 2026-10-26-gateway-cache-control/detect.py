"""Is prompt caching surviving your gateway? Two checks, standard library only.

1. Live probe: send the same cache-marked request twice through the gateway.
   The second response must report cache_read_input_tokens > 0.

     python3 detect.py probe --url https://your-gateway/v1/messages \
         --header "x-api-key: $KEY" --header "anthropic-version: 2023-06-01" \
         --model <a Claude model your gateway routes>

   It sends about 6,000 words of filler twice, so it costs a few cents of input
   tokens. Use --format openai for an OpenAI-compatible /chat/completions route
   (the marker goes on the system content block, which is what most gateways
   document for Claude).

2. Usage-log scan: point it at a JSONL file of response usage objects (one per
   line, as your gateway or tracing tool exports them).

     python3 detect.py scan usage.jsonl

Exit code 0 = caching seen, 1 = no cache reads (likely dropped), 2 = error.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request

FILLER = " ".join(f"Reference line {i}: this text exists only to pass the cache minimum." for i in range(600))


def _usage_reads(usage: dict) -> tuple[int, int]:
    """(cache reads, cache writes) from an Anthropic or OpenAI-shaped usage object."""
    reads = usage.get("cache_read_input_tokens") or 0
    reads = reads or (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
    writes = usage.get("cache_creation_input_tokens") or 0
    return int(reads), int(writes)


def build_body(fmt: str, model: str) -> dict:
    block = {"type": "text", "text": FILLER, "cache_control": {"type": "ephemeral"}}
    if fmt == "openai":
        return {"model": model, "max_tokens": 1,
                "messages": [{"role": "system", "content": [block]},
                             {"role": "user", "content": "Reply with the word ok."}]}
    return {"model": model, "max_tokens": 1, "system": [block],
            "messages": [{"role": "user", "content": "Reply with the word ok."}]}


def post(url: str, headers: dict, body: dict) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode(),
                                 {"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def probe(url: str, headers: dict, model: str, fmt: str = "anthropic") -> int:
    body = build_body(fmt, model)
    first = _usage_reads(post(url, headers, body)["usage"])
    second = _usage_reads(post(url, headers, body)["usage"])
    print(f"call 1: cache_read={first[0]} cache_write={first[1]}")
    print(f"call 2: cache_read={second[0]} cache_write={second[1]}")
    if second[0] > 0:
        print("OK: the second call was served from the prompt cache")
        return 0
    print("PROBLEM: identical second call read nothing from the cache; "
          "the gateway is probably dropping cache_control")
    return 1


def scan(path: str, min_prompt: int = 1024) -> int:
    n = big = reads = writes = 0
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            u = json.loads(line)
            u = u.get("usage", u)
            n += 1
            r, w = _usage_reads(u)
            reads, writes = reads + r, writes + w
            prompt = (u.get("input_tokens") or u.get("prompt_tokens") or 0) + r + w
            big += prompt >= min_prompt
    print(f"{n} requests, {big} with prompts >= {min_prompt} tokens, "
          f"cache_read total={reads}, cache_write total={writes}")
    if big and reads == 0:
        print("PROBLEM: large prompts but zero cache reads; check whether cache_control reaches the provider")
        return 1
    print("OK: cache reads present" if reads else "no large prompts; nothing to judge")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe")
    p.add_argument("--url", required=True)
    p.add_argument("--model", default="claude-example")
    p.add_argument("--format", choices=["anthropic", "openai"], default="anthropic")
    p.add_argument("--header", action="append", default=[])
    s = sub.add_parser("scan")
    s.add_argument("path")
    s.add_argument("--min-prompt", type=int, default=1024)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "probe":
            headers = dict(h.split(":", 1) for h in a.header)
            return probe(a.url, {k.strip(): v.strip() for k, v in headers.items()}, a.model, a.format)
        return scan(a.path, a.min_prompt)
    except Exception as e:  # noqa: BLE001
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
