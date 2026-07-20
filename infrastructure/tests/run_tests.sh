#!/bin/bash
APP_DIR="${ANDP_APP_DIR:-examples/meeshy}"


# ANDP Infrastructure Integration Tests

set -e

echo "Running Infrastructure Tests..."

# Test App Store Connect API modules (pytest)
echo "Testing App Store Connect API modules..."
if python3 -m pytest infrastructure/tests/python/ -q; then
    echo "✅ ASC API pytest suite PASSED"
else
    echo "❌ ASC API pytest suite FAILED"
    exit 1
fi

# Test Version Manager
echo "Testing version-manager.sh..."
OLD_VERSION=$(cat VERSION)
OLD_BUILD=$(cat BUILD_NUMBER)
./version-manager.sh set-version 9.9.9
./version-manager.sh set-build 100
VERSION_INFO=$(./version-manager.sh get)
if [[ "$VERSION_INFO" == *"9.9.9 (100)"* ]]; then
    echo "✅ version-manager.sh set/get PASSED"
else
    echo "❌ version-manager.sh set/get FAILED: $VERSION_INFO"
    exit 1
fi

./version-manager.sh bump-build
VERSION_INFO=$(./version-manager.sh get)
if [[ "$VERSION_INFO" == *"9.9.9 (101)"* ]]; then
    echo "✅ version-manager.sh bump PASSED"
else
    echo "❌ version-manager.sh bump FAILED: $VERSION_INFO"
    exit 1
fi
# Restore version and build number so tests never pollute the working tree
./version-manager.sh set-version "$OLD_VERSION"
./version-manager.sh set-build "$OLD_BUILD"
git checkout -- "$APP_DIR/Apps/Meeshy/Info.plist" 2>/dev/null || true
rm -f "$APP_DIR/Apps/MeeshyTests/Info.plist.new1"

# Test Artifact Manager
echo "Testing artifact-manager.sh..."
mkdir -p build/test
touch build/test/app.ipa
./artifact-manager.sh package > /dev/null
if [ -f "artifacts/app.ipa" ] && [ -f "artifacts/Meeshy.dmg" ] && [ -f "artifacts/Meeshy.pkg" ]; then
    echo "✅ artifact-manager.sh package PASSED"
else
    echo "❌ artifact-manager.sh package FAILED"
    exit 1
fi

# Test Localization Validator
echo "Testing localization-validator.py..."
mkdir -p test_lproj/en.lproj test_lproj/fr.lproj
echo "\"key1\" = \"val1\";" > test_lproj/en.lproj/Localizable.strings
echo "\"key1\" = \"val1\";" > test_lproj/fr.lproj/Localizable.strings
if python3 infrastructure/localization-validator.py test_lproj > /dev/null; then
    echo "✅ localization-validator.py success case PASSED"
else
    echo "❌ localization-validator.py success case FAILED"
    exit 1
fi

echo "" > test_lproj/fr.lproj/Localizable.strings
if python3 infrastructure/localization-validator.py test_lproj > /dev/null; then
    echo "❌ localization-validator.py failure case FAILED (it should have failed)"
    exit 1
else
    echo "✅ localization-validator.py failure case PASSED"
fi
rm -rf test_lproj

# Test Analytics Manager
echo "Testing analytics-manager.sh..."
./infrastructure/analytics-manager.sh record test_type test_name 42 SUCCESS > /dev/null
if ls metrics/test_type_*.json > /dev/null 2>&1; then
    echo "✅ analytics-manager.sh PASSED"
else
    echo "❌ analytics-manager.sh FAILED"
    exit 1
fi

# Test Performance Monitor
echo "Testing performance-monitor.py..."
mkdir -p mock.xcresult
touch mock.xcresult/Info.plist
if python3 infrastructure/performance-monitor.py mock.xcresult > /dev/null; then
    echo "✅ performance-monitor.py PASSED"
else
    echo "❌ performance-monitor.py FAILED"
    exit 1
fi
rm -rf mock.xcresult

# Test AI Analyzer
echo "Testing ai-analyzer.py..."
# Create a temporary file to ensure a predictable error at a specific line
cat <<AI_EOF > "$APP_DIR/Apps/TestIssue.swift"
import SwiftUI
struct TestIssue: View {
    var body: some View {
        // Line 5
        Button("Test") { }
    }
}
AI_EOF
AI_OUTPUT=$(python3 infrastructure/ai-analyzer.py "$APP_DIR/Apps")
rm "$APP_DIR/Apps/TestIssue.swift"
if [[ "$AI_OUTPUT" == *"Bolt Optimized"* ]] && [[ "$AI_OUTPUT" == *"TestIssue.swift:5 - Risk:"* ]]; then
    echo "✅ ai-analyzer.py PASSED"
else
    echo "❌ ai-analyzer.py FAILED or output format unexpected"
    echo "$AI_OUTPUT"
    exit 1
fi

# Test Visual Compare (Basic check)
echo "Testing visual-compare.sh..."
touch img1.png img2.png
if ./infrastructure/visual-compare.sh img1.png img1.png > /dev/null; then
    echo "✅ visual-compare.sh identical case PASSED"
else
    echo "❌ visual-compare.sh identical case FAILED"
    exit 1
fi
rm img1.png img2.png

# Test Dashboard Generator
echo "Testing generate-dashboard.sh..."
if ./infrastructure/generate-dashboard.sh > /dev/null; then
    if [ -f "dashboard.html" ]; then
        echo "✅ generate-dashboard.sh PASSED"
    else
        echo "❌ generate-dashboard.sh FAILED: dashboard.html missing"
        exit 1
    fi
else
    echo "❌ generate-dashboard.sh FAILED"
    exit 1
fi

echo "All Infrastructure Tests PASSED."
