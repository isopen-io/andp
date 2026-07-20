#!/bin/bash
APP_DIR="${ANDP_APP_DIR:-examples/meeshy}"


# ANDP Localization Manager
# Orchestrates localization validation

set -e

RESOURCES_PATH="$APP_DIR/Apps/Meeshy"

echo "Running localization validation..."

if [ -f "infrastructure/localization-validator.py" ]; then
    python3 infrastructure/localization-validator.py "$RESOURCES_PATH"
else
    echo "Error: localization-validator.py not found."
    exit 1
fi
