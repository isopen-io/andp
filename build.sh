#!/bin/bash

# ANDP Build Script — thin wrapper around `andp build`.
#
# The positional signature is preserved: .github/workflows/andp-release.yml
# calls `./build.sh "$SCHEME" Release iphoneos` and must keep working.
# Everything else — target resolution, destinations, logs, structured
# failures — lives in `andp build`.

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

SCHEME=${1:-"Meeshy"}
CONFIGURATION=${2:-"Release"}
SDK=${3:-"iphoneos"}

andp_cli() { command -v andp >/dev/null 2>&1 && andp "$@" || python3 -m andp "$@"; }

# -sdk and -destination overlap; -destination is the form Xcode recommends, so
# the legacy third argument is translated here rather than exposed in the CLI.
case "$SDK" in
    iphoneos|appletvos|watchos|xros)  DESTINATION="generic" ;;
    *simulator)                      DESTINATION="" ;;      # let the target decide
    *)                               DESTINATION="generic" ;;
esac

START_TIME=$(date +%s)

echo "Building scheme: $SCHEME ($CONFIGURATION) for $SDK..."

ARGS=(build --scheme "$SCHEME" --configuration "$CONFIGURATION")
[ -n "$DESTINATION" ] && ARGS+=(--destination "$DESTINATION")

STATUS="SUCCESS"
andp_cli "${ARGS[@]}" || STATUS="FAILED"

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# Repo instrumentation, not a tool responsibility — it stays here.
if [ -x "$ROOT_DIR/infrastructure/analytics-manager.sh" ]; then
    "$ROOT_DIR/infrastructure/analytics-manager.sh" record "build" "$SCHEME" "$DURATION" "$STATUS"
fi

if [ "$STATUS" == "FAILED" ]; then
    echo "Build FAILED."
    exit 1
fi

echo "Build complete in ${DURATION}s."
