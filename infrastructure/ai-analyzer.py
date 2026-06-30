#!/usr/bin/env python3

import os
import sys
import re
import json

# Bolt Optimization: Pre-compiled regex patterns for performance and single-pass scanning.
TEXT_PATTERN = re.compile(r'Text\("([^"]+)"\)')
# Combining multiple UI patterns into a single regex.
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

                        # Bolt Optimization: Pre-index modifier and hover effect locations to avoid
                        # repeated string joining and regex searching in the loop.
                        modifier_indices = [j for j, l in enumerate(lines) if ACCESSIBILITY_MODIFIER_PATTERN.search(l)]
                        hover_indices = [j for j, l in enumerate(lines) if HOVER_EFFECT_PATTERN.search(l)]

                        # Single pass through lines for other checks
                        for i, line in enumerate(lines):
                            line_num = i + 1

                            # 2. Dead Code (TODOs)
                            if "TODO:" in line:
                                results["dead_code"].append(f"{filepath}:{line_num} - Note: Unresolved TODO")

                            # 3. Accessibility Risks & Dynamic Type
                            if UI_COMPONENT_PATTERN.search(line):
                                # Bolt Optimization: Check pre-indexed indices instead of joining context
                                # Check if any accessibility modifier exists within the next 20 lines.
                                has_modifier = any(i <= idx < i + 20 for idx in modifier_indices)
                                if not has_modifier:
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
                                # Bolt Optimization: Check pre-indexed hover indices
                                # Check if any hover effect exists within the next 10 lines.
                                has_hover = any(i <= idx < i + 10 for idx in hover_indices)
                                if not has_hover:
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
    for label, key in categories:
        issues = analysis_results[key]
        if issues:
            found_any = True
            print(f"\n{label}:")
            for issue in issues:
                print(f"  - {issue}")

    if not found_any:
        print("\n✅ No major quality risks detected.")

    print("\n" + "=" * 40)

    # Save results for dashboard
    os.makedirs("metrics", exist_ok=True)
    with open("metrics/ai_analysis.json", "w") as f:
        json.dump(analysis_results, f, indent=2)

if __name__ == "__main__":
    main()
