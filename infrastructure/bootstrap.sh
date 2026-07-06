#!/bin/bash

# ANDP Bootstrap Script

set -e

echo "Bootstrapping ANDP environment..."

# In a real macOS environment, we would check for:
# - Xcode
# - XcodeGen (brew install xcodegen)
# - Python 3 + dependencies (PyYAML, requests)

if [[ "$OSTYPE" == "darwin"* ]]; then
    if ! command -v xcodegen >/dev/null 2>&1; then
        echo "Installing XcodeGen..."
        HOMEBREW_NO_AUTO_UPDATE=1 brew install xcodegen
    fi
else
    echo "Running on non-macOS environment ($OSTYPE). Standard build tools may be unavailable."
fi

# Install python dependencies for ASC manager
if command -v pip3 >/dev/null 2>&1; then
    # Optimization: Check if dependencies are already satisfied to avoid slow pip call
    if ! python3 -c "import yaml, requests, jwt, cryptography, pytest" 2>/dev/null; then
        echo "Installing Python dependencies..."
        # On modern macOS (PEP 668), pip may refuse to install outside a venv.
        # We use --break-system-packages for CI/CD simplicity.
        PIP_FLAGS="--user"
        if pip3 install --help | grep -q "break-system-packages"; then
            PIP_FLAGS="$PIP_FLAGS --break-system-packages"
        fi
        # cryptography is required by PyJWT for ES256 (App Store Connect JWTs)
        pip3 install PyYAML requests pyjwt cryptography pytest $PIP_FLAGS
    else
        echo "Python dependencies already satisfied."
    fi
fi

echo "Bootstrap complete."
