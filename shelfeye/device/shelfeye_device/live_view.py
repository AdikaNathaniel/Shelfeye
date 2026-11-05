"""Live view, sent to the server so it works from anywhere.

The Pi is usually behind a router (or a phone hotspot) that the server can't
reach, so the Pi makes every connection itself:
  1. It keeps asking the server "is anyone watching?" (each request is held
     open for up to 25 s, so a viewer is noticed within a second or two).
  2. When someone is, it switches the camera to video and uploads a few JPEG
     frames a second, until the last viewer leaves or the time limit is hit.
  3. Then it switches back to stills, and counting resumes.
"""
import io
import logging
import threading
import time

import requests

log = logging.getLogger(__name__)

NO_FRAME_SECONDS = 15  # give up if the camera stops producing video
RETRY_SECONDS = 10  # after the server couldn't be reached
LIMIT_COOLDOWN_SECONDS = 30  # pause after the time limit before streaming again


class FrameBuffer(io.BufferedIOBase):
    """Holds the latest JPEG frame from the camera's video encoder."""

    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()
        return len(buf)


class LiveView:
    def __init__(self, camera, server_url, node_id, token, max_minutes, fps):
        self.camera = camera
        self.base_url = f"{server_url}/api/nodes/{node_id}/live"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.max_seconds = max_minutes * 60
        self.interval = 1 / max(fps, 0.2)
        self.frames = FrameBuffer()

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="live-view").start()
        log.info("Live view ready, sent through %s", self.base_url.split("/api/")[0])

    def _run(self):
        session = requests.Session()
        session.headers.update(self.headers)
        while True:
            try:
                response = session.get(f"{self.base_url}/wait", timeout=40)
                response.raise_for_status()
                if response.json().get("watching"):
                    self._stream(session)
            except (requests.RequestException, ValueError) as exc:
                log.warning("Live view: server unreachable, will retry: %s", exc)
                time.sleep(RETRY_SECONDS)
            except Exception:
                log.exception("Live view failed, will retry")
                time.sleep(RETRY_SECONDS)

    def _stream(self, session):
        log.info("Live view started, counting paused")
        self.frames.frame = None
        self.camera.start_preview(self.frames)
        try:
            started = time.monotonic()
            sent = None
            while time.monotonic() - started < self.max_seconds:
                next_send = time.monotonic() + self.interval
                with self.frames.condition:
                    has_new = self.frames.condition.wait_for(
                        lambda: self.frames.frame is not None and self.frames.frame is not sent,
                        timeout=NO_FRAME_SECONDS,
                    )
                    if not has_new:
                        log.warning("Camera sent no video for %d s, ending live view", NO_FRAME_SECONDS)
                        return
                    sent = self.frames.frame
                response = session.post(
                    f"{self.base_url}/frame",
                    data=bytes(sent),
                    headers={"Content-Type": "image/jpeg"},
                    timeout=15,
                )
                response.raise_for_status()
                if not response.json().get("watching"):
                    return  # the last viewer closed the live view
                time.sleep(max(0.0, next_send - time.monotonic()))
            log.info("Live view reached its %d-minute limit", self.max_seconds // 60)
        finally:
            self.camera.stop_preview()
            log.info("Live view ended, counting resumed")
        # The dashboard closes its view at the same limit; don't restart for a viewer
        # that is about to leave, so counting gets a chance to run.
        time.sleep(LIMIT_COOLDOWN_SECONDS)
