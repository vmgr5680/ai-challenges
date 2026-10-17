"""AFTER: the retry loop reads the first event before returning, so a drop before
any content is retried; a drop after content still surfaces (no silent replay).

    python3 fix.py
"""

from pattern import ScriptedUpstream, StreamDropped, consume, retry_until_first_event


def run(label: str, script: list[str]) -> None:
    upstream = ScriptedUpstream(script)
    try:
        text = consume(retry_until_first_event(upstream, num_retries=2))
        result = f"caller got {text!r}"
    except StreamDropped as e:
        result = f"caller got StreamDropped({e})"
    print(f"        {label:34s} attempts={upstream.attempts}  {result}")


def main() -> None:
    print("AFTER   retry loop holds the first event, num_retries=2")
    run("drop, then ok", ["drop", "ok"])
    run("drop, drop, then ok", ["drop", "drop", "ok"])
    run("drops every time (budget spent)", ["drop", "drop", "drop", "drop"])


if __name__ == "__main__":
    main()
