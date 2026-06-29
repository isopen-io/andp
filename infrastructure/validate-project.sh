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

# 3. visionOS & iPad Responsiveness Checks (Iteration 7)
echo "Validating visionOS and iPad responsiveness settings..."

# Check if visionOS is in supported platforms for Meeshy target
if ! grep -q "platform: \[iOS, visionOS\]" "$PROJECT_FILE"; then
    echo "⚠️ Warning: Meeshy target does not explicitly support [iOS, visionOS] in project.yml"
fi

# Check for targeted device families (1=iPhone, 2=iPad, 7=visionOS)
if ! grep -q "TARGETED_DEVICE_FAMILY: \"1,2,7\"" "$PROJECT_FILE"; then
    echo "⚠️ Warning: TARGETED_DEVICE_FAMILY does not include visionOS (7) or iPad (2)"
fi

# Check for Stage Manager / Split View support (Requires iPad)
# In project.yml, UIRequiresFullScreen: NO is usually the default, but we should verify it's not set to YES
if grep -q "UIRequiresFullScreen: YES" "$PROJECT_FILE"; then
    echo "❌ Error: UIRequiresFullScreen is set to YES, which breaks Stage Manager and Split View!"
    exit 1
fi

# 4. Platform Consistency Checks (Regression Fix for CI Failure)
echo "Verifying platform consistency between app and dependencies..."

# If main app supports visionOS, tests and extensions should too (except Widgets which are often platform-specific)
if grep -q "Meeshy:" "$PROJECT_FILE" && grep -A 2 "Meeshy:" "$PROJECT_FILE" | grep -q "platform: \[iOS, visionOS\]"; then
    for target in "MeeshyTests" "MeeshyUITests" "MeeshyNotificationExtension"; do
        if ! grep -A 5 "$target:" "$PROJECT_FILE" | grep -q "platform: \[iOS, visionOS\]"; then
            echo "❌ Error: Target $target does not match main app platform [iOS, visionOS]!"
            exit 1
        fi
    done
fi

echo "✅ Project configuration validation passed."
