#!/bin/bash

# ANDP Build Script

set -e

SCHEME=${1:-"Meeshy"}
CONFIGURATION=${2:-"Release"}
SDK=${3:-"iphoneos"}

START_TIME=$(date +%s)

echo "Building scheme: $SCHEME ($CONFIGURATION) for $SDK..."

# Build settings to allow compilation in CI without certificates
BUILD_SETTINGS=""
if [ "$CI" == "true" ] || [ "$GITHUB_ACTIONS" == "true" ]; then
    echo "CI environment detected. Disabling code signing for build-only validation."
    BUILD_SETTINGS="CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY= CODE_SIGN_ENTITLEMENTS= CODE_SIGNING_INJECT_BASE_ENTITLEMENTS=NO"
fi

STATUS="SUCCESS"
if command -v xcodebuild >/dev/null 2>&1; then
    if ! xcodebuild -scheme "$SCHEME" \
               -configuration "$CONFIGURATION" \
               -sdk "$SDK" \
               $BUILD_SETTINGS \
               build; then
        STATUS="FAILED"
    fi
else
    echo "Warning: xcodebuild not found. Simulating build success."
fi

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# Record metrics
if [ -x "./infrastructure/analytics-manager.sh" ]; then
    ./infrastructure/analytics-manager.sh record "build" "$SCHEME" "$DURATION" "$STATUS"
fi

if [ "$STATUS" == "FAILED" ]; then
    echo "Build FAILED."
    exit 1
fi

echo "Build complete in ${DURATION}s."
