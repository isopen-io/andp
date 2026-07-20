#!/bin/bash

# ANDP Metadata Manager Wrapper

set -e

COMMAND=$1
shift

# Handle optional --account flag
ACCOUNT="primary"
PARAMS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        --account)
            ACCOUNT="$2"
            shift 2
            ;;
        *)
            PARAMS+=("$1")
            shift
            ;;
    esac
done

echo "Running Metadata command: $COMMAND for account: $ACCOUNT..."

python3 -m andp.asc.metadata_manager "$COMMAND" "${PARAMS[@]}" --account "$ACCOUNT"
