#!/bin/bash

# ANDP Dashboard Generator
# Aggregates metrics and AI insights into an HTML dashboard

set -e

OUTPUT_FILE="dashboard.html"
METRICS_DIR="metrics"

echo "Generating Developer Productivity Dashboard..."

# Bolt Optimization: Consolidate everything into a single Python process to minimize startup overhead.
# This replaces multiple shell forks (ls, head, date) and multiple python3 -c spawns.
# Spawning Python has a fixed overhead (~0.3s). Doing it once instead of 4-5 times saves ~1.2s.
python3 <<'EOF' > "$OUTPUT_FILE"
import json
import os
import glob
from datetime import datetime, timezone

def get_latest_metric(metrics_dir, type_prefix):
    files = glob.glob(os.path.join(metrics_dir, f"{type_prefix}*.json"))
    if not files:
        return None
    try:
        return max(files, key=os.path.getmtime)
    except Exception:
        return None

METRICS_DIR = "metrics"
BUILD_METRIC = get_latest_metric(METRICS_DIR, "build")
TEST_METRIC = get_latest_metric(METRICS_DIR, "test")
PERF_METRIC = get_latest_metric(METRICS_DIR, "perf")
AI_METRIC = os.path.join(METRICS_DIR, "ai_analysis.json")

print("<!DOCTYPE html>")
print("<html>")
print("<head>")
print("    <title>ANDP Developer Productivity Dashboard</title>")
print("    <style>")
print("        body { font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 1200px; margin: 0 auto; padding: 20px; background-color: #f5f5f7; }")
print("        h1 { color: #1d1d1f; border-bottom: 1px solid #d2d2d7; padding-bottom: 10px; }")
print("        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-top: 20px; }")
print("        .card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }")
print("        .card h2 { margin-top: 0; font-size: 1.2rem; color: #0071e3; }")
print("        .metric { font-size: 2rem; font-weight: bold; margin: 10px 0; }")
print("        .status { padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: bold; }")
print("        .status-success { background: #e2f5e9; color: #15803d; }")
print("        .status-failed { background: #fee2e2; color: #b91c1c; }")
print("        .list { list-style: none; padding: 0; }")
print("        .list li { margin-bottom: 8px; border-bottom: 1px solid #f2f2f2; padding-bottom: 4px; font-size: 0.9rem; }")
print("    </style>")
print("</head>")
print("<body>")
print("    <h1>ANDP Productivity Dashboard</h1>")
# Use timezone-aware UTC datetime
print(f"    <p>Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>")

print("    <div class=\"grid\">")
print("        <!-- Build Metrics -->")
print("        <div class=\"card\">")
print("            <h2>Latest Build</h2>")

if BUILD_METRIC and os.path.exists(BUILD_METRIC):
    try:
        with open(BUILD_METRIC) as f:
            d = json.load(f)
            print(f'            <div class="metric">{d["value"]}s</div>')
            print(f'            <span class="status status-{d["status"].lower()}">{d["status"]}</span>')
            print(f'            <p>{d["name"]}</p>')
    except Exception as e:
        print(f"<p>Error loading build data: {e}</p>")
else:
    print("            <p>No build data available.</p>")

print("        </div>")

print("        <!-- Test Metrics -->")
print("        <div class=\"card\">")
print("            <h2>Latest Tests</h2>")

if TEST_METRIC and os.path.exists(TEST_METRIC):
    try:
        with open(TEST_METRIC) as f:
            d = json.load(f)
            print(f'            <div class="metric">{d["value"]}s</div>')
            print(f'            <span class="status status-{d["status"].lower()}">{d["status"]}</span>')
            print(f'            <p>{d["name"]}</p>')
    except Exception as e:
        print(f"<p>Error loading test data: {e}</p>")
else:
    print("            <p>No test data available.</p>")

print("        </div>")

print("        <!-- Performance Metrics -->")
print("        <div class=\"card\">")
print("            <h2>Performance</h2>")

if PERF_METRIC and os.path.exists(PERF_METRIC):
    try:
        with open(PERF_METRIC) as f:
            data = json.load(f)
            d = data.get('metrics', {})
            print('            <ul class="list">')
            print(f'                <li>Startup: {d.get("startup_time", "N/A")}s</li>')
            print(f'                <li>Memory: {d.get("memory_usage_mb", "N/A")}MB</li>')
            print(f'                <li>CPU: {d.get("cpu_usage_pct", "N/A")}%</li>')
            print('            </ul>')
    except Exception as e:
        print(f"<p>Error loading performance data: {e}</p>")
else:
    print("            <p>No performance data available.</p>")

print("        </div>")
print("    </div>")

print("    <div class=\"grid\">")
print("        <!-- AI Insights -->")
print("        <div class=\"card\" style=\"grid-column: span 2;\">")
print("            <h2>AI Quality Insights</h2>")

if os.path.exists(AI_METRIC):
    try:
        with open(AI_METRIC) as f:
            data = json.load(f)
            print('            <ul class="list">')
            for category, issues in data.items():
                if issues:
                    print(f'                <li><strong>{category.replace("_", " ").title()}</strong>')
                    print('                    <ul>')
                    for issue in issues[:3]: # Show top 3
                        print(f'                        <li>{issue}</li>')
                    print('                    </ul>')
                    print('                </li>')
            if not any(data.values()):
                print('                <li>✅ No issues detected</li>')
            print('            </ul>')
    except Exception as e:
        print(f"<p>Error loading AI analysis data: {e}</p>")
else:
    print("            <p>No AI analysis data available.</p>")

print("        </div>")
print("    </div>")
print("</body>")
print("</html>")
EOF

echo "Dashboard generated: $OUTPUT_FILE"
