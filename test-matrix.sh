#!/bin/bash

# ANDP Test Matrix Orchestrator
# Runs tests across multiple devices and OS versions

set -e

SCHEME=${1:-"Meeshy"}

# Define the matrix
DEVICES=("iPhone 15" "iPad Pro (11-inch) (4th generation)")
OS_VERSIONS=("17.0")

echo "Starting test matrix execution for scheme: $SCHEME..."

for device in "${DEVICES[@]}"; do
    for os in "${OS_VERSIONS[@]}"; do
        echo "========================================"
        echo "Testing on $device ($os)"
        echo "========================================"
        ./test.sh "$SCHEME" "$device" "$os"
    done
done

echo "Test matrix execution complete."
