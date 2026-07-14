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

# Bolt Optimization: Consolidate two date calls into one to reduce process forks (-1 fork).
# We fetch both the unix timestamp and the UTC date string in a single invocation.
DATES=$(date -u +"%s %Y-%m-%dT%H:%M:%SZ")
TIMESTAMP=${DATES%% *}
DATE_STR=${DATES#* }

# Bolt Optimization: Use shell built-in $RANDOM for UUID generation to eliminate process forks (-2 forks).
# This replaces the 'tr /dev/urandom | head' pipeline which is much more expensive.
UUID="${RANDOM}${RANDOM}"

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
