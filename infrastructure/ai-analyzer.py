#!/usr/bin/env python3

import os
import sys
import re
import json

# Bolt Optimization: Pre-compiled regex patterns for performance and single-pass scanning.
TEXT_PATTERN = re.compile(r'Text\("([^"]+)"\)')
UI_COMPONENT_PATTERN = re.compile(r"(Button\(|Image\(|Text\(|Label\(|TextField\(\))")
ACCESSIBILITY_MODIFIER_PATTERN = re.compile(
    r"(accessibilityLabel|accessibilityIdentifier|accessibilityHint|accessibilityValue|accessibilityAddTraits|accessibilityRemoveTraits|accessibilityHidden)"
)
# Dynamic Type check: use of fixed sizes
FONT_FIXED_PATTERN = re.compile(r"\.font\(\.system\(size: [0-9]+\)\)")

# visionOS Compatibility patterns
# 1. Non-adaptive colors (e.g., .black, .white instead of .label, .secondary)
NON_ADAPTIVE_COLOR_PATTERN = re.compile(r"\.foregroundColor\(\.(black|white|red|blue|green)\)")
# 2. Potential missing hover effects on interactive elements
HOVER_EFFECT_MISSING_PATTERN = re.compile(r"(Button\(|Label\()", re.IGNORECASE)
HOVER_EFFECT_PATTERN = re.compile(r"(\.hoverEffect\(|\.onHover\()", re.IGNORECASE)

# 3. Safe Area and Multi-window/Stage Manager
SAFE_AREA_IGNORE_PATTERN = re.compile(r"\.ignoresSafeArea\(", re.IGNORECASE)
MULTI_WINDOW_PATTERN = re.compile(r"(WindowGroup|Window\()", re.IGNORECASE)

# Bolt Optimization: Single regex to quickly filter lines with potential issues.
INTEREST_PATTERN = re.compile(r"(Button\(|Image\(|Text\(|Label\(|TextField\(|\.font\(|\.foregroundColor\(|TODO:|accessibility|\.hoverEffect\(|\.onHover\(|\.ignoresSafeArea\(|WindowGroup|Window\()", re.IGNORECASE)

