#!/usr/bin/env python3

import os
import sys
import re
import json

def analyze_path(path):
    """
    Bolt Optimization: Performs a single-pass analysis of the codebase.
    Reduces I/O and filesystem traversal overhead by 75% by combining
    four separate analysis passes into one.
    """
    print(f"Analyzing {path}...")

    results = {
        "architectural_smells": [],
        "dead_code": [],
        "accessibility_risks": [],
        "localization_risks": []
    }

    # Pre-compile regex for performance
    text_pattern = re.compile(r'Text\("([^"]+)"\)')

    file_count = 0
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(".swift"):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding='utf-8') as f:
                        content = f.read()

                        # 1. Architectural Smells
                        line_count = content.count('\n') + 1
                        if line_count > 500:
                            results["architectural_smells"].append(
                                f"Smell: Massive file detected ({line_count} lines) at {filepath}"
                            )

                        # 2. Dead Code (TODOs)
                        if "TODO:" in content:
                            results["dead_code"].append(f"Note: Unresolved TODO in {filepath}")

                        # 3. Accessibility Risks
                        if "Button(" in content and "accessibilityLabel" not in content:
                            results["accessibility_risks"].append(
                                f"Risk: Button without accessibilityLabel in {filepath}"
                            )

                        # 4. Localization Risks
                        hardcoded = text_pattern.findall(content)
                        for match in hardcoded:
                            if match and not match.isupper():
                                results["localization_risks"].append(
                                    f"Risk: Possibly hardcoded string '{match}' in {filepath}"
                                )
                except Exception as e:
                    print(f"Warning: Could not read {filepath}: {e}")
                file_count += 1

    print(f"Processed {file_count} files in a single pass.")
    return results

def main():
    path = "Apps"
    if len(sys.argv) > 1:
        path = sys.argv[1]

    print("ANDP AI Quality Analysis")
    print("=" * 30)

    # Single-pass execution
    analysis_results = analyze_path(path)

    # Flatten for console output
    all_issues = []
    for category in ["architectural_smells", "dead_code", "accessibility_risks", "localization_risks"]:
        issues = analysis_results[category]
        all_issues.extend(issues)

    if not all_issues:
        print("✅ No major quality risks detected.")
    else:
        for issue in all_issues:
            print(f"- {issue}")

    print("=" * 30)

    # Save results for dashboard
    os.makedirs("metrics", exist_ok=True)
    with open("metrics/ai_analysis.json", "w") as f:
        json.dump(analysis_results, f, indent=2)

if __name__ == "__main__":
    main()
