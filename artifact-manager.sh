#!/bin/bash

# ANDP Artifact Manager
# Manages build artifacts (IPA, APP, XCARCHIVE, DMG, PKG)

set -e

ARTIFACTS_DIR="artifacts"
BUILD_DIR="build"

COMMAND=$1

function package_artifacts() {
    echo "Packaging artifacts..."
    mkdir -p "$ARTIFACTS_DIR"

    # Find IPAs
    find "$BUILD_DIR" -name "*.ipa" -exec cp {} "$ARTIFACTS_DIR/" \;

    # Find Apps and zip them
    find "$BUILD_DIR" -name "*.app" -type d -exec zip -r "$ARTIFACTS_DIR/\$(basename {}).zip" {} \;

    # Find Archives
    find "$BUILD_DIR" -name "*.xcarchive" -type d -exec zip -r "$ARTIFACTS_DIR/\$(basename {}).zip" {} \;

    # Generate Mock DMG if on macOS
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # Real hdiutil call would go here
        echo "Simulating DMG creation..."
        touch "$ARTIFACTS_DIR/Meeshy.dmg"
    else
        touch "$ARTIFACTS_DIR/Meeshy.dmg"
    fi

    # Generate Mock PKG
    echo "Simulating PKG creation..."
    touch "$ARTIFACTS_DIR/Meeshy.pkg"

    echo "Artifacts organized in $ARTIFACTS_DIR:"
    ls -R "$ARTIFACTS_DIR"
}

function clean_artifacts() {
    echo "Cleaning artifacts..."
    rm -rf "$ARTIFACTS_DIR"
}

case $COMMAND in
    "package")
        package_artifacts
        ;;
    "clean")
        clean_artifacts
        ;;
    "list")
        if [ -d "$ARTIFACTS_DIR" ]; then
            ls -lh "$ARTIFACTS_DIR"
        else
            echo "No artifacts directory found."
        fi
        ;;
    *)
        echo "Usage: $0 {package|clean|list}"
        exit 1
        ;;
esac
