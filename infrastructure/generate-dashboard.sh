#!/bin/bash

# ANDP Dashboard Generator
# Aggregates metrics and AI insights into an HTML dashboard

set -e

OUTPUT_FILE="dashboard.html"
METRICS_DIR="metrics"

echo "Generating Developer Productivity Dashboard..."

# Bolt Optimization: Consolidated multiple Python spawns and shell forks (like 'ls -t | head')
# into a single Python process. This reduces interpreter startup overhead (~0.3s per spawn)
# and streamlines the I/O.
python3 <<EOF > "$OUTPUT_FILE"
import json
import os
import glob
from datetime import datetime

METRICS_DIR = "$METRICS_DIR"

def get_latest_metric(metric_type):
    files = glob.glob(os.path.join(METRICS_DIR, f"{metric_type}_*.json"))
    if not files:
        return None
    # Sort by mtime descending
    files.sort(key=os.path.getmtime, reverse=True)
    try:
        with open(files[0], 'r') as f:
            return json.load(f)
    except Exception:
        return None

build_metric = get_latest_metric("build")
test_metric = get_latest_metric("test")
perf_metric = get_latest_metric("perf")

ai_metric_path = os.path.join(METRICS_DIR, "ai_analysis.json")
ai_data = None
if os.path.exists(ai_metric_path):
    try:
        with open(ai_metric_path, 'r') as f:
            ai_data = json.load(f)
    except Exception:
        pass

now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
    <p>Last updated: {now}</p>

    <div class="grid">
        <!-- Build Metrics -->
        <div class="card">
            <h2>Latest Build</h2>""")

if build_metric:
    status = build_metric.get('status', 'UNKNOWN')
    print(f"""<div class="metric">{build_metric.get('value', 'N/A')}s</div>
            <span class="status status-{status.lower()}">{status}</span>
            <p>{build_metric.get('name', '')}</p>""")
else:
    print("<p>No build data available.</p>")

print("""        </div>

        <!-- Test Metrics -->
        <div class="card">
            <h2>Latest Tests</h2>""")

if test_metric:
    status = test_metric.get('status', 'UNKNOWN')
    print(f"""<div class="metric">{test_metric.get('value', 'N/A')}s</div>
            <span class="status status-{status.lower()}">{status}</span>
            <p>{test_metric.get('name', '')}</p>""")
else:
    print("<p>No test data available.</p>")

print("""        </div>

        <!-- Performance Metrics -->
        <div class="card">
            <h2>Performance</h2>""")

if perf_metric and 'metrics' in perf_metric:
    d = perf_metric['metrics']
    print(f"""<ul class="list">
                <li>Startup: {d.get('startup_time', 'N/A')}s</li>
                <li>Memory: {d.get('memory_usage_mb', 'N/A')}MB</li>
                <li>CPU: {d.get('cpu_usage_pct', 'N/A')}%</li>
            </ul>""")
else:
    print("<p>No performance data available.</p>")

print("""        </div>
    </div>

    <div class="grid">
        <!-- AI Insights -->
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
EOF

echo "Dashboard generated: $OUTPUT_FILE"
