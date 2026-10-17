"""Sample client code for detect.py to scan. Not run; the mcp package is not needed."""
from mcp.client.auth import OAuthClientProvider
from mcp.client.auth.extensions.client_credentials import (
    ClientCredentialsOAuthProvider,
    RFC7523OAuthClientProvider,
)

ci_bot = ClientCredentialsOAuthProvider(
    server_url="https://tools.example.test/mcp",
    storage=storage,
    client_id="ci-bot",
    client_secret=secret,
)

legacy = RFC7523OAuthClientProvider(server_url="https://tools.example.test/mcp", storage=storage)

desktop = OAuthClientProvider("https://tools.example.test/mcp", client_metadata, storage, redirect, callback)
