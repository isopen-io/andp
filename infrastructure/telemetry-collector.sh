#!/bin/bash
set -e

# ANDP Telemetry Collector
# Aggregates build, test, and quality metrics into a single telemetry event.

METRICS_DIR="metrics"
mkdir -p "$METRICS_DIR"

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
# Bolt Optimization: native shell UUID-ish generation
UUID=$(tr -dc 'a-f0-9' < /dev/urandom | head -c 8)
EVENT_FILE="${METRICS_DIR}/telemetry_${UUID}.json"

echo "Collecting platform telemetry..."

# Basic Platform Context
OS_TYPE=$(uname)
ARCH=$(uname -m)

# Gather available metrics
BUILD_DATA="{}"
if [ -f "${METRICS_DIR}/build_metrics.json" ]; then
    BUILD_DATA=$(cat "${METRICS_DIR}/build_metrics.json")
fi

TEST_DATA="{}"
if [ -f "${METRICS_DIR}/test_metrics.json" ]; then
    TEST_DATA=$(cat "${METRICS_DIR}/test_metrics.json")
fi

ANALYSIS_DATA="{}"
if [ -f "${METRICS_DIR}/analysis_report.json" ]; then
    ANALYSIS_DATA=$(cat "${METRICS_DIR}/analysis_report.json")
fi

SBOM_COMPONENTS="[]"
if [ -f "${METRICS_DIR}/sbom.json" ]; then
    SBOM_COMPONENTS=$(python3 -c "import json; print(json.dumps(json.load(open('metrics/sbom.json'))['components']))")
fi

# Construct the Telemetry Event
python3 - << END
import json
import os

telemetry = {
    "timestamp": "$TIMESTAMP",
    "event_id": "$UUID",
    "environment": {
        "os": "$OS_TYPE",
        "arch": "$ARCH",
        "ci": os.environ.get("CI", "false")
    },
    "metrics": {
        "build": $BUILD_DATA,
        "test": $TEST_DATA,
        "analysis": $ANALYSIS_DATA
    },
    "supply_chain": {
        "dependencies_count": len($SBOM_COMPONENTS),
        "sbom_available": os.path.exists("metrics/sbom.json")
    }
}

with open('$EVENT_FILE', 'w') as f:
    json.dump(telemetry, f, indent=2)
END

echo "✅ Telemetry event recorded: $EVENT_FILE"
