import os
import re
import sys

def parse_strings_file(filepath):
    """Simple parser for .strings files."""
    keys = set()
    if not os.path.exists(filepath):
        return keys

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        # Regex to find "key" = "value";
        matches = re.findall(r'"([^"]+)"\s*=\s*"[^"]*"\s*;', content)
        for match in matches:
            keys.add(match)
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
        ref_keys = parse_strings_file(os.path.join(ref_dir, strings_file))
        print(f"  Checking {strings_file} ({len(ref_keys)} keys)...")

        for lproj in lproj_dirs:
            if lproj == reference_lang:
                continue

            target_path = os.path.join(base_path, lproj, strings_file)
            target_keys = parse_strings_file(target_path)

            missing = ref_keys - target_keys
            if missing:
                print(f"❌ {lproj}/{strings_file}: Missing keys: {missing}")
                all_passed = False
            else:
                print(f"✅ {lproj}/{strings_file}: All keys present.")

    return all_passed

if __name__ == "__main__":
    search_path = "Apps/Meeshy/Resources"
    if len(sys.argv) > 1:
        search_path = sys.argv[1]

    if validate_localization(search_path):
        print("\nLocalization validation PASSED.")
        sys.exit(0)
    else:
        print("\nLocalization validation FAILED.")
        sys.exit(1)
