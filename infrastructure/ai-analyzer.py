#!/usr/bin/env python3

import os
import sys
import re
import json

# Bolt Optimization: Consolidated patterns for high-performance single-pass analysis.
# Pre-compiling regex avoids recompilation in the loop.
TEXT_PATTERN = re.compile(r'Text\("([^"]+)"\)')
UI_COMPONENT_PATTERN = re.compile(r"(Button\(|Image\(|Text\(|Label\(|TextField\(\))")
ACCESSIBILITY_MODIFIER_PATTERN = re.compile(
    r"(accessibilityLabel|accessibilityIdentifier|accessibilityHint|accessibilityValue|accessibilityAddTraits|accessibilityRemoveTraits|accessibilityHidden)"
)
FONT_FIXED_PATTERN = re.compile(r"\.font\(\.system\(size: [0-9]+\)\)")

def analyze_path(path):
    """
    Bolt Optimization: Performs a single-pass analysis of the codebase.
    Reduces I/O and filesystem traversal overhead by combining
    all quality, accessibility, and architectural checks into one pass.
    """
    print(f"Analyzing {path}...")

    results = {
        "architectural_smells": [],
        "dead_code": [],
        "accessibility_risks": [],
        "localization_risks": []
    }

    file_count = 0
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(".swift"):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding='utf-8') as f:
                        lines = f.readlines()
                        content = "".join(lines)
                        line_count = len(lines)

                        # 1. Architectural Smells
                        if line_count > 500:
                            results["architectural_smells"].append(
                                f"Smell: Massive file detected ({line_count} lines) at {filepath}"
                            )

                        # 2. Dead Code (TODOs)
                        if "TODO:" in content:
                            results["dead_code"].append(f"Note: Unresolved TODO in {filepath}")

                        # 3. Accessibility & Localization & Dynamic Type (Line-by-line for context)
                        for i, line in enumerate(lines):
                            # Localization check
                            hardcoded = TEXT_PATTERN.findall(line)
                            for match in hardcoded:
                                if match and not match.isupper():
                                    results["localization_risks"].append(
                                        f"Risk: Possibly hardcoded string '{match}' at {filepath}:{i+1}"
                                    )

                            # Accessibility check (with 20-line lookahead)
                            if UI_COMPONENT_PATTERN.search(line):
                                # Optimized context check: only join what's needed
                                context = "".join(lines[i:i+20])
                                if not ACCESSIBILITY_MODIFIER_PATTERN.search(context):
                                    results["accessibility_risks"].append(
                                        f"Risk: Missing accessibility modifier at {filepath}:{i+1}: {line.strip()}"
                                    )

                            # Dynamic Type check
                            if FONT_FIXED_PATTERN.search(line):
                                results["accessibility_risks"].append(
                                    f"Risk: Dynamic Type Violation (fixed font) at {filepath}:{i+1}: {line.strip()}"
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

    print("ANDP Unified Quality Analysis")
    print("=" * 30)

    # Single-pass execution
    analysis_results = analyze_path(path)

    # Flatten for console output
    issue_count = 0
    for category in ["architectural_smells", "dead_code", "accessibility_risks", "localization_risks"]:
        issues = analysis_results[category]
        if issues:
            print(f"\n[{category.replace('_', ' ').title()}]")
            for issue in issues:
                print(f"- {issue}")
                issue_count += 1

    if issue_count == 0:
        print("✅ No major quality risks detected.")
    else:
        print(f"\nFound {issue_count} total issues.")

    print("=" * 30)

    # Save results for dashboard
    os.makedirs("metrics", exist_ok=True)
    with open("metrics/ai_analysis.json", "w") as f:
        json.dump(analysis_results, f, indent=2)

if __name__ == "__main__":
    main()
