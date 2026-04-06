# DEPRECATED: Legacy one-off environment probe script retained for reference only. Not part of Gen 3 pipeline/runtime.
import os, json, re

base = r'C:\Games\Vintagestory\assets\survival\recipes'

# Sample one file from each recipe type directory
recipe_types = ['grid', 'barrel', 'clayforming', 'smithing', 'knapping', 'alloy', 'cooking']

def load_json_tolerant(filepath):
    """Load JSON with tolerance for comments and BOM"""
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        text = f.read()
    # Remove single-line comments
    text = re.sub(r'//.*?$', '', text, flags=re.MULTILINE)
    # Remove multi-line comments
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    # Remove trailing commas before } or ]
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return json.loads(text)

for rtype in recipe_types:
    rdir = os.path.join(base, rtype)
    if not os.path.isdir(rdir):
        print(f"\n=== {rtype}: NOT FOUND ===")
        continue
    
    # Find first json file
    for f in os.listdir(rdir):
        if f.endswith('.json'):
            filepath = os.path.join(rdir, f)
            print(f"\n=== {rtype}: {f} ===")
            try:
                data = load_json_tolerant(filepath)
                print(json.dumps(data, indent=2)[:1500])
            except Exception as e:
                print(f"Error: {e}")
                # Print raw content
                with open(filepath, 'r', encoding='utf-8-sig') as fh:
                    print(fh.read()[:800])
            break
