#!/bin/bash

# ANDP Dashboard Generator (Bolt Optimized)
# Aggregates metrics and AI insights into an HTML dashboard in a single pass

set -e

OUTPUT_FILE="dashboard.html"
METRICS_DIR="metrics"
VISUAL_DIR="Tests/VisualBaselines/Diffs"

echo "Generating Developer Productivity Dashboard..."

# Bolt Optimization: Consolidate multiple Python spawns and shell forks into a single Python process.
# This reduces execution time by eliminating process overhead and shell fork/pipe chains.
python3 <<EOF > "$OUTPUT_FILE"
import json
import os
import glob
import base64
from datetime import datetime

METRICS_DIR = "$METRICS_DIR"
VISUAL_DIR = "$VISUAL_DIR"

def get_latest_metric(metric_type):
    files = glob.glob(os.path.join(METRICS_DIR, f"{metric_type}*.json"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)

def load_json(path):
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except:
        return None

def get_image_base64(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except:
        return None

build_data = load_json(get_latest_metric("build"))
test_data = load_json(get_latest_metric("test"))
perf_data = load_json(get_latest_metric("perf"))
ai_data = load_json(os.path.join(METRICS_DIR, "ai_analysis.json"))
telemetry_data = load_json(get_latest_metric("telemetry"))
sbom_data = load_json(os.path.join(METRICS_DIR, "sbom.json"))
gov_data = load_json(os.path.join(METRICS_DIR, "governance_scorecard.json"))

# Get visual diffs (Iteration 10)
visual_diffs = []
if os.path.exists(VISUAL_DIR):
    for diff_file in glob.glob(os.path.join(VISUAL_DIR, "*.png")):
        name = os.path.basename(diff_file).replace("_diff.png", "")
        visual_diffs.append({
            "name": name,
            "diff": get_image_base64(diff_file)
        })

now = datetime.now().strftime("%a %b %d %H:%M:%S UTC %Y")

html_header = f"""<!DOCTYPE html>
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
        .visual-diff {{ margin-top: 10px; border: 1px solid #eee; padding: 10px; border-radius: 8px; }}
        .visual-diff img {{ max-width: 100%; height: auto; }}
    </style>
</head>
<body>
    <h1>ANDP Productivity Dashboard</h1>
    <p>Last updated: {now}</p>

    <div class="grid">
        <!-- Governance -->
        <div class="card">
            <h2>Governance Scores</h2>
            {"<div class='metric'>" + str(gov_data.get('accessibility_score', 0)) + "%</div><p>Accessibility</p>" if gov_data else "<p>No data</p>"}
            {"<div class='metric'>" + str(gov_data.get('localization_score', 0)) + "%</div><p>Localization</p>" if gov_data else ""}
            {"<div class='metric'>" + str(gov_data.get('design_compliance_score', 0)) + "%</div><p>Design Compliance</p>" if gov_data else ""}
        </div>

        <!-- Latest Build -->
        <div class="card">
            <h2>Latest Build</h2>"""

print(html_header)

if build_data:
    print(f'            <div class="metric">{build_data["value"]}s</div><span class="status status-{build_data["status"].lower()}">{build_data["status"]}</span><p>{build_data["name"]}</p>')
else:
    print('            <p>No build data available.</p>')

print("""        </div>

        <!-- Test Metrics -->
        <div class="card">
            <h2>Latest Tests</h2>""")

if test_data:
    print(f'            <div class="metric">{test_data["value"]}s</div><span class="status status-{test_data["status"].lower()}">{test_data["status"]}</span><p>{test_data["name"]}</p>')
else:
    print('            <p>No test data available.</p>')

print("""        </div>
    </div>

    <div class="grid">
        <!-- Supply Chain -->
        <div class="card">
            <h2>Supply Chain Security</h2>""")

if sbom_data:
    print(f'            <div class="metric">{len(sbom_data.get("components", []))}</div><p>Dependencies Tracked</p><span class="status status-success">SBOM VALID</span>')
else:
    print('            <p>No SBOM data available.</p>')

print("""        </div>

        <!-- Latest Telemetry -->
        <div class="card">
            <h2>System Health</h2>""")

if telemetry_data:
    print(f'            <ul class="list"><li>ID: {telemetry_data.get("event_id")}</li><li>OS: {telemetry_data.get("environment", {}).get("os")}</li><li>ARCH: {telemetry_data.get("environment", {}).get("arch")}</li></ul>')
else:
    print('            <p>No telemetry data available.</p>')

print("""        </div>

        <!-- Performance -->
        <div class="card">
            <h2>Performance</h2>""")

if perf_data and 'metrics' in perf_data:
    m = perf_data['metrics']
    print(f'            <ul class="list"><li>Startup: {m["startup_time"]}s</li><li>Memory: {m["memory_usage_mb"]}MB</li><li>CPU: {m["cpu_usage_pct"]}%</li></ul>')
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
    for category, issues in ai_data.items():
        if isinstance(issues, list) and issues:
            print(f'                <li><strong>{category.replace("_", " ").title()}</strong>')
            print('                <ul>')
            for issue in issues[:3]:
                print(f'                    <li>{issue}</li>')
            print('                </ul></li>')
    if not any(isinstance(v, list) and v for v in ai_data.values()):
        print('                <li>✅ No issues detected</li>')
    print('            </ul>')
else:
    print('            <p>No AI analysis data available.</p>')

print("""        </div>

        <!-- Visual Regression -->
        <div class="card">
            <h2>Visual Regression Diffs</h2>""")

if visual_diffs:
    for diff in visual_diffs:
        print(f'            <div class="visual-diff">')
        print(f'                <p><strong>{diff["name"]}</strong></p>')
        print(f'                <img src="data:image/png;base64,{diff["diff"]}" alt="diff">')
        print(f'            </div>')
else:
    print('            <p>✅ No visual regressions detected.</p>')

print("""        </div>
    </div>
</body>
</html>""")
EOF

echo "Dashboard generated: $OUTPUT_FILE"
