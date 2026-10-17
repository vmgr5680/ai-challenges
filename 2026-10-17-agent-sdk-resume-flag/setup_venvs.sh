#!/usr/bin/env bash
# Creates the two pinned venvs the real-release runs and tests use (~280 MB each: the wheel bundles the CLI).
set -euo pipefail
cd "$(dirname "$0")"
for v in 0.2.120 0.2.121; do
  python3.12 -m venv ".venv-$v"
  ".venv-$v/bin/pip" install -q "claude-agent-sdk==$v"
done
