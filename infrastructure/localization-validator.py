import os
import re
import sys

# RTL Compatibility: Check for hardcoded directional words that should probably be localized or avoided
DIRECTIONAL_PATTERN = re.compile(r'\b(left|right|leading|trailing)\b', re.IGNORECASE)

def parse_strings_file(filepath):
    """Simple parser for .strings files."""
    keys = {}
    if not os.path.exists(filepath):
        return keys

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        # Regex to find "key" = "value";
        matches = re.findall(r'"([^"]+)"\s*=\s*"([^"]*)"\s*;', content)
        for key, value in matches:
            keys[key] = value
    return keys

def validate_localization(base_path):
    print(f"Validating localization in {base_path}...")

    # Find all .lproj directories
    lproj_dirs = [d for d in os.listdir(base_path) if d.endswith('.lproj')]

    if not lproj_dirs:
        print("No .lproj directories found.")
        return True

    # Use Base or en as reference
    reference_lang = 'en.lproj' if 'en.lproj' in lproj_dirs else lproj_dirs[0]
    print(f"Using {reference_lang} as reference.")

    # Get all .strings files in reference
    ref_dir = os.path.join(base_path, reference_lang)
    strings_files = [f for f in os.listdir(ref_dir) if f.endswith('.strings')]

    all_passed = True

    for strings_file in strings_files:
        ref_data = parse_strings_file(os.path.join(ref_dir, strings_file))
        ref_keys = set(ref_data.keys())
        print(f"  Checking {strings_file} ({len(ref_keys)} keys)...")

        # RTL / Directional Check on reference
        for key, value in ref_data.items():
            if DIRECTIONAL_PATTERN.search(value):
                print(f"⚠️  Warning: '{strings_file}' contains directional word in key '{key}': \"{value}\". Ensure this is handled for RTL.")

        for lproj in lproj_dirs:
            if lproj == reference_lang:
                continue

            target_path = os.path.join(base_path, lproj, strings_file)
            target_data = parse_strings_file(target_path)
            target_keys = set(target_data.keys())

            missing = ref_keys - target_keys
            if missing:
                print(f"❌ {lproj}/{strings_file}: Missing keys: {missing}")
                all_passed = False
            else:
                print(f"✅ {lproj}/{strings_file}: All keys present.")

            # Check for empty translations
            for key, value in target_data.items():
                if not value.strip():
                    print(f"⚠️  Warning: {lproj}/{strings_file}: Empty translation for key '{key}'")

    return all_passed

if __name__ == "__main__":
    # Default search paths if none provided
    search_paths = ["Apps/Meeshy"]
    if len(sys.argv) > 1:
        search_paths = sys.argv[1:]

    success = True
    for path in search_paths:
        if not validate_localization(path):
            success = False

    if success:
        print("\nLocalization validation PASSED.")
        sys.exit(0)
    else:
        print("\nLocalization validation FAILED.")
        sys.exit(1)
