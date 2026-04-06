# DEPRECATED: Legacy one-off environment probe script retained for reference only. Not part of Gen 3 pipeline/runtime.
import os

# Check base game locations
paths = [
    r'C:\Program Files\Vintage Story',
    r'C:\Program Files (x86)\Vintage Story',
    r'C:\Users\Kjol\AppData\Local\Programs\Vintagestory',
]

for p in paths:
    exists = os.path.isdir(p)
    print(f"{p}: EXISTS={exists}")
    if exists:
        # Check for assets folders
        for sub in ['assets/survival/recipes', 'assets/game/recipes', 'assets\\survival\\recipes', 'assets\\game\\recipes']:
            full = os.path.join(p, sub)
            if os.path.isdir(full):
                print(f"  Found recipes at: {full}")

# Also check Cache/unpack top-level folders
unpack = r'C:\Users\Kjol\AppData\Roaming\VintagestoryData\Cache\unpack'
if os.path.isdir(unpack):
    entries = os.listdir(unpack)
    print(f"\nCache/unpack has {len(entries)} entries:")
    for e in entries[:20]:
        print(f"  {e}")
    if len(entries) > 20:
        print(f"  ... and {len(entries)-20} more")
