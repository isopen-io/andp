#!/bin/bash

# ANDP Test Orchestrator — thin wrapper around `andp test`.
#
# The positional signature is preserved (scheme, device, OS version). Booting
# the simulator is no longer done here: `-destination platform=iOS Simulator`
# makes xcodebuild do it, and doing it twice only cost time.
#
# Report generation stays in shell: `andp test` runs the suite and hands back
# the .xcresult path in its envelope; turning it into a report is this script's
# job. The path is read from the envelope rather than guessed — the bundle is
# named after the resolved target, which need not match the scheme.

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

SCHEME=${1:-"Meeshy"}
DEVICE_NAME=${2:-"iPhone 15"}
OS_VERSION=${3:-"17.0"}

andp_cli() { command -v andp >/dev/null 2>&1 && andp "$@" || python3 -m andp "$@"; }

START_TIME=$(date +%s)

echo "Starting test orchestration for scheme: $SCHEME..."

ENVELOPE=$(andp_cli test --json \
    --scheme "$SCHEME" --destination "$DEVICE_NAME" --os "$OS_VERSION") || true

STATUS=$(printf '%s' "$ENVELOPE" | python3 -c \
    'import json,sys; d=json.load(sys.stdin); print("SUCCESS" if d.get("ok") else "FAILED")' \
    2>/dev/null || echo "FAILED")
RESULT_BUNDLE_PATH=$(printf '%s' "$ENVELOPE" | python3 -c \
    'import json,sys; r=(json.load(sys.stdin).get("results") or [{}])[0]; print(r.get("result_bundle") or "")' \
    2>/dev/null || echo "")

# The tool ran in DRY-RUN if xcodebuild is missing — say so, never pretend.
printf '%s' "$ENVELOPE" | grep -q '"dry_run": true' && \
    echo "⚠️  xcodebuild absent — aucun test n'a été exécuté (DRY-RUN)."

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# Repo instrumentation, not a tool responsibility — it stays here.
if [ -x "$ROOT_DIR/infrastructure/analytics-manager.sh" ]; then
    "$ROOT_DIR/infrastructure/analytics-manager.sh" record "test" "$SCHEME" "$DURATION" "$STATUS"
fi

echo "Tests complete in ${DURATION}s ($STATUS)."

if [ -x "./test-report.sh" ] && [ -n "$RESULT_BUNDLE_PATH" ] && [ -e "$RESULT_BUNDLE_PATH" ]; then
    ./test-report.sh "$RESULT_BUNDLE_PATH"
fi

if [ "$STATUS" == "FAILED" ]; then
    echo "Tests FAILED."
    exit 1
fi
