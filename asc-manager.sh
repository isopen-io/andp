#!/bin/bash

# ANDP ASC Manager Wrapper

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

echo "Running ASC command: $COMMAND for account: $ACCOUNT..."

python3 infrastructure/asc/asc_manager.py "$COMMAND" "${PARAMS[@]}" --account "$ACCOUNT"
