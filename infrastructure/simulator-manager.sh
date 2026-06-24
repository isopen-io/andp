#!/bin/bash

# ANDP Simulator Manager
# Manages Apple Simulators using simctl

set -e

COMMAND=$1
DEVICE_NAME=${2:-"iPhone 15"}
RUNTIME=${3:-"iOS 17.0"}

function usage() {
    echo "Usage: $0 [list|boot|shutdown|delete] [device_name] [runtime]"
    echo "Example: $0 boot 'iPhone 15' 'iOS 17.0'"
}

if [ -z "$COMMAND" ]; then
    usage
    exit 1
fi

# Check for simctl
if ! command -v xcrun simctl >/dev/null 2>&1; then
    echo "Warning: xcrun simctl not found. This script requires macOS with Xcode."
    if [[ "$OSTYPE" != "darwin"* ]]; then
        echo "Simulating $COMMAND for $DEVICE_NAME on $RUNTIME..."
        exit 0
    else
        exit 1
    fi
fi

case $COMMAND in
    list)
        xcrun simctl list
        ;;
    boot)
        echo "Looking for $DEVICE_NAME ($RUNTIME)..."
        DEVICE_ID=$(xcrun simctl list devices | grep "$DEVICE_NAME" | grep -v "unavailable" | head -n 1 | sed -E 's/.*\(([-A-Z0-9]+)\).*/\1/')

        if [ -z "$DEVICE_ID" ]; then
            echo "Device not found. Creating $DEVICE_NAME for $RUNTIME..."
            # Try to get the latest runtime if not specified or not found
            RUNTIME_ID=$(xcrun simctl list runtimes | grep "$RUNTIME" | head -n 1 | awk '{print $NF}')
            if [ -z "$RUNTIME_ID" ]; then
                echo "Error: Runtime $RUNTIME not found."
                exit 1
            fi
            DEVICE_ID=$(xcrun simctl create "$DEVICE_NAME" "com.apple.CoreSimulator.SimDeviceType.$(echo $DEVICE_NAME | sed 's/ /-/g')" "$RUNTIME_ID")
        fi

        echo "Booting device $DEVICE_ID..."
        xcrun simctl boot "$DEVICE_ID" || true

        echo "Waiting for device to boot..."
        xcrun simctl bootstatus "$DEVICE_ID"
        echo "Device is ready."
        ;;
    shutdown)
        DEVICE_ID=$(xcrun simctl list devices | grep "$DEVICE_NAME" | grep "Booted" | head -n 1 | sed -E 's/.*\(([-A-Z0-9]+)\).*/\1/')
        if [ -n "$DEVICE_ID" ]; then
            echo "Shutting down device $DEVICE_ID..."
            xcrun simctl shutdown "$DEVICE_ID"
        else
            echo "No booted device found named $DEVICE_NAME."
        fi
        ;;
    delete)
        DEVICE_ID=$(xcrun simctl list devices | grep "$DEVICE_NAME" | head -n 1 | sed -E 's/.*\(([-A-Z0-9]+)\).*/\1/')
        if [ -n "$DEVICE_ID" ]; then
            echo "Deleting device $DEVICE_ID..."
            xcrun simctl delete "$DEVICE_ID"
        fi
        ;;
    *)
        usage
        exit 1
        ;;
esac
