#!/bin/bash

# ANDP Dashboard Generator
# Aggregates metrics and AI insights into an HTML dashboard

set -e

OUTPUT_FILE="dashboard.html"
METRICS_DIR="metrics"

echo "Generating Developer Productivity Dashboard..."

# Bolt Optimization: Consolidated multiple Python spawns and shell forks into a single Python process.
# This eliminates redundant interpreter startup overhead (~0.3s per spawn) and shell forks for file discovery.
python3 <<EOF_PY > "$OUTPUT_FILE"
import json
import os
import glob
import datetime

def get_latest_metric(m_dir, m_type):
    try:
        # Match original shell glob pattern: ${type}*.json
        files = glob.glob(os.path.join(m_dir, f"{m_type}*.json"))
        if not files:
            return None
        return max(files, key=os.path.getmtime)
    except:
        return None

def load_json(filepath):
    if not filepath or not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except:
        return None

build_data = load_json(get_latest_metric('$METRICS_DIR', 'build'))
test_data = load_json(get_latest_metric('$METRICS_DIR', 'test'))
perf_data = load_json(get_latest_metric('$METRICS_DIR', 'perf'))
ai_data = load_json(os.path.join('$METRICS_DIR', 'ai_analysis.json'))

# Match system date output format as closely as possible
now = datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y")

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

if build_data:
    val = build_data.get('value', 'N/A')
    status = build_data.get('status', 'UNKNOWN')
    name = build_data.get('name', 'N/A')
    print(f'            <div class="metric">{val}s</div>')
    print(f'            <span class="status status-{status.lower()}">{status}</span>')
    print(f'            <p>{name}</p>')
else:
    print('            <p>No build data available.</p>')

print("""        </div>

        <!-- Test Metrics -->
        <div class="card">
            <h2>Latest Tests</h2>""")

if test_data:
    val = test_data.get('value', 'N/A')
    status = test_data.get('status', 'UNKNOWN')
    name = test_data.get('name', 'N/A')
    print(f'            <div class="metric">{val}s</div>')
    print(f'            <span class="status status-{status.lower()}">{status}</span>')
    print(f'            <p>{name}</p>')
else:
    print('            <p>No test data available.</p>')

print("""        </div>

        <!-- Performance Metrics -->
        <div class="card">
            <h2>Performance</h2>""")

if perf_data:
    m = perf_data.get('metrics', {})
    print('            <ul class="list">')
    print(f'                <li>Startup: {m.get("startup_time", "N/A")}s</li>')
    print(f'                <li>Memory: {m.get("memory_usage_mb", "N/A")}MB</li>')
    print(f'                <li>CPU: {m.get("cpu_usage_pct", "N/A")}%</li>')
    print('            </ul>')
else:
    print('            <p>No performance data available.</p>')

print("""        </div>
    </div>

    <div class="grid">
        <!-- AI Insights -->
        <div class="card" style="grid-column: span 2;">
            <h2>AI Quality Insights</h2>""")

if ai_data:
    print('            <ul class="list">')
    has_any = False
    for category, issues in ai_data.items():
        if issues:
            has_any = True
            cat_name = category.replace("_", " ").title()
            print(f'                <li><strong>{cat_name}</strong>')
            print('                    <ul>')
            for issue in issues[:3]:
                print(f'                        <li>{issue}</li>')
            print('                    </ul>')
            print('                </li>')
    if not has_any:
        print('                <li>✅ No issues detected</li>')
    print('            </ul>')
else:
    print('            <p>No AI analysis data available.</p>')

print("""        </div>
    </div>
</body>
</html>""")
EOF_PY

echo "Dashboard generated: $OUTPUT_FILE"
