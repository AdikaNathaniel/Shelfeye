"""Device configuration, read from an env file (default /etc/shelfeye/shelfeye.env).

Real environment variables override values from the file.
"""
import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ENV_PATH = "/etc/shelfeye/shelfeye.env"


def _read_env_file(path):
    values = {}
    if not path or not Path(path).exists():
        return values
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass
class Config:
    node_id: str
    openai_api_key: str
    openai_model: str
    server_url: str
    device_token: str
    data_dir: Path
    catalog: list
    capture_interval: int
    change_threshold: float
    recheck_minutes: int
    keep_images_days: int
    live_view: bool
    live_view_fps: float
    live_view_max_minutes: int


def load_config(env_path=DEFAULT_ENV_PATH):
    file_values = _read_env_file(env_path)

    def get(key, default=None):
        return os.environ.get(key, file_values.get(key, default))

    api_key = get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set (check your shelfeye.env)")

    catalog = []
    catalog_path = get("SHELFEYE_CATALOG")
    if catalog_path and Path(catalog_path).exists():
        catalog = json.loads(Path(catalog_path).read_text())

    data_dir = Path(get("SHELFEYE_DATA_DIR", "./shelfeye-data"))
    data_dir.mkdir(parents=True, exist_ok=True)

    return Config(
        node_id=get("SHELFEYE_NODE_ID", "shelf-1"),
        openai_api_key=api_key,
        openai_model=get("OPENAI_MODEL", "gpt-4.1-mini"),
        server_url=get("SHELFEYE_SERVER_URL", "").rstrip("/"),
        device_token=get("SHELFEYE_DEVICE_TOKEN", ""),
        data_dir=data_dir,
        catalog=catalog,
        capture_interval=int(get("CAPTURE_INTERVAL_SECONDS", "180")),
        change_threshold=float(get("CHANGE_THRESHOLD", "0.01")),
        recheck_minutes=int(get("RECHECK_MINUTES", "30")),
        keep_images_days=int(get("KEEP_IMAGES_DAYS", "365")),
        # LIVE_VIEW_PORT=0 is how older config files turned live view off.
        live_view=get("LIVE_VIEW", "off" if get("LIVE_VIEW_PORT") == "0" else "on").lower()
        not in ("off", "0", "false", "no"),
        live_view_fps=float(get("LIVE_VIEW_FPS", "2")),
        live_view_max_minutes=int(get("LIVE_VIEW_MAX_MINUTES", "10")),
    )
