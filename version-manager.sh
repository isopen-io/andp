#!/bin/bash

# ANDP Version Manager
# Handles semantic versioning and build numbers

set -e

COMMAND=$1
VALUE=$2

# Project info
PROJECT_NAME=$(grep "name:" project.yml | head -n 1 | awk '{print $2}')
XCODEPROJ="${PROJECT_NAME}.xcodeproj"

function get_marketing_version() {
    if command -v agvtool >/dev/null 2>&1 && [ -d "$XCODEPROJ" ]; then
        agvtool mvers -terse
    else
        # Fallback: search in project.yml or Info.plist
        # For simplicity in this demo, we read from a version file if it exists, else default
        if [ -f "VERSION" ]; then
            cat VERSION
        else
            echo "1.0.0"
        fi
    fi
}

function get_build_number() {
    if command -v agvtool >/dev/null 2>&1 && [ -d "$XCODEPROJ" ]; then
        agvtool vers -terse
    else
        if [ -f "BUILD_NUMBER" ]; then
            cat BUILD_NUMBER
        else
            echo "1"
        fi
    fi
}

function set_marketing_version() {
    local version=$1
    echo "Setting marketing version to $version"
    if command -v agvtool >/dev/null 2>&1 && [ -d "$XCODEPROJ" ]; then
        agvtool new-marketing-version "$version"
    fi
    echo "$version" > VERSION
}

function set_build_number() {
    local build=$1
    echo "Setting build number to $build"
    if command -v agvtool >/dev/null 2>&1 && [ -d "$XCODEPROJ" ]; then
        agvtool next-bump # or agvtool new-version -all "$build"
    fi
    echo "$build" > BUILD_NUMBER
}

case $COMMAND in
    "get")
        echo "Version: $(get_marketing_version) ($(get_build_number))"
        ;;
    "set-version")
        if [ -z "$VALUE" ]; then echo "Value required"; exit 1; fi
        set_marketing_version "$VALUE"
        ;;
    "set-build")
        if [ -z "$VALUE" ]; then echo "Value required"; exit 1; fi
        set_build_number "$VALUE"
        ;;
    "bump-build")
        CURRENT=$(get_build_number)
        NEW=$((CURRENT + 1))
        set_build_number "$NEW"
        ;;
    "tag")
        VERSION=$(get_marketing_version)
        BUILD=$(get_build_number)
        TAG="v$VERSION-$BUILD"
        echo "Creating git tag $TAG"
        if git rev-parse "$TAG" >/dev/null 2>&1; then
            echo "Tag $TAG already exists"
        else
            git tag -a "$TAG" -m "Release $TAG"
            echo "Tag $TAG created. Run 'git push --tags' to upload."
        fi
        ;;
    *)
        echo "Usage: $0 {get|set-version|set-build|bump-build|tag} [value]"
        exit 1
        ;;
esac
