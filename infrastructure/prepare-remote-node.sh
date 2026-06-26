#!/bin/bash

# ANDP Remote Node Preparation Script
# This script automates the setup of a remote macOS runner for ANDP.

set -e

echo "================================================"
echo "      ANDP Remote Node Preparation             "
echo "================================================"

# 1. Check for Xcode
if ! command -v xcodebuild >/dev/null 2>&1; then
    echo "❌ Error: Xcode command line tools are not installed."
    echo "Please install Xcode and the command line tools before running this script."
    exit 1
fi

XCODE_VERSION=$(xcodebuild -version | head -n 1)
echo "Found $XCODE_VERSION"

# 2. Install Homebrew if missing
if ! command -v brew >/dev/null 2>&1; then
    echo "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    echo "Homebrew already installed."
fi

# 3. Install XcodeGen
if ! command -v xcodegen >/dev/null 2>&1; then
    echo "Installing XcodeGen..."
    HOMEBREW_NO_AUTO_UPDATE=1 brew install xcodegen
else
    echo "XcodeGen already installed ($(xcodegen --version))."
fi

# 4. Bootstrap Python Environment
echo "Setting up Python environment..."
if [ -f "./infrastructure/bootstrap.sh" ]; then
    ./infrastructure/bootstrap.sh
else
    echo "⚠️ Warning: infrastructure/bootstrap.sh not found in current directory."
fi

# 5. Verify Toolchain
echo "Verifying toolchain..."
TOOLS=("xcodebuild" "xcodegen" "python3" "pip3" "security" "codesign")
for tool in "${TOOLS[@]}"; do
    if command -v "$tool" >/dev/null 2>&1; then
        echo "✅ $tool: $(command -v "$tool")"
    else
        echo "❌ $tool NOT FOUND"
    fi
done

echo "================================================"
echo "      Preparation Complete                     "
echo "================================================"
