import os
os.environ["DATABASE_URL"] = "postgresql://postgres:gMilkqIwIFsQgJRQYonBHKJyFgZGPfaE@shinkansen.proxy.rlwy.net:38376/railway"

import sys
import types
import runpy

_dotenv = types.ModuleType("dotenv")


def _load_dotenv(*args, **kwargs):
    return False


_dotenv.load_dotenv = _load_dotenv
sys.modules["dotenv"] = _dotenv

if len(sys.argv) < 2:
    raise SystemExit("Usage: python railway_wrapper.py <target_script.py> [args...]")

target_script = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(target_script, run_name="__main__")