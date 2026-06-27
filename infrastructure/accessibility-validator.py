import os
import sys
import re

# Bolt Optimization: Pre-compiled regex patterns for performance.
# Combining multiple UI patterns into a single regex reduces search calls by 5x.
UI_COMPONENT_PATTERN = re.compile(r"(Button\(|Image\(|Text\(|Label\(|TextField\(\))")
ACCESSIBILITY_MODIFIER_PATTERN = re.compile(
    r"(accessibilityLabel|accessibilityIdentifier|accessibilityHint|accessibilityValue|accessibilityAddTraits|accessibilityRemoveTraits|accessibilityHidden)"
)
# Dynamic Type check: use of fixed sizes
FONT_FIXED_PATTERN = re.compile(r"\.font\(\.system\(size: [0-9]+\)\)")

def scan_accessibility(directory):
    print(f"Scanning for accessibility in {directory}...")
    swift_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".swift"):
                swift_files.append(os.path.join(root, file))

    issues = []

    for file_path in swift_files:
        try:
            with open(file_path, "r", encoding='utf-8') as f:
                lines = f.readlines()
                for i, line in enumerate(lines):
                    # Check for UI components missing labels
                    if UI_COMPONENT_PATTERN.search(line):
                        # Check context (next 20 lines) for any accessibility modifier
                        # Bolt Optimization: Use pre-compiled regex for modifier check
                        context = "".join(lines[i:i+20])
                        if not ACCESSIBILITY_MODIFIER_PATTERN.search(context):
                            issues.append(f"{file_path}:{i+1} - Missing accessibility modifier for component: {line.strip()}")

                    # Check for fixed fonts (Dynamic Type violation)
                    if FONT_FIXED_PATTERN.search(line):
                        issues.append(f"{file_path}:{i+1} - Dynamic Type Violation: Fixed font size used: {line.strip()}")
        except Exception as e:
            print(f"Warning: Could not read {file_path}: {e}")

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