def analyze_path(path):
    """
    Bolt Optimization: Performs a high-performance single-pass analysis of the codebase.
    Consolidates architectural, dead code, accessibility, and localization checks.
    """
    print(f"Analyzing {path}...")

    results = {
        "architectural_smells": [],
        "dead_code": [],
        "accessibility_risks": [],
        "localization_risks": [],
        "visionos_readiness": [],
        "multi_window_support": [],
        "governance_metrics": {
            "ui_components_total": 0,
            "accessibility_modifiers_found": 0,
            "strings_total": 0,
            "hardcoded_strings_found": 0,
            "safe_area_overrides": 0
        }
    }

    # Bolt Optimization: Exclude heavy/irrelevant directories
    EXCLUDE_DIRS = {'.git', '.xcresult', 'DerivedData', 'build', 'artifacts', 'metrics'}

    file_count = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        for file in files:
            if file.endswith(".swift"):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding='utf-8') as f:
                        lines = f.readlines()
                        line_count = len(lines)

                        if line_count > 500:
                            results["architectural_smells"].append(
                                f"{filepath}:0 - Smell: Massive file detected ({line_count} lines)"
                            )

                        last_accessibility_line = 999999
                        last_hover_line = 999999

                        for i in range(line_count - 1, -1, -1):
                            line = lines[i]
                            line_num = i + 1

                            if not INTEREST_PATTERN.search(line):
                                continue

                            if ACCESSIBILITY_MODIFIER_PATTERN.search(line):
                                last_accessibility_line = i
                                results["governance_metrics"]["accessibility_modifiers_found"] += 1
                            if HOVER_EFFECT_PATTERN.search(line):
                                last_hover_line = i

                            if "TODO:" in line:
                                results["dead_code"].append(f"{filepath}:{line_num} - Note: Unresolved TODO")

                            if UI_COMPONENT_PATTERN.search(line):
                                results["governance_metrics"]["ui_components_total"] += 1
                                if last_accessibility_line - i > 20:
                                    results["accessibility_risks"].append(
                                        f"{filepath}:{line_num} - Risk: UI component missing accessibility modifier"
                                    )

                            if FONT_FIXED_PATTERN.search(line):
                                results["accessibility_risks"].append(
                                    f"{filepath}:{line_num} - Risk: Dynamic Type Violation (Fixed font size)"
                                )

                            hardcoded = TEXT_PATTERN.findall(line)
                            for match in hardcoded:
                                results["governance_metrics"]["strings_total"] += 1
                                if match and not match.isupper():
                                    results["governance_metrics"]["hardcoded_strings_found"] += 1
                                    results["localization_risks"].append(
                                        f"{filepath}:{line_num} - Risk: Possibly hardcoded string '{match}'"
                                    )

                            if NON_ADAPTIVE_COLOR_PATTERN.search(line):
                                results["visionos_readiness"].append(
                                    f"{filepath}:{line_num} - Warning: Non-adaptive color used"
                                )

                            if HOVER_EFFECT_MISSING_PATTERN.search(line):
                                if last_hover_line - i > 10:
                                    results["visionos_readiness"].append(
                                        f"{filepath}:{line_num} - Warning: Interactive element may missing .hoverEffect() or .onHover()"
                                    )

                            if SAFE_AREA_IGNORE_PATTERN.search(line):
                                results["governance_metrics"]["safe_area_overrides"] += 1
                                results["visionos_readiness"].append(
                                    f"{filepath}:{line_num} - Note: Explicit Safe Area override detected"
                                )

                            if MULTI_WINDOW_PATTERN.search(line):
                                results["multi_window_support"].append(
                                    f"{filepath}:{line_num} - Info: Multi-window/Stage Manager support detected"
                                )

                except Exception as e:
                    print(f"Warning: Could not read {filepath}: {e}")
                file_count += 1

    # Calculate final scores
    metrics = results["governance_metrics"]
    metrics["accessibility_score"] = 0
    if metrics["ui_components_total"] > 0:
        # Simple ratio: components that didn't trigger a risk
        risks_count = len(results["accessibility_risks"])
        metrics["accessibility_score"] = max(0, 100 - (risks_count * 100 // metrics["ui_components_total"]))

    metrics["localization_score"] = 0
    if metrics["strings_total"] > 0:
        metrics["localization_score"] = 100 - (metrics["hardcoded_strings_found"] * 100 // metrics["strings_total"])

    print(f"Processed {file_count} files in a single pass.")
    return results

def main():
    path = "Apps"
    if len(sys.argv) > 1:
        path = sys.argv[1]

    print("ANDP AI Quality Analysis & Governance (Bolt Optimized)")
    print("=" * 60)

    analysis_results = analyze_path(path)

    # Scorecard
    m = analysis_results["governance_metrics"]
    print(f"\nGOVERNANCE SCORECARD:")
    print(f"  Accessibility Score: {m['accessibility_score']}%")
    print(f"  Localization Score:  {m['localization_score']}%")

    categories = [
        ("Architectural Smells", "architectural_smells"),
        ("Dead Code", "dead_code"),
        ("Accessibility Risks", "accessibility_risks"),
        ("Localization Risks", "localization_risks"),
        ("visionOS Readiness", "visionos_readiness"),
        ("Multi-window Support", "multi_window_support")
    ]

    found_any = False
    issue_count = 0
    for label, key in categories:
        issues = analysis_results[key]
        if issues:
            issues.sort()
            found_any = True
            print(f"\n{label}:")
            for issue in issues:
                print(f"  - {issue}")
                issue_count += 1

    if not found_any:
        print("\n✅ No major quality risks detected.")
    else:
        print(f"\nFound {issue_count} total issues.")

    print("\n" + "=" * 60)

    os.makedirs("metrics", exist_ok=True)
    with open("metrics/ai_analysis.json", "w") as f:
        json.dump(analysis_results, f, indent=2)

    with open("metrics/governance_scorecard.json", "w") as f:
        json.dump(analysis_results["governance_metrics"], f, indent=2)

if __name__ == "__main__":
    main()
