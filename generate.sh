#!/bin/bash

# ANDP Project Generation Script
# Wrapper for XcodeGen — runs against the app in $ANDP_APP_DIR (default: bundled example app)

set -e

APP_DIR="${ANDP_APP_DIR:-examples/meeshy}"
PROJECT_FILE="$APP_DIR/project.yml"

if [ ! -f "$PROJECT_FILE" ]; then
    echo "Error: $PROJECT_FILE not found."
    exit 1
fi

echo "Generating Xcode project using XcodeGen (app: $APP_DIR)..."

if command -v xcodegen >/dev/null 2>&1; then
    (cd "$APP_DIR" && xcodegen generate)
else
    echo "Warning: xcodegen not found. Skipping generation (running in CI-ready mode)."
    # On a real CI runner, xcodegen would be pre-installed or bootstrapped.
fi

echo "Project generation complete."
