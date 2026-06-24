#!/bin/bash

# ANDP Build Matrix Orchestrator
# Builds multiple schemes and configurations

set -e

SCHEMES=("Meeshy" "MeeshyWidgets")
CONFIGURATIONS=("Debug" "Release")
PLATFORMS=("iOS")

echo "Starting build matrix execution..."

for scheme in "${SCHEMES[@]}"; do
    for config in "${CONFIGURATIONS[@]}"; do
        for platform in "${PLATFORMS[@]}"; do
            echo "========================================"
            echo "Building $scheme | $config | $platform"
            echo "========================================"
            ./build.sh "$scheme" "$config"
        done
    done
done

echo "Build matrix execution complete."
