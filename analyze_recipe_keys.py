import os, json, re

def parse_json5(text):
    text = text.lstrip('\ufeff')
    text = re.sub(r'//[^\n]*', '', text)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    text = re.sub(r'(?<=[{,\n])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r' "\1":', text)
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return json.loads(text)

def get_keys(obj):
    if isinstance(obj, list):
        keys = set()
        for item in obj:
            if isinstance(item, dict):
                keys.update(item.keys())
        return keys
    elif isinstance(obj, dict):
        return set(obj.keys())
    return set()

type_keys = {}
type_errors = {}
type_files = {}

roots = [
    (r'C:\Games\Vintagestory\assets\survival\recipes', 'BASE'),
    (r'Cache\unpack', 'MOD')
]

for root_path, source in roots:
    for dp, dn, fn in os.walk(root_path):
        norm = dp.replace('/', os.sep)
        if os.sep + 'recipes' + os.sep not in norm:
            continue
        parts = norm.split(os.sep + 'recipes' + os.sep)
        rtype = parts[1].split(os.sep)[0]
        label = source + ':' + rtype
        
        for f in fn:
            if not f.endswith('.json'):
                continue
            fpath = os.path.join(dp, f)
            type_files.setdefault(label, 0)
            type_files[label] += 1
            try:
                with open(fpath, encoding='utf-8-sig') as fh:
                    data = parse_json5(fh.read())
                keys = get_keys(data)
                type_keys.setdefault(label, {})
                for k in keys:
                    kl = k.lower()
                    type_keys[label].setdefault(kl, 0)
                    type_keys[label][kl] += 1
            except Exception as e:
                type_errors.setdefault(label, 0)
                type_errors[label] += 1

outpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'recipe_key_analysis.txt')
with open(outpath, 'w') as out:
    for label in sorted(type_keys.keys()):
        total = type_files.get(label, 0)
        err = type_errors.get(label, 0)
        parsed = total - err
        keys_sorted = sorted(type_keys[label].items(), key=lambda x: -x[1])
        out.write(f'\n=== {label} ({total} files, {err} parse errors, {parsed} parsed) ===\n')
        for k, v in keys_sorted:
            pct = round(100*v/max(parsed,1))
            out.write(f'  {k}: {v}/{parsed} ({pct}%)\n')
    
    # Cross-type summary
    all_keys = set()
    for d in type_keys.values():
        all_keys.update(d.keys())
    out.write('\n\n=== CROSS-TYPE KEY PRESENCE ===\n')
    for k in sorted(all_keys):
        present = [label for label in sorted(type_keys.keys()) if k in type_keys[label]]
        out.write(f'  {k}: present in {len(present)} types -> {present}\n')

print(f'Done - wrote {outpath}')
