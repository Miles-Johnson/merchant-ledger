import os
import subprocess

RAILWAY = "postgresql://postgres:oOxYpSxuanvKDQiExaCnCHpaBwWxwkya@maglev.proxy.rlwy.net:33597/railway"

env = os.environ.copy()
env["DATABASE_URL"] = RAILWAY

for script in [
    "scripts/parse_recipes_json.py",
    "scripts/build_canonical_items.py",
    "scripts/apply_manual_lr_links.py",
    "scripts/link_recipes.py",
]:
    print(f"\n=== Running {script} ===")
    result = subprocess.run(["python", script], env=env, capture_output=False)
    print(f"=== {script} exit code: {result.returncode} ===")
    if result.returncode != 0:
        print("FAILED - stopping")
        break