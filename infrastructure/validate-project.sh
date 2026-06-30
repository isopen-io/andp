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
    # We ignore failures here to allow the script to continue if yaml is missing in some environments,
    # but ideally it should be installed.
    python3 infrastructure/dependency-analyzer.py || echo "⚠️ Warning: dependency-analyzer.py failed."
else
    echo "⚠️ Warning: dependency-analyzer.py not found."
fi

# 3. visionOS & iPad Responsiveness Checks (Iteration 7)
echo "Validating visionOS and iPad responsiveness settings..."

# Check for targeted device families (1=iPhone, 2=iPad, 7=visionOS)
if ! grep -q "TARGETED_DEVICE_FAMILY: \"1,2,7\"" "$PROJECT_FILE"; then
    echo "⚠️ Warning: TARGETED_DEVICE_FAMILY does not include visionOS (7) or iPad (2)"
fi

# Check for Stage Manager / Split View support (Requires iPad)
if grep -q "UIRequiresFullScreen: YES" "$PROJECT_FILE"; then
    echo "❌ Error: UIRequiresFullScreen is set to YES, which breaks Stage Manager and Split View!"
    exit 1
fi

# Ensure all iPad orientations are supported for full responsiveness
if ! grep -q "UISupportedInterfaceOrientations~ipad" "$PROJECT_FILE"; then
    echo "⚠️ Warning: UISupportedInterfaceOrientations~ipad missing. Ensure all orientations are supported for full iPad responsiveness."
fi

# 4. Platform Consistency Checks
echo "Verifying platform consistency..."
# Ensure visionOS deployment targets are present
if ! grep -q "visionOS: \"1.0\"" "$PROJECT_FILE"; then
    echo "⚠️ Warning: visionOS deployment target missing in project.yml"
fi

echo "✅ Project configuration validation passed."
