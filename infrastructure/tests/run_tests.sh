#!/bin/bash

# ANDP Infrastructure Integration Tests

set -e

echo "Running Infrastructure Tests..."

# Test Version Manager
echo "Testing version-manager.sh..."
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

echo "All Infrastructure Tests PASSED."
