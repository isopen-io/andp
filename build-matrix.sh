#!/bin/bash

# ANDP Build Matrix Orchestrator — thin wrapper around `andp build --all`.
#
# The matrix used to be hard-coded here: two schemes, one platform. A project
# declaring nine targets across five platforms had four of them never built.
# The matrix now comes from the `targets:` block of andp.yml, so adding a
# platform is a config change, not a script edit.

set -e

andp_cli() { command -v andp >/dev/null 2>&1 && andp "$@" || python3 -m andp "$@"; }

echo "Starting build matrix execution..."

andp_cli build --all

echo "Build matrix execution complete."
