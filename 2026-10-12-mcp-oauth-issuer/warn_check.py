"""What does upgrading change for a pre-provisioned provider that has no issuer=?

Run with each pinned release (see README):  .venv-<ver>/bin/python warn_check.py "<label>"
Nothing is sent: the provider is only constructed, never used.

Functions:
    build()             construct ClientCredentialsOAuthProvider without issuer=
    visible_by_default() does the warning reach stderr under Python's default filters?
    fails_ci_guard()     does `-W "error:Omitting `issuer`"` turn it into a failure?
"""
import inspect
import subprocess
import sys
import warnings

from mcp.client.auth.extensions.client_credentials import ClientCredentialsOAuthProvider

GUARD = "error:Omitting `issuer`"


class MemoryStorage:
    async def get_tokens(self): return None
    async def set_tokens(self, tokens): pass
    async def get_client_info(self): return None
    async def set_client_info(self, info): pass


def build():
    return ClientCredentialsOAuthProvider(
        server_url="https://tools.example.test/mcp", storage=MemoryStorage(),
        client_id="ci-bot", client_secret="not-a-real-secret")


def _run(*flags: str) -> subprocess.CompletedProcess:
    # Imported as a module (not __main__), the way library code runs inside an app.
    return subprocess.run([sys.executable, *flags, "-c", "import warn_check; warn_check.build()"],
                          capture_output=True, text=True)


def visible_by_default() -> bool:
    return "Omitting" in _run().stderr


def fails_ci_guard() -> bool:
    return _run("-W", GUARD).returncode != 0


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "this release"
    accepts = "issuer" in inspect.signature(ClientCredentialsOAuthProvider).parameters
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        build()
    kind = caught[0].category.__name__ if caught else "none"
    print(f"[{label}]")
    print(f"  accepts issuer=        : {accepts}")
    print(f"  warning when omitted   : {kind}")
    print(f"  shown by default       : {visible_by_default() if caught else '-'}")
    print(f"  fails the CI guard     : {fails_ci_guard() if caught else '-'}")
