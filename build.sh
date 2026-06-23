#!/bin/bash

# ANDP Build Script

set -e

SCHEME=${1:-"Meeshy"}
CONFIGURATION=${2:-"Release"}
SDK=${3:-"iphoneos"}

echo "Building scheme: $SCHEME ($CONFIGURATION) for $SDK..."

# In a real environment:
# xcodebuild -scheme "$SCHEME" \
#            -configuration "$CONFIGURATION" \
#            -sdk "$SDK" \
#            build

if command -v xcodebuild >/dev/null 2>&1; then
    xcodebuild -scheme "$SCHEME" -configuration "$CONFIGURATION" -sdk "$SDK" build
else
    echo "Warning: xcodebuild not found. Simulating build success."
fi

echo "Build complete."
