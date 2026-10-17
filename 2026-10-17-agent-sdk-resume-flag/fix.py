"""AFTER: the fixed release binds the value to the flag, and an app-side guard rejects bad IDs earlier.

1. `show_fixed_argv()`: the real SDK 0.2.121 emits one token, '--resume=--version',
   and the bundled CLI rejects it as an invalid session ID.
2. `safe_resume_id()`: the guard I'd put in front of any "resume my session"
   endpoint, on every release. The upgrade stops flag injection; it does not
   check that the caller owns the session they asked for.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from common import FIXED, INJECTED, resume_tokens, run_bundled_cli, sdk_argv


def show_fixed_argv() -> None:
    argv = sdk_argv(FIXED, INJECTED)
    toks = resume_tokens(argv)
    print(f"SDK {FIXED}, resume={INJECTED!r}")
    print(f"  argv tokens : {toks}")
    print(f"  standalone {INJECTED!r} token in argv: {INJECTED in argv}")
    code, out = run_bundled_cli(FIXED, [*toks, "-p", "hi"])
    print(f"  bundled CLI : exit {code}, output: {out.splitlines()[0] if out else ''!r}")


# Return a canonical session UUID the caller owns, or raise. `owners` maps session IDs
# your app created (from ResultMessage.session_id) to the user who created them.
# Anything else never reaches the SDK.
def safe_resume_id(raw: str, user: str, owners: Mapping[str, str]) -> str:
    try:
        sid = str(uuid.UUID(raw))
    except (ValueError, AttributeError, TypeError):
        raise ValueError("not a session UUID") from None
    if owners.get(sid) != user:
        raise PermissionError("session not found for this user")
    return sid


def show_guard() -> None:
    mine = "8f8b1c0e-2b1e-4a3f-9c2d-5e6f7a8b9c0d"
    theirs = "550e8400-e29b-41d4-a716-446655440000"
    owners = {mine: "alice", theirs: "bob"}
    print("safe_resume_id() for user 'alice':")
    for raw in [INJECTED, "-r", "release-notes", theirs, mine]:
        try:
            result = f"ok -> {safe_resume_id(raw, 'alice', owners)}"
        except (ValueError, PermissionError) as e:
            result = f"rejected ({e})"
        print(f"  {raw!r:42} {result}")


if __name__ == "__main__":
    show_fixed_argv()
    print()
    show_guard()
