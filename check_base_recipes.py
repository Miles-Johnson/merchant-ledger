# DEPRECATED: Legacy one-off environment probe script retained for reference only. Not part of Gen 3 pipeline/runtime.
import os

base = r'C:\Games\Vintagestory'

# Check for assets directory structure
for root, dirs, files in os.walk(base):
    # Only look at paths containing 'recipes'
    if 'recipes' in root.lower() and 'assets' in root.lower():
        json_count = sum(1 for f in files if f.endswith('.json'))
        if json_count > 0:
            # Show relative path from base
            rel = os.path.relpath(root, base)
            print(f"{rel} ({json_count} json files)")
    # Don't recurse too deep into non-asset dirs
    depth = root.replace(base, '').count(os.sep)
    if depth > 1 and 'assets' not in root.lower():
        dirs.clear()
