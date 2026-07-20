#!/bin/bash

# ANDP Simulator Manager
# Manages Apple Simulators using simctl

set -e

COMMAND=$1
DEVICE_NAME=${2:-"iPhone 15"}
RUNTIME=${3:-"iOS 17.0"}

function usage() {
    echo "Usage: $0 [list|boot|shutdown|delete|mass-reset|pool-init] [device_name] [runtime]"
    echo "Example: $0 boot 'iPhone 15' 'iOS 17.0'"
    echo "         $0 mass-reset 'iOS 17.0'"
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

        # Iteration 11: Robust boot logic with retries
        RETRY_COUNT=0
        MAX_RETRIES=3
        BOOT_SUCCESS=false

        while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
            echo "Booting device $DEVICE_ID (Attempt $((RETRY_COUNT + 1))/$MAX_RETRIES)..."
            if xcrun simctl boot "$DEVICE_ID" 2>/dev/null || xcrun simctl list devices | grep "$DEVICE_ID" | grep -q "Booted"; then
                echo "Waiting for device $DEVICE_ID to be ready..."
                if xcrun simctl bootstatus "$DEVICE_ID" >/dev/null 2>&1; then
                    echo "✅ Device is ready."
                    BOOT_SUCCESS=true
                    break
                fi
            fi
            RETRY_COUNT=$((RETRY_COUNT + 1))
            echo "⚠️ Boot failed. Waiting 5s before retry..."
            sleep 5
        done

        if [ "$BOOT_SUCCESS" = false ]; then
            echo "❌ Failed to boot device $DEVICE_ID after $MAX_RETRIES attempts."
            exit 1
        fi
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
    mass-reset)
        echo "Mass resetting simulators for runtime: $RUNTIME..."
        # Shutdown all booted simulators for this runtime
        xcrun simctl list devices | grep "$RUNTIME" | grep "Booted" | sed -E 's/.*\(([-A-Z0-9]+)\).*/\1/' | xargs -I {} xcrun simctl shutdown {} || true
        # Erase all simulators for this runtime
        xcrun simctl list devices | grep "$RUNTIME" | sed -E 's/.*\(([-A-Z0-9]+)\).*/\1/' | xargs -I {} xcrun simctl erase {}
        echo "✅ Mass reset complete."
        ;;
    pool-init)
        echo "Initializing simulator pool for $RUNTIME..."
        DEVICES=("iPhone 15" "iPhone 15 Pro" "iPad (10th generation)")
        for DEV in "${DEVICES[@]}"; do
            echo "Preparing $DEV..."
            $0 boot "$DEV" "$RUNTIME"
            $0 shutdown "$DEV"
        done
        echo "✅ Pool initialization complete."
        ;;
    *)
        usage
        exit 1
        ;;
esac
