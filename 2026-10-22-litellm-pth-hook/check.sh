#!/bin/sh
# Quick host check for the poisoned LiteLLM releases (1.107.0 on 21 Oct 2026; 1.82.7 / 1.82.8 in March 2026).
# From a clean shell. Do not run python or pip from the suspect environment.
find / \( -name cook.pth -o -name litellm_init.pth \) -path '*-packages*' 2>/dev/null
find / -type d -name 'litellm-1.107.0.dist-info' 2>/dev/null
ls -la /tmp/.pc_once_72129118c59f5636c0bb /tmp/remote_code_loader.lock 2>/dev/null
