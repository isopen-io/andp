#!/bin/bash

# ANDP Analytics Manager
# Handles metric collection and storage

set -e

METRICS_DIR="metrics"
mkdir -p "$METRICS_DIR"

COMMAND=$1
TYPE=$2
NAME=$3
VALUE=$4
STATUS=${5:-"SUCCESS"}

usage() {
    echo "Usage: $0 record <type> <name> <value> [status]"
    echo "Example: $0 record build Meeshy 120 SUCCESS"
    exit 1
}

if [ "$COMMAND" != "record" ]; then
    usage
fi

TIMESTAMP=$(date +%s)
DATE_STR=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
# Bolt Optimization: Replace expensive /dev/urandom pipeline with shell-native $RANDOM.
# This significantly reduces process spawning overhead during telemetry recording.
UUID=$(printf '%04x%04x' $RANDOM $RANDOM)
FILENAME="${METRICS_DIR}/${TYPE}_${TIMESTAMP}_${UUID}.json"

cat <<EOF > "$FILENAME"
{
  "timestamp": $TIMESTAMP,
  "date": "$DATE_STR",
  "type": "$TYPE",
  "name": "$NAME",
  "value": "$VALUE",
  "status": "$STATUS"
}
EOF

echo "Metric recorded: $FILENAME"
