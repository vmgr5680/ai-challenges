"""BEFORE: on the last affected release, a session ID that starts with '-' becomes a CLI flag.

1. `show_argv()` asks the real SDK (0.2.120) to build its CLI command for
   resume="--version" and prints the resume tokens.
2. `show_cli_parse()` hands those two tokens to the CLI bundled in the same
   wheel. The CLI declares `--resume [value]` with an optional value, so it does
   not bind '--version' as the session ID; it runs --version instead.

'--version' is harmless on purpose. The advisory (GHSA-h4mw-j7qp-8mwm) explains
that an attacker would pick a flag that loads an MCP server config instead.
"""

from common import AFFECTED, INJECTED, resume_tokens, run_bundled_cli, sdk_argv


def show_argv() -> list[str]:
    argv = sdk_argv(AFFECTED, INJECTED)
    toks = resume_tokens(argv)
    print(f"SDK {AFFECTED}, resume={INJECTED!r}")
    print(f"  argv tokens : {toks}")
    print(f"  standalone {INJECTED!r} token in argv: {INJECTED in argv}")
    return toks


def show_cli_parse(toks: list[str]) -> None:
    code, out = run_bundled_cli(AFFECTED, [*toks, "-p", "hi"])
    print(f"  bundled CLI : exit {code}, output: {out.splitlines()[0] if out else ''!r}")
    print("  -> the 'session ID' was parsed as a flag; no session was resumed")


if __name__ == "__main__":
    show_cli_parse(show_argv())
