#!/bin/bash

# ANDP Release Manager
# Automates release notes, tagging, and promotion

set -e

DRY_RUN=false
if [[ "$*" == *"--dry-run"* ]]; then
    DRY_RUN=true
fi

echo "Starting release process..."

# 1. Generate Release Notes from Git
CHANGELOG="CHANGELOG.md"
VERSION=$(./version-manager.sh get | awk '{print $2}')

echo "Generating release notes for $VERSION..."

# Get last tag
LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")

{
    echo "## $VERSION - $(date +%Y-%m-%d)"
    if [ -n "$LAST_TAG" ]; then
        echo "### Changes since $LAST_TAG"
        git log "$LAST_TAG..HEAD" --oneline --no-merges | sed 's/^/- /'
    else
        echo "### Initial Release"
        git log --oneline --no-merges | sed 's/^/- /'
    fi
    echo ""
} > RELEASE_NOTES.tmp

if [ -f "$CHANGELOG" ]; then
    # Simple deduplication: if the first line of CHANGELOG is the same as the first line of RELEASE_NOTES.tmp, skip
    if head -n 1 "$CHANGELOG" | grep -q "## $VERSION"; then
        echo "Version $VERSION already exists in $CHANGELOG. Skipping update."
    else
        cat RELEASE_NOTES.tmp "$CHANGELOG" > "${CHANGELOG}.new"
        mv "${CHANGELOG}.new" "$CHANGELOG"
    fi
else
    mv RELEASE_NOTES.tmp "$CHANGELOG"
fi
rm -f RELEASE_NOTES.tmp

# 2. Tag the release
if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would tag the release using version-manager.sh"
else
    ./version-manager.sh tag
fi

echo "Release process complete."
