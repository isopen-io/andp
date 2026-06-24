#!/bin/bash

# ANDP Visual Regression Comparison
# Compares two images using pixel-based comparison via Swift utility

set -e

IMAGE1=$1
IMAGE2=$2
DIFF_OUT=$3

if [ -z "$IMAGE1" ] || [ -z "$IMAGE2" ]; then
    echo "Usage: $0 <image1> <image2> [diff_output]"
    exit 1
fi

echo "Comparing $IMAGE1 and $IMAGE2..."

# Fast-path: If files are bitwise identical, they are visually identical.
# This avoids the overhead of booting the Swift interpreter/compiler and pixel comparison.
if cmp -s "$IMAGE1" "$IMAGE2"; then
    echo "✅ Images are identical (fast-path)."
    exit 0
fi

if [[ "$OSTYPE" == "darwin"* ]]; then
    # Compile and run the Swift comparer
    swift infrastructure/visual-comparer.swift "$IMAGE1" "$IMAGE2"
else
    echo "Warning: Comparison not fully supported on non-macOS. Doing basic byte comparison."
    if cmp -s "$IMAGE1" "$IMAGE2"; then
        echo "✅ Images are identical."
        exit 0
    else
        echo "❌ Images differ."
        exit 1
    fi
fi
