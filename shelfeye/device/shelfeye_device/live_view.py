"""Live view: an MJPEG stream of the camera, served on demand.

The camera only switches to video when the first viewer connects and goes
back to counting when the last one leaves. Each viewing session is capped so
a forgotten browser tab can't stop counting for good.
"""
import io
import logging
import socket
import threading
import time
from http import server
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

log = logging.getLogger(__name__)

MAX_VIEWERS = 3  # the Pi Zero can't serve many streams at once
NO_FRAME_SECONDS = 15  # give up on a stream if the camera stops producing frames


class FrameBuffer(io.BufferedIOBase):
    """Holds the latest JPEG frame and wakes up every connected viewer."""

    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()
        return len(buf)


class _Server(ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class LiveView:
    def __init__(self, camera, port, max_minutes):
        self.camera = camera
        self.port = port
        self.max_seconds = max_minutes * 60
        self.frames = FrameBuffer()
        self.viewers = 0
        self._lock = threading.Lock()

    def _join(self):
        with self._lock:
            if self.viewers >= MAX_VIEWERS:
                return False
            if self.viewers == 0:
                log.info("Live view started, counting paused")
                self.camera.start_preview(self.frames)
            self.viewers += 1
            return True

    def _leave(self):
        with self._lock:
            self.viewers -= 1
            if self.viewers == 0:
                self.camera.stop_preview()
                log.info("Live view ended, counting resumed")

    def start(self):
        live_view = self

        class Handler(server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != "/stream.mjpg":
                    self.send_error(404)
                    return
                try:
                    joined = live_view._join()
                except Exception:
                    log.exception("Could not start live view")
                    self.send_error(503, "Camera unavailable")
                    return
                if not joined:
                    self.send_error(503, "Too many viewers")
                    return
                try:
                    live_view._stream(self)
                finally:
                    live_view._leave()

            def log_message(self, *args):
                pass  # keep the service log quiet

        httpd = _Server(("", self.port), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        log.info("Live view available on port %d", self.port)

    def _stream(self, handler):
        handler.send_response(200)
        handler.send_header("Cache-Control", "no-cache, private")
        handler.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
        handler.end_headers()
        started = time.monotonic()
        try:
            while time.monotonic() - started < self.max_seconds:
                with self.frames.condition:
                    if not self.frames.condition.wait(timeout=NO_FRAME_SECONDS):
                        log.warning("Camera sent no video for %d s, ending live view", NO_FRAME_SECONDS)
                        return
                    frame = self.frames.frame
                handler.wfile.write(b"--FRAME\r\n")
                handler.send_header("Content-Type", "image/jpeg")
                handler.send_header("Content-Length", str(len(frame)))
                handler.end_headers()
                handler.wfile.write(frame)
                handler.wfile.write(b"\r\n")
        except ConnectionError:
            pass  # viewer closed the page


def local_ip(server_url):
    """The Pi's address on the network it uses to reach the server."""
    host = urlparse(server_url).hostname or "8.8.8.8"
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect((host, 80))  # no packets are sent; this just picks the route
            return s.getsockname()[0]
        except OSError:
            return None
