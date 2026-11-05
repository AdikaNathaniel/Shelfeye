"""Loads server/.env into the environment, for running the server on your own computer.

Real environment variables (e.g. those set on Render) always win over the file.
Imported by db.py, which every other module imports first.
"""
import os
from pathlib import Path

ENV_FILE = Path(__file__).with_name(".env")


def load_env_file(path=ENV_FILE):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()
