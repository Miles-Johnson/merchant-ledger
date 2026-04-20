#!/usr/bin/env python3
import subprocess
import sys


SCRIPTS = [
    "scripts/ingest_lr_prices.py",
    "scripts/compute_primitive_prices.py",
    "scripts/build_canonical_items.py",
    "scripts/apply_manual_lr_links.py",
]


def run_script(path: str) -> None:
    print(f"\n=== Running: python {path} ===")
    completed = subprocess.run([sys.executable, path], check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Script failed ({completed.returncode}): {path}")


def main() -> int:
    try:
        for script in SCRIPTS:
            run_script(script)
    except Exception as exc:
        print(f"\n[ERROR] {exc}")
        return 1

    print("\n[OK] sync_railway complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())