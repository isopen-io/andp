import os
import sys
import re

def scan_accessibility(directory):
    print(f"Scanning for accessibility in {directory}...")
    swift_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".swift"):
                swift_files.append(os.path.join(root, file))

    issues = []
    # Patterns for UI components
    ui_patterns = [
        r"Button\(",
        r"Image\(",
        r"Text\(",
        r"Label\(",
        r"TextField\("
    ]

    # Accessibility modifiers to check
    accessibility_modifiers = [
        "accessibilityLabel",
        "accessibilityIdentifier",
        "accessibilityHint",
        "accessibilityValue",
        "accessibilityAddTraits",
        "accessibilityRemoveTraits"
    ]

    # Dynamic Type check: use of fixed sizes
    font_fixed_pattern = r"\.font\(\.system\(size: [0-9]+\)\)"

    for file_path in swift_files:
        with open(file_path, "r") as f:
            lines = f.readlines()
            for i, line in enumerate(lines):
                # Check for UI components missing labels
                for pattern in ui_patterns:
                    if re.search(pattern, line):
                        # Check context (next 10 lines) for any accessibility modifier
                        context = "".join(lines[i:i+10])
                        if not any(mod in context for mod in accessibility_modifiers):
                            issues.append(f"{file_path}:{i+1} - Missing accessibility modifier for component: {line.strip()}")

                # Check for fixed fonts (Dynamic Type violation)
                if re.search(font_fixed_pattern, line):
                    issues.append(f"{file_path}:{i+1} - Dynamic Type Violation: Fixed font size used: {line.strip()}")

    return issues

if __name__ == "__main__":
    path = "Apps/Meeshy"
    if len(sys.argv) > 1:
        path = sys.argv[1]

    violations = scan_accessibility(path)

    print("\nAccessibility Audit Report:")
    print("-" * 25)
    if not violations:
        print("✅ No major accessibility issues found.")
    else:
        for v in violations:
            print(f"❌ {v}")
        print(f"\nFound {len(violations)} potential issues.")
    print("-" * 25)
