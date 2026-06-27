#!/bin/bash

# ANDP Project Validation Script

set -e

PROJECT_FILE="project.yml"

echo "Validating project configuration..."

if [ ! -f "$PROJECT_FILE" ]; then
    echo "❌ project.yml missing!"
    exit 1
fi

# 1. Directory Checks
REQUIRED_DIRS=("Apps/Meeshy" "packages/MeeshySDK" "Apps/MeeshyWidgets" "Apps/MeeshyNotificationExtension" "Apps/MeeshyTests")

for dir in "${REQUIRED_DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        echo "⚠️  Warning: Directory $dir not found (might be created in next step)."
    fi
done

# 2. Dependency Analysis (Modular Governance)
echo "Running dependency analysis..."
if [ -f "infrastructure/dependency-analyzer.py" ]; then
    python3 infrastructure/dependency-analyzer.py
else
    echo "⚠️ Warning: dependency-analyzer.py not found."
fi

echo "✅ Project configuration validation passed."
