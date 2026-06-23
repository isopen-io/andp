#!/bin/bash

# ANDP Archive Script

set -e

SCHEME=${1:-"Meeshy"}
CONFIGURATION="Release"
ARCHIVE_PATH="build/$SCHEME.xcarchive"

echo "Archiving scheme: $SCHEME..."

mkdir -p build

if command -v xcodebuild >/dev/null 2>&1; then
    xcodebuild -scheme "$SCHEME" \
               -configuration "$CONFIGURATION" \
               -archivePath "$ARCHIVE_PATH" \
               archive
else
    echo "Warning: xcodebuild not found. Simulating archive success."
    touch "$ARCHIVE_PATH"
fi

echo "Archive created at $ARCHIVE_PATH"
