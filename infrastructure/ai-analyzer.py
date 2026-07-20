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
# Note: Label( is deliberately excluded — a Label is not interactive by itself, and in the
# dominant Button { Label } pattern it would consume the hover modifier during the reverse
# pass and falsely flag the enclosing Button.
HOVER_EFFECT_MISSING_PATTERN = re.compile(r"(?<![A-Za-z])Button\(")
HOVER_EFFECT_PATTERN = re.compile(r"(\.hoverEffect\(|\.onHover\()")

# 3. Multi-window/Stage Manager support (Iteration 9)
MULTI_WINDOW_PATTERN = re.compile(r"(WindowGroup|Window\()")

# Design & Responsiveness patterns (Iteration 10)
SAFE_AREA_OVERRIDE_PATTERN = re.compile(r"\.ignoresSafeArea\(")
FIXED_FRAME_PATTERN = re.compile(r"\.frame\(width: [0-9]+(\.[0-9]+)?, height: [0-9]+(\.[0-9]+)?\)")
RESTRICTIVE_NAV_STYLE_PATTERN = re.compile(r"\.navigationViewStyle\(\.stack\)")

# Bolt Optimization: Single regex to quickly filter lines with potential issues.
# This avoids running multiple regexes on lines that are purely structural or empty.
INTEREST_PATTERN = re.compile(
    r"(Button\(|Image\(|Text\(|Label\(|TextField\(|\.font\(|\.foregroundColor\(|TODO:|accessibility|\.hoverEffect\(|\.onHover\(|\.ignoresSafeArea\(|\.frame\(width:|\.navigationViewStyle\(\.stack\)|HStack|VStack|ZStack|WindowGroup|Window\()"
)

