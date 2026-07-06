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
HOVER_EFFECT_MISSING_PATTERN = re.compile(r"Button\(")
HOVER_EFFECT_PATTERN = re.compile(r"\.hoverEffect\(")

# Bolt Optimization: Single regex to quickly filter lines with potential issues.
# This avoids running multiple regexes on lines that are purely structural or empty.
INTEREST_PATTERN = re.compile(r"(Button\(|Image\(|Text\(|Label\(|TextField\(|\.font\(|\.foregroundColor\(|TODO:|accessibility|\.hoverEffect\()")

def analyze_path(path):
    """
    Bolt Optimization: Performs a high-performance single-pass analysis of the codebase.
    Consolidates architectural, dead code, accessibility, and localization checks.
    Includes directory exclusion to speed up traversal.
    """
    print(f"Analyzing {path}...")

    results = {
        "architectural_smells": [],
        "dead_code": [],
        "accessibility_risks": [],
        "localization_risks": [],
        "visionos_readiness": []
    }

    # Bolt Optimization: Exclude heavy/irrelevant directories
    EXCLUDE_DIRS = {'.git', '.xcresult', 'DerivedData', 'build', 'artifacts'}

    file_count = 0
    for root, dirs, files in os.walk(path):
        # In-place modification of dirs to skip excluded ones
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        for file in files:
            if file.endswith(".swift"):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding='utf-8') as f:
                        lines = f.readlines()
                        line_count = len(lines)

                        # 1. Architectural Smells (Whole file check)
                        if line_count > 500:
                            results["architectural_smells"].append(
                                f"{filepath}:0 - Smell: Massive file detected ({line_count} lines)"
                            )

                        # Bolt Optimization: Use a reverse pass to implement O(1) lookahead state.
                        # This avoids repeated array slicing or multi-line string joining.
                        last_accessibility_line = 999999
                        last_hover_line = 999999

                        for i in range(line_count - 1, -1, -1):
                            line = lines[i]
                            line_num = i + 1

                            # Fast-path: skip lines that don't match any pattern of interest
                            if not INTEREST_PATTERN.search(line):
                                continue

                            # Update lookahead states
                            if ACCESSIBILITY_MODIFIER_PATTERN.search(line):
                                last_accessibility_line = i
                            if HOVER_EFFECT_PATTERN.search(line):
                                last_hover_line = i

                            # 2. Dead Code (TODOs)
                            if "TODO:" in line:
                                results["dead_code"].append(f"{filepath}:{line_num} - Note: Unresolved TODO")

                            # 3. Accessibility Risks & Dynamic Type
                            if UI_COMPONENT_PATTERN.search(line):
                                # Bolt Optimization: O(1) state check vs O(M) pre-indexed search
                                if last_accessibility_line - i > 20:
                                    results["accessibility_risks"].append(
                                        f"{filepath}:{line_num} - Risk: UI component missing accessibility modifier"
                                    )

                            if FONT_FIXED_PATTERN.search(line):
                                results["accessibility_risks"].append(
                                    f"{filepath}:{line_num} - Risk: Dynamic Type Violation (Fixed font size)"
                                )

                            # 4. Localization Risks
                            hardcoded = TEXT_PATTERN.findall(line)
                            for match in hardcoded:
                                if match and not match.isupper():
                                    results["localization_risks"].append(
                                        f"{filepath}:{line_num} - Risk: Possibly hardcoded string '{match}'"
                                    )

                            # 5. visionOS Readiness
                            if NON_ADAPTIVE_COLOR_PATTERN.search(line):
                                results["visionos_readiness"].append(
                                    f"{filepath}:{line_num} - Warning: Non-adaptive color used (use semantic colors for visionOS)"
                                )

                            if HOVER_EFFECT_MISSING_PATTERN.search(line):
                                # Bolt Optimization: O(1) state check vs O(M) pre-indexed search
                                if last_hover_line - i > 10:
                                    results["visionos_readiness"].append(
                                        f"{filepath}:{line_num} - Warning: Interactive element may missing .hoverEffect() for visionOS"
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

    print("ANDP AI Quality Analysis (Bolt Optimized)")
    print("=" * 40)

    # Single-pass execution
    analysis_results = analyze_path(path)

    # Sort and print results
    categories = [
        ("Architectural Smells", "architectural_smells"),
        ("Dead Code", "dead_code"),
        ("Accessibility Risks", "accessibility_risks"),
        ("Localization Risks", "localization_risks"),
        ("visionOS Readiness", "visionos_readiness")
    ]

    found_any = False
    issue_count = 0
    for label, key in categories:
        issues = analysis_results[key]
        if issues:
            # Sort by filename and line number for readability
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

    print("\n" + "=" * 40)

    # Save results for dashboard
    os.makedirs("metrics", exist_ok=True)
    with open("metrics/ai_analysis.json", "w") as f:
        json.dump(analysis_results, f, indent=2)

if __name__ == "__main__":
    main()
