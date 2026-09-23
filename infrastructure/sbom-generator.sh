#!/bin/bash

# ANDP Software Bill of Materials (SBOM) Generator (Bolt Optimized)
# Generates a CycloneDX-compatible JSON SBOM for the project in a single Python pass.

set -e

APP_DIR="${ANDP_APP_DIR:-examples/meeshy}"
OUTPUT_DIR="${ANDP_CONFIG_DIR:-.andp}/metrics"
mkdir -p "$OUTPUT_DIR"
OUTPUT_FILE="${OUTPUT_DIR}/sbom.json"

# Bolt Optimization: Single-process Python execution eliminates process forks,
# tr/urandom broken pipes, and repeated disk re-reads per component.
ANDP_APP_DIR="$APP_DIR" ANDP_OUTPUT_FILE="$OUTPUT_FILE" python3 - << 'EOF_PY'
import os
import sys
import json
import uuid
import datetime
import yaml

app_dir = os.environ.get("ANDP_APP_DIR", "examples/meeshy")
output_file = os.environ.get("ANDP_OUTPUT_FILE", ".andp/metrics/sbom.json")

project_path = os.path.join(app_dir, "project.yml")
project_name = "UnknownProject"
packages = {}

if os.path.exists(project_path):
    try:
        with open(project_path, "r", encoding="utf-8") as f:
            loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
            config = yaml.load(f, Loader=loader) or {}
            project_name = config.get("name", "UnknownProject")
            packages = config.get("packages", {}) or {}
    except Exception as e:
        sys.stderr.write(f"Error parsing project.yml: {e}\n")

print(f"Generating SBOM for {project_name}...")
print("Analyzing dependencies from project.yml...")

now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

components = []
for name, details in packages.items():
    if not details:
        continue
    if "url" in details:
        version = details.get("from", "unknown")
        url = details["url"]
        print(f"Adding remote dependency: {name} ({version})...")
        components.append({
            "name": name,
            "version": version,
            "type": "library",
            "externalReferences": [{"type": "vcs", "url": url}]
        })
    elif "path" in details:
        url = details["path"]
        print(f"Adding local package: {name}...")
        components.append({
            "name": name,
            "version": "local",
            "type": "library",
            "externalReferences": [{"type": "vcs", "url": url}]
        })

sbom = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.5",
    "serialNumber": f"urn:uuid:{uuid.uuid4()}",
    "version": 1,
    "metadata": {
        "timestamp": now,
        "tools": [
            {
                "vendor": "Apple Native Delivery Platform",
                "name": "ANDP SBOM Generator",
                "version": "1.0.0"
            }
        ],
        "component": {
            "name": project_name,
            "type": "application"
        }
    },
    "components": components
}

with open(output_file, "w", encoding="utf-8") as f:
    json.dump(sbom, f, indent=2)

print(f"✅ SBOM generated: {output_file}")
EOF_PY