# Iteration 11: Patterns for dead code detection
PRIVATE_DECL_PATTERN = re.compile(r"private (?:func|var|let) ([a-zA-Z0-9_]+)")

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
        "visionos_readiness": [],
        "design_violations": [],
        "multi_window_support": [],
        "governance_metrics": {
            "ui_components_total": 0,
            "accessibility_modifiers_found": 0,
            "strings_total": 0,
            "hardcoded_strings_found": 0,
            "safe_area_overrides": 0,
            "design_compliance_score": 100
        }
    }

    # Bolt Optimization: Exclude heavy/irrelevant directories
    EXCLUDE_DIRS = {'.git', '.xcresult', 'DerivedData', 'build', 'artifacts', 'metrics'}

    file_count = 0
    design_issues_count = 0
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

                        # 1. Architectural Smells & Dead Code Heuristics (Iteration 11)
                        if line_count > 500:
                            results["architectural_smells"].append(
                                f"{filepath}:0 - Smell: Massive file detected ({line_count} lines)"
                            )

                        # Heuristic for deeply nested containers
                        nesting_level = 0
                        private_decls = {} # name -> line_num
                        full_content = "".join(lines)

                        for idx, line in enumerate(lines):
                            # Nesting check
                            if any(c in line and "{" in line for c in ["HStack", "VStack", "ZStack"]):
                                nesting_level += 1
                                if nesting_level > 5:
                                    results["architectural_smells"].append(
                                        f"{filepath}:{idx+1} - Smell: Deeply nested SwiftUI container (depth {nesting_level})"
                                    )
                            if "}" in line and nesting_level > 0:
                                nesting_level -= 1

                            # Dead code heuristic: collect private decls
                            match = PRIVATE_DECL_PATTERN.search(line)
                            if match:
                                name = match.group(1)
                                private_decls[name] = idx + 1

                        # Verify if private decls are referenced
                        for name, line_num in private_decls.items():
                            # Count occurrences; if only 1, it's just the declaration
                            if full_content.count(name) <= 1:
                                results["dead_code"].append(
                                    f"{filepath}:{line_num} - Note: Potentially unused private declaration '{name}'"
                                )

                        # Bolt Optimization: Use a reverse pass to implement O(1) lookahead state.
                        # This works because SwiftUI modifiers appear AFTER the component they modify.
                        # By going from bottom to top, we see the modifier before the component.
                        last_accessibility_line = -1
                        last_hover_line = -1

                        for i in range(line_count - 1, -1, -1):
                            line = lines[i]
                            line_num = i + 1

                            # Fast-path: skip lines that don't match any pattern of interest
                            if not INTEREST_PATTERN.search(line):
                                continue

                            # Update lookahead states
                            if ACCESSIBILITY_MODIFIER_PATTERN.search(line):
                                last_accessibility_line = i
                                results["governance_metrics"]["accessibility_modifiers_found"] += 1
                            if HOVER_EFFECT_PATTERN.search(line):
                                last_hover_line = i

                            # 2. Dead Code (TODOs)
                            if "TODO:" in line:
                                results["dead_code"].append(f"{filepath}:{line_num} - Note: Unresolved TODO")

                            # 3. Accessibility Risks & Dynamic Type
                            if UI_COMPONENT_PATTERN.search(line):
                                results["governance_metrics"]["ui_components_total"] += 1
                                # Check if a modifier was seen within the last 20 lines (below this line)
                                if last_accessibility_line == -1 or (last_accessibility_line - i > 20):
                                    results["accessibility_risks"].append(
                                        f"{filepath}:{line_num} - Risk: UI component missing accessibility modifier"
                                    )
                                last_accessibility_line = -1 # Reset for next component

                            if FONT_FIXED_PATTERN.search(line):
                                results["accessibility_risks"].append(
                                    f"{filepath}:{line_num} - Risk: Dynamic Type Violation (Fixed font size)"
                                )

                            # 4. Localization Risks
                            hardcoded = TEXT_PATTERN.findall(line)
                            for match in hardcoded:
                                results["governance_metrics"]["strings_total"] += 1
                                if match and not match.isupper():
                                    results["governance_metrics"]["hardcoded_strings_found"] += 1
                                    results["localization_risks"].append(
                                        f"{filepath}:{line_num} - Risk: Possibly hardcoded string '{match}'"
                                    )

                            # 5. visionOS Readiness
                            if NON_ADAPTIVE_COLOR_PATTERN.search(line):
                                results["visionos_readiness"].append(
                                    f"{filepath}:{line_num} - Warning: Non-adaptive color used (use semantic colors for visionOS)"
                                )

                            if HOVER_EFFECT_MISSING_PATTERN.search(line):
                                # Check if a hover effect was seen within the last 10 lines (below this line)
                                if last_hover_line == -1 or (last_hover_line - i > 10):
                                    results["visionos_readiness"].append(
                                        f"{filepath}:{line_num} - Warning: Interactive element may missing .hoverEffect() or .onHover()"
                                    )
                                last_hover_line = -1 # Reset for next component

                            # 6. Design & Responsiveness (Iteration 10)
                            if SAFE_AREA_OVERRIDE_PATTERN.search(line):
                                results["design_violations"].append(
                                    f"{filepath}:{line_num} - Design: Safe Area override detected (.ignoresSafeArea())"
                                )
                                results["governance_metrics"]["safe_area_overrides"] += 1
                                design_issues_count += 1

                            if FIXED_FRAME_PATTERN.search(line):
                                results["design_violations"].append(
                                    f"{filepath}:{line_num} - Design: Fixed frame detected (prefer flexible constraints)"
                                )
                                design_issues_count += 1

                            if RESTRICTIVE_NAV_STYLE_PATTERN.search(line):
                                results["design_violations"].append(
                                    f"{filepath}:{line_num} - Design: Restrictive navigation style (.stack) may break iPad layout"
                                )
                                design_issues_count += 1

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

    # Iteration 10 Design Compliance Score
    if file_count > 0:
        metrics["design_compliance_score"] = max(0, 100 - (design_issues_count * 10 // file_count))

    print(f"Processed {file_count} files in a single pass.")
    return results

def main():
    path = "Apps"
    if len(sys.argv) > 1:
        path = sys.argv[1]

    print("ANDP AI Quality Analysis & Governance (Bolt Optimized)")
    print("=" * 60)

    # Single-pass execution
    analysis_results = analyze_path(path)

    # Scorecard
    m = analysis_results["governance_metrics"]
    print(f"\nGOVERNANCE SCORECARD:")
    print(f"  Accessibility Score:     {m['accessibility_score']}%")
    print(f"  Localization Score:      {m['localization_score']}%")
    print(f"  Design Compliance Score: {m['design_compliance_score']}%")

    categories = [
        ("Architectural Smells", "architectural_smells"),
        ("Dead Code", "dead_code"),
        ("Accessibility Risks", "accessibility_risks"),
        ("Localization Risks", "localization_risks"),
        ("visionOS Readiness", "visionos_readiness"),
        ("Design Violations", "design_violations"),
        ("Multi-window Support", "multi_window_support")
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

    print("\n" + "=" * 60)

    # Save results for dashboard
    os.makedirs("metrics", exist_ok=True)
    with open("metrics/ai_analysis.json", "w") as f:
        json.dump(analysis_results, f, indent=2)

    with open("metrics/governance_scorecard.json", "w") as f:
        json.dump(analysis_results["governance_metrics"], f, indent=2)

if __name__ == "__main__":
    main()
