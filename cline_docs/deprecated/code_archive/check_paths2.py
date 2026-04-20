# DEPRECATED: Legacy one-off environment probe script retained for reference only. Not part of Gen 3 pipeline/runtime.
import os, glob, json

# Try to find Vintagestory.exe via common locations and registry-like hints
# Check if clientsettings has install path
try:
    with open(r'C:\Users\Kjol\AppData\Roaming\VintagestoryData\clientsettings.json', 'r') as f:
        cs = json.load(f)
    print("=== clientsettings.json keys ===")
    for k, v in cs.items():
        if 'path' in k.lower() or 'install' in k.lower() or 'dir' in k.lower() or 'game' in k.lower():
            print(f"  {k}: {v}")
except Exception as e:
    print(f"Error reading clientsettings: {e}")

# Check if there's a survival or game folder in Cache/unpack (base game might be there)
unpack = r'C:\Users\Kjol\AppData\Roaming\VintagestoryData\Cache\unpack'
print("\n=== Looking for 'survival' or 'game' in unpack entries ===")
for entry in os.listdir(unpack):
    if 'survival' in entry.lower() or entry.lower().startswith('game'):
        print(f"  {entry}")

# Check a couple mod folders for recipe structure
print("\n=== Exploring recipe structures in first few mods ===")
count = 0
for entry in os.listdir(unpack):
    mod_path = os.path.join(unpack, entry)
    if not os.path.isdir(mod_path):
        continue
    # Walk for recipes
    for root, dirs, files in os.walk(mod_path):
        if 'recipes' in root.lower():
            json_files = [f for f in files if f.endswith('.json')]
            if json_files:
                print(f"\n  Mod: {entry}")
                print(f"  Recipe path: {root}")
                print(f"  JSON files ({len(json_files)}): {json_files[:5]}")
                # Read one sample
                sample = os.path.join(root, json_files[0])
                try:
                    with open(sample, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        print(f"  Sample (array, len={len(data)}): keys={list(data[0].keys()) if data else 'empty'}")
                    else:
                        print(f"  Sample keys: {list(data.keys())}")
                        if 'output' in data:
                            print(f"  Output: {data['output']}")
                        if 'ingredientPattern' in data:
                            print(f"  Has ingredientPattern")
                        if 'ingredients' in data:
                            print(f"  Ingredients type: {type(data['ingredients']).__name__}")
                except Exception as e:
                    print(f"  Error reading {sample}: {e}")
                count += 1
                if count >= 5:
                    break
    if count >= 5:
        break

# Also try finding VS install via where command or common Steam paths
steam_path = r'C:\Program Files (x86)\Steam\steamapps\common\Vintage Story'
if os.path.isdir(steam_path):
    print(f"\n=== Found Steam install: {steam_path} ===")
else:
    print(f"\n=== Steam path not found: {steam_path} ===")

# Check D drive
for drive in ['C:', 'D:', 'E:']:
    for subdir in ['Vintage Story', 'VintageStory', 'Games\\Vintage Story']:
        p = os.path.join(drive + '\\', subdir)
        if os.path.isdir(p):
            print(f"Found at: {p}")
