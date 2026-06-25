#!/usr/bin/env python3

import os
import sys
import re

def analyze_architectural_smells(path):
    print(f"Analyzing architectural smells in {path}...")
    issues = []
    # Check for Massive View Controllers (simplified: very long files)
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(".swift"):
                filepath = os.path.join(root, file)
                with open(filepath, "r") as f:
                    lines = f.readlines()
                    if len(lines) > 500:
                        issues.append(f"Smell: Massive file detected ({len(lines)} lines) at {filepath}")

    # Check for hardcoded secrets (simplified)
    # This is already partially handled by security-auditor, but we can add UI-related ones
    return issues

def analyze_dead_code(path):
    print(f"Analyzing dead code in {path}...")
    # Simplified: look for TODOs and FIXMEs as proxy for incomplete/dead-ish code
    # Real implementation would use something like Periphery
    issues = []
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(".swift"):
                filepath = os.path.join(root, file)
                with open(filepath, "r") as f:
                    content = f.read()
                    if "TODO:" in content:
                        issues.append(f"Note: Unresolved TODO in {filepath}")
    return issues

def analyze_accessibility_risks(path):
    print(f"Analyzing accessibility risks in {path}...")
    issues = []
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(".swift"):
                filepath = os.path.join(root, file)
                with open(filepath, "r") as f:
                    content = f.read()
                    if "Button(" in content and "accessibilityLabel" not in content:
                        issues.append(f"Risk: Button without accessibilityLabel in {filepath}")
    return issues

def analyze_localization_risks(path):
    print(f"Analyzing localization risks in {path}...")
    issues = []
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(".swift"):
                filepath = os.path.join(root, file)
                with open(filepath, "r") as f:
                    content = f.read()
                    # Look for hardcoded strings in Text()
                    hardcoded = re.findall(r'Text\("([^"]+)"\)', content)
                    for match in hardcoded:
                        if match and not match.isupper(): # Basic heuristic for non-key strings
                            issues.append(f"Risk: Possibly hardcoded string '{match}' in {filepath}")
    return issues

def main():
    path = "Apps"
    if len(sys.argv) > 1:
        path = sys.argv[1]

    print("ANDP AI Quality Analysis")
    print("=" * 30)

    smells = analyze_architectural_smells(path)
    dead_code = analyze_dead_code(path)
    accessibility = analyze_accessibility_risks(path)
    localization = analyze_localization_risks(path)

    all_issues = smells + dead_code + accessibility + localization

    if not all_issues:
        print("✅ No major quality risks detected.")
    else:
        for issue in all_issues:
            print(f"- {issue}")

    print("=" * 30)

    # Save results for dashboard
    import json
    results = {
        "architectural_smells": smells,
        "dead_code": dead_code,
        "accessibility_risks": accessibility,
        "localization_risks": localization
    }

    os.makedirs("metrics", exist_ok=True)
    with open("metrics/ai_analysis.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
