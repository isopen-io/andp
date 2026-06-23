#!/bin/bash

# ANDP ASC Manager Wrapper

set -e

COMMAND=$1
ARG=$2

echo "Running ASC command: $COMMAND..."

python3 infrastructure/asc/asc_manager.py "$COMMAND" "$ARG"
