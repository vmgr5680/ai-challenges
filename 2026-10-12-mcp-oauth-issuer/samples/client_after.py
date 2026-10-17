"""Sample client code for detect.py to scan. Not run; the mcp package is not needed."""
from mcp.client.auth.extensions.client_credentials import ClientCredentialsOAuthProvider

ci_bot = ClientCredentialsOAuthProvider(
    server_url="https://tools.example.test/mcp",
    storage=storage,
    client_id="ci-bot",
    client_secret=secret,
    issuer="https://login.example.test",
)
