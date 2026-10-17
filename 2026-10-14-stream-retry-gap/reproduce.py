"""BEFORE: the retry loop wraps the open, so a stream that drops before its first
event is never retried, even with num_retries=2.

    python3 reproduce.py
"""

from pattern import ScriptedUpstream, StreamDropped, consume, retry_open_only


def main() -> None:
    upstream = ScriptedUpstream(["drop", "ok", "ok"])
    print("BEFORE  retry wraps open_stream() only, num_retries=2")
    print("        upstream script: attempt 1 drops before first event, attempt 2+ ok")
    stream = retry_open_only(upstream, num_retries=2)
    print(f"        retry loop returned after {upstream.attempts} attempt(s): it counted a success")
    try:
        text = consume(stream)
        print(f"        caller got: {text!r}")
    except StreamDropped as e:
        print(f"        caller got: StreamDropped({e}) while reading the body")
    print(f"        upstream attempts: {upstream.attempts}  (retries used: {upstream.attempts - 1} of 2)")


if __name__ == "__main__":
    main()
