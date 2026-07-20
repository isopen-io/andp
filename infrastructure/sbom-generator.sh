#!/bin/bash
APP_DIR="${ANDP_APP_DIR:-examples/meeshy}"

set -e

# ANDP Software Bill of Materials (SBOM) Generator
# Generates a CycloneDX-compatible JSON SBOM for the project.

OUTPUT_DIR="metrics"
mkdir -p "$OUTPUT_DIR"
OUTPUT_FILE="${OUTPUT_DIR}/sbom.json"

# Project metadata from project.yml
PROJECT_NAME=$(grep "name:" "$APP_DIR/project.yml" | head -n 1 | awk '{print $2}')
[ -z "$PROJECT_NAME" ] && PROJECT_NAME="UnknownProject"

echo "Generating SBOM for $PROJECT_NAME..."

# Basic SBOM metadata
cat << EOM > "$OUTPUT_FILE"
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "serialNumber": "urn:uuid:$(tr -dc 'a-f0-9' < /dev/urandom | head -c 8)-$(tr -dc 'a-f0-9' < /dev/urandom | head -c 4)-$(tr -dc 'a-f0-9' < /dev/urandom | head -c 4)-$(tr -dc 'a-f0-9' < /dev/urandom | head -c 4)-$(tr -dc 'a-f0-9' < /dev/urandom | head -c 12)",
  "version": 1,
  "metadata": {
    "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
    "tools": [
      {
        "vendor": "Apple Native Delivery Platform",
        "name": "ANDP SBOM Generator",
        "version": "1.0.0"
      }
    ],
    "component": {
      "name": "$PROJECT_NAME",
      "type": "application"
    }
  },
  "components": []
}
EOM

# Function to add a component to the SBOM
add_component() {
    local name=$1
    local version=$2
    local url=$3
    local type=$4

    python3 - "$OUTPUT_FILE" "$name" "$version" "$url" "$type" << 'END'
import sys
import json

file_path = sys.argv[1]
name = sys.argv[2]
version = sys.argv[3]
url = sys.argv[4]
type_val = sys.argv[5]

with open(file_path, 'r') as f:
    data = json.load(f)

component = {
    "name": name,
    "version": version,
    "type": type_val,
    "externalReferences": [
        {
            "type": "vcs",
            "url": url
        }
    ]
}
data['components'].append(component)

with open(file_path, 'w') as f:
    json.dump(data, f, indent=2)
END
}

# Parse project.yml for dependencies
echo "Analyzing dependencies from project.yml..."

# Extract all packages
# Use python to parse YAML to avoid brittle grep/awk
DEPS=$(python3 - << 'END'
import sys
import yaml

try:
    with open(os.environ.get('ANDP_APP_DIR', 'examples/meeshy') + '/project.yml', 'r') as f:
        config = yaml.safe_load(f)

    packages = config.get('packages', {})
    for name, details in packages.items():
        if 'url' in details:
            print(f"DEP_REMOTE|{name}|{details.get('from', 'unknown')}|{details['url']}")
        elif 'path' in details:
            print(f"DEP_LOCAL|{name}|local|{details['path']}")
except Exception as e:
    sys.stderr.write(f"Error parsing project.yml: {e}\n")
END
)

echo "$DEPS" | while IFS='|' read -r type name version url; do
    [ -z "$type" ] && continue
    if [ "$type" == "DEP_REMOTE" ]; then
        echo "Adding remote dependency: $name ($version)..."
        add_component "$name" "$version" "$url" "library"
    elif [ "$type" == "DEP_LOCAL" ]; then
        echo "Adding local package: $name..."
        add_component "$name" "$version" "$url" "library"
    fi
done

echo "✅ SBOM generated: $OUTPUT_FILE"
