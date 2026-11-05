"""ShelfEye device loop: capture -> detect change -> count with OpenAI -> store on SD -> push to server."""
import argparse
import logging
import shutil
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .config import DEFAULT_ENV_PATH, load_config
from .imaging import changed_fraction, fingerprint, jpeg_for_api
from .live_view import LiveView
from .store import Store
from .uploader import flush_outbox, send_heartbeat
from .vision import analyze_image

log = logging.getLogger("shelfeye")

HEARTBEAT_SECONDS = 5 * 60


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_image_path(data_dir):
    folder = data_dir / "images" / date.today().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    return folder / datetime.now().strftime("%H%M%S.jpg")


def delete_old_images(data_dir, keep_days):
    cutoff = (date.today() - timedelta(days=keep_days)).isoformat()
    images = data_dir / "images"
    if not images.exists():
        return
    for folder in images.iterdir():
        if folder.is_dir() and folder.name < cutoff:
            shutil.rmtree(folder, ignore_errors=True)


def keep_images_days(cfg, store):
    """Photo retention: the dashboard's value if it ever sent one, else KEEP_IMAGES_DAYS."""
    saved = store.get_setting("keep_images_days")
    return int(saved) if saved else cfg.keep_images_days


def apply_server_settings(settings, store):
    """Save settings from the dashboard on the SD card, so they survive restarts and outages."""
    days = (settings or {}).get("keep_images_days")
    if not isinstance(days, int) or days < 1:
        return
    if store.get_setting("keep_images_days") != str(days):
        log.info("Dashboard set photo retention to %d days", days)
        store.set_setting("keep_images_days", days)


def analyze(path, cfg, store):
    """Count the products in one photo, save the result and queue it for the server."""
    items = analyze_image(jpeg_for_api(path), cfg.openai_api_key, cfg.openai_model, cfg.catalog)
    captured_at = now_iso()
    changes = store.apply_reading(items, captured_at)
    labels = {item["name"]: item["label_text"] for item in items}
    store.queue(
        {
            "reading_id": str(uuid.uuid4()),
            "node_id": cfg.node_id,
            "captured_at": captured_at,
            "image": str(path.relative_to(cfg.data_dir)),
            "items": [
                {"name": name, "count": count, "label_text": labels.get(name, "")}
                for name, count in store.current_counts().items()
            ],
            "changes": changes,
        }
    )
    for change in changes:
        log.info("%s: %d -> %d (%+d)", change["name"], change["previous"], change["current"], change["delta"])
    if not changes:
        log.info("No change in counts")
    return changes


def run(cfg, store):
    from .camera import Camera

    camera = Camera()
    if cfg.live_view and cfg.server_url:
        LiveView(
            camera, cfg.server_url, cfg.node_id, cfg.device_token, cfg.live_view_max_minutes, cfg.live_view_fps
        ).start()
    last_analyzed = None  # fingerprint of the last photo we sent to OpenAI
    previous = None  # fingerprint of the photo just before this one
    last_analysis_time = 0.0
    last_heartbeat = 0.0

    while True:
        if time.time() - last_heartbeat > HEARTBEAT_SECONDS:
            live_view = cfg.live_view and bool(cfg.server_url)
            settings = send_heartbeat(cfg.server_url, cfg.node_id, cfg.device_token, live_view)
            apply_server_settings(settings, store)
            last_heartbeat = time.time()

        path = new_image_path(cfg.data_dir)
        if not camera.capture(path):
            # Live view has the camera. It may also have been re-aimed, so
            # start change detection afresh once counting resumes.
            previous = None
            time.sleep(5)
            continue
        current = fingerprint(path)

        changed = last_analyzed is None or changed_fraction(current, last_analyzed) > cfg.change_threshold
        recheck_due = time.time() - last_analysis_time > cfg.recheck_minutes * 60
        # Only analyse once the scene has settled, so a hand reaching in isn't counted.
        stable = previous is not None and changed_fraction(current, previous) <= cfg.change_threshold

        analyzed = False
        if (changed or recheck_due) and stable:
            try:
                analyze(path, cfg, store)
                last_analyzed = current
                last_analysis_time = time.time()
                analyzed = True
            except Exception:
                log.exception("Analysis failed, will retry on the next frame")
        if not analyzed:
            path.unlink(missing_ok=True)  # only keep photos that were analysed

        previous = current
        flush_outbox(store, cfg.server_url, cfg.node_id, cfg.device_token)
        delete_old_images(cfg.data_dir, keep_images_days(cfg, store))
        time.sleep(cfg.capture_interval)


def main():
    parser = argparse.ArgumentParser(description="ShelfEye shelf camera")
    parser.add_argument("--config", default=DEFAULT_ENV_PATH, help="path to shelfeye.env")
    parser.add_argument("--image", type=Path, help="analyse this photo once instead of using the camera")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(args.config)
    store = Store(cfg.data_dir / "shelfeye.db")

    if args.image:
        # Copy into the data folder so the stored reading points at a file we keep.
        path = new_image_path(cfg.data_dir)
        shutil.copy(args.image, path)
        analyze(path, cfg, store)
        flush_outbox(store, cfg.server_url, cfg.node_id, cfg.device_token)
        return

    run(cfg, store)


if __name__ == "__main__":
    main()
