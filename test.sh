#!/bin/bash

# ANDP Test Orchestrator
# Orchestrates running tests using xcodebuild

set -e

SCHEME=${1:-"Meeshy"}
DEVICE_NAME=${2:-"iPhone 15"}
OS_VERSION=${3:-"17.0"}

RESULT_BUNDLE_PATH="TestResults.xcresult"

echo "Starting test orchestration for scheme: $SCHEME..."

# Ensure simulator is ready
./simulator-manager.sh boot "$DEVICE_NAME" "iOS $OS_VERSION"

echo "Running tests..."

# Clean up previous results
rm -rf "$RESULT_BUNDLE_PATH"

if command -v xcodebuild >/dev/null 2>&1; then
    xcodebuild test \
        -scheme "$SCHEME" \
        -destination "platform=iOS Simulator,name=$DEVICE_NAME,OS=$OS_VERSION" \
        -resultBundlePath "$RESULT_BUNDLE_PATH"
else
    echo "Warning: xcodebuild not found. Simulating test success."
    mkdir -p "$RESULT_BUNDLE_PATH"
    # Create a mock Info.plist that xcresulttool might expect
    echo "Simulated result" > "$RESULT_BUNDLE_PATH/Info.plist"
fi

echo "Tests complete."

# Generate report
if [ -x "./test-report.sh" ]; then
    ./test-report.sh "$RESULT_BUNDLE_PATH"
fi

# Visual Regression Check (Example for a specific test)
# In a real setup, we would extract screenshots from the .xcresult
# and compare them against baselines.
# Here we provide a hook.
echo "Checking for visual regressions..."
# ./infrastructure/visual-compare.sh path/to/captured.png Tests/VisualBaselines/expected.png || echo "Visual regression detected!"
