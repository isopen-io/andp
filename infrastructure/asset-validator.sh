#!/bin/bash
APP_DIR="${ANDP_APP_DIR:-examples/meeshy}"


# ANDP Asset Validator (Iteration 10)
# Verifies that all targets in project.yml have required assets in their .xcassets

set -e

PROJECT_YML="$APP_DIR/project.yml"
ASSETS_DIR="$APP_DIR/Apps"

echo "Running ANDP Asset Governance..."

# 1. Check if project.yml exists
if [ ! -f "$PROJECT_YML" ]; then
    echo "❌ project.yml not found."
    exit 1
fi

# 2. Extract targets and their asset requirements
# This is a simplified extraction looking for common patterns
TARGETS=$(grep -E "^  [A-Za-z0-9]+:" "$PROJECT_YML" | sed 's/  //' | sed 's/://')

VIOLATIONS=0

for TARGET in $TARGETS; do
    echo "Validating target: $TARGET"

    # Try to find the directory for the target
    TARGET_DIR=$(find "$APP_DIR/Apps" -maxdepth 1 -type d -name "$TARGET")

    if [ -d "$TARGET_DIR" ]; then
        ASSETS_PATH=$(find "$TARGET_DIR" -name "*.xcassets")

        if [ -z "$ASSETS_PATH" ]; then
            # Not every target needs assets (e.g. tests), but main apps should
            if [[ "$TARGET" != *Tests ]] && [[ "$TARGET" != *UITests ]] && [[ "$TARGET" != *Extension ]]; then
                echo "  ⚠️ Warning: No .xcassets found for target $TARGET"
                VIOLATIONS=$((VIOLATIONS + 1))
            fi
            continue
        fi

        # Check for AppIcon if it's an application target
        TYPE=$(grep -A 5 "  $TARGET:" "$PROJECT_YML" | grep "type:" | head -n 1 | awk '{print $2}')

        if [ "$TYPE" == "application" ]; then
            APPICON_NAME=$(grep -A 20 "  $TARGET:" "$PROJECT_YML" | grep "ASSETCATALOG_COMPILER_APPICON_NAME" | head -n 1 | awk '{print $2}')
            if [ -z "$APPICON_NAME" ]; then APPICON_NAME="AppIcon"; fi

            ICON_PATH=$(find "$ASSETS_PATH" -name "$APPICON_NAME.appiconset")
            if [ -z "$ICON_PATH" ]; then
                echo "  ❌ Error: Missing $APPICON_NAME in $ASSETS_PATH for target $TARGET"
                VIOLATIONS=$((VIOLATIONS + 1))
            else
                echo "  ✅ AppIcon found: $APPICON_NAME"
            fi

            # Check for AccentColor
            ACCENT_NAME=$(grep -A 20 "  $TARGET:" "$PROJECT_YML" | grep "ASSETCATALOG_COMPILER_GLOBAL_ACCENT_COLOR_NAME" | head -n 1 | awk '{print $2}')
            if [ ! -z "$ACCENT_NAME" ]; then
                ACCENT_PATH=$(find "$ASSETS_PATH" -name "$ACCENT_NAME.colorset")
                if [ -z "$ACCENT_PATH" ]; then
                    echo "  ❌ Error: Missing $ACCENT_NAME in $ASSETS_PATH for target $TARGET"
                    VIOLATIONS=$((VIOLATIONS + 1))
                else
                    echo "  ✅ AccentColor found: $ACCENT_NAME"
                fi
            fi
        fi
    fi
done

if [ $VIOLATIONS -eq 0 ]; then
    echo "✅ Asset Governance PASSED."
else
    echo "❌ Asset Governance FAILED with $VIOLATIONS violations."
    # We don't exit with 1 yet to allow CI to see the report, but we could
fi

# Store results for dashboard/governance report
mkdir -p metrics
echo "{\"asset_violations\": $VIOLATIONS, \"status\": \"$( [ $VIOLATIONS -eq 0 ] && echo "PASSED" || echo "FAILED" )\"}" > metrics/asset_governance.json
