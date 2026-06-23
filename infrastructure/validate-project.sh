#!/bin/bash

# ANDP Project Validation Script

set -e

PROJECT_FILE="project.yml"

echo "Validating project configuration..."

if [ ! -f "$PROJECT_FILE" ]; then
    echo "❌ project.yml missing!"
    exit 1
fi

# Check for required directories mentioned in project.yml
REQUIRED_DIRS=("Apps/Meeshy" "packages/MeeshySDK" "Apps/MeeshyWidgets" "Apps/MeeshyNotificationExtension" "Apps/MeeshyTests")

for dir in "${REQUIRED_DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        echo "⚠️  Warning: Directory $dir not found (might be created in next step)."
    fi
done

echo "✅ Project configuration validation passed."
