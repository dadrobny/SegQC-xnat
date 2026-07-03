#!/usr/bin/env bash
# Thin wrapper → the usage-gated AIDE loop supervisor. Config: loop.local.toml.
exec python "$(dirname "$0")/loop.py" "$@"
