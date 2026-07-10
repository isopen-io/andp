#!/bin/bash

# ANDP Dashboard Generator
# Aggregates metrics and AI insights into an HTML dashboard

set -e

OUTPUT_FILE="dashboard.html"
METRICS_DIR="metrics"

echo "Generating Developer Productivity Dashboard..."

# Function to extract latest metrics from JSON files
get_latest_metric() {
    local type=$1
    ls -t "$METRICS_DIR/${type}"*.json 2>/dev/null | head -n 1
}

BUILD_METRIC=$(get_latest_metric "build")
TEST_METRIC=$(get_latest_metric "test")
PERF_METRIC=$(get_latest_metric "perf")
AI_METRIC="$METRICS_DIR/ai_analysis.json"

# Bolt Optimization: Consolidate multiple Python spawns into a single process.
# Each Python startup takes ~0.3s. Consolidating 4 calls into 1 saves ~0.9s.
# We also consolidate the HTML boilerplate into the same heredoc for better performance.
export BUILD_METRIC TEST_METRIC PERF_METRIC AI_METRIC

python3 <<EOF_PY > "$OUTPUT_FILE"
import json
import os
import datetime

def get_json_data(filepath):
    if filepath and os.path.isfile(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception:
            return None
    return None

build_data = get_json_data(os.environ.get('BUILD_METRIC'))
test_data = get_json_data(os.environ.get('TEST_METRIC'))
perf_data = get_json_data(os.environ.get('PERF_METRIC'))
ai_data = get_json_data(os.environ.get('AI_METRIC'))

print(f"""<!DOCTYPE html>
<html>
<head>
    <title>ANDP Developer Productivity Dashboard</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 1200px; margin: 0 auto; padding: 20px; background-color: #f5f5f7; }}
        h1 {{ color: #1d1d1f; border-bottom: 1px solid #d2d2d7; padding-bottom: 10px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-top: 20px; }}
        .card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        .card h2 {{ margin-top: 0; font-size: 1.2rem; color: #0071e3; }}
        .metric {{ font-size: 2rem; font-weight: bold; margin: 10px 0; }}
        .status {{ padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: bold; }}
        .status-success {{ background: #e2f5e9; color: #15803d; }}
        .status-failed {{ background: #fee2e2; color: #b91c1c; }}
        .list {{ list-style: none; padding: 0; }}
        .list li {{ margin-bottom: 8px; border-bottom: 1px solid #f2f2f2; padding-bottom: 4px; font-size: 0.9rem; }}
    </style>
</head>
<body>
    <h1>ANDP Productivity Dashboard</h1>
    <p>Last updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

    <div class="grid">
        <div class="card">
            <h2>Latest Build</h2>""")

if build_data:
    print(f'<div class="metric">{build_data["value"]}s</div><span class="status status-{build_data["status"].lower()}">{build_data["status"]}</span><p>{build_data["name"]}</p>')
else:
    print("<p>No build data available.</p>")

print("""        </div>
        <div class="card">
            <h2>Latest Tests</h2>""")

if test_data:
    print(f'<div class="metric">{test_data["value"]}s</div><span class="status status-{test_data["status"].lower()}">{test_data["status"]}</span><p>{test_data["name"]}</p>')
else:
    print("<p>No test data available.</p>")

print("""        </div>
        <div class="card">
            <h2>Performance</h2>""")

if perf_data and 'metrics' in perf_data:
    m = perf_data['metrics']
    print(f'<ul class="list"><li>Startup: {m.get("startup_time", "N/A")}s</li><li>Memory: {m.get("memory_usage_mb", "N/A")}MB</li><li>CPU: {m.get("cpu_usage_pct", "N/A")}%</li></ul>')
else:
    print("<p>No performance data available.</p>")

print("""        </div>
    </div>
    <div class="grid">
        <div class="card" style="grid-column: span 2;">
            <h2>AI Quality Insights</h2>""")

if ai_data:
    print('<ul class="list">')
    for category, issues in ai_data.items():
        if issues:
            print(f'<li><strong>{category.replace("_", " ").title()}</strong>')
            print('<ul>')
            for issue in issues[:3]: # Show top 3
                print(f'<li>{issue}</li>')
            print('</ul></li>')
    if not any(ai_data.values()):
        print('<li>✅ No issues detected</li>')
    print('</ul>')
else:
    print("<p>No AI analysis data available.</p>")

print("""        </div>
    </div>
</body>
</html>""")
EOF_PY

echo "Dashboard generated: $OUTPUT_FILE"
