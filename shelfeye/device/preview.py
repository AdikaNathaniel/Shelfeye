"""Live camera preview for aiming the ShelfEye camera.

Stop ShelfEye first (only one program can use the camera at a time):
    sudo systemctl stop shelfeye
    python3 preview.py
Then open http://<pi-ip>:8080 on a phone or computer on the same network.
Press Ctrl+C to stop, then: sudo systemctl start shelfeye
"""
import io
import logging
import socketserver
from http import server
from threading import Condition

from libcamera import ColorSpace, controls
from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import FileOutput

PORT = 8080
SIZE = (1280, 720)

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ShelfEye camera preview</title>
<style>
  body { margin: 0; font-family: system-ui, sans-serif; background: #fff8f1; color: #2a1f17; }
  header { background: linear-gradient(135deg, #fed7aa, #ffedd8); padding: 14px 16px; }
  h1 { margin: 0; font-size: 1.2rem; color: #9a3d0b; }
  p { margin: 4px 0 0; font-size: 0.85rem; color: #7c6a5c; }
  main { padding: 16px; max-width: 1000px; margin: 0 auto; }
  img { width: 100%; border-radius: 12px; border: 1px solid #f4e2d0; background: #000; }
</style></head>
<body><header><h1>ShelfEye camera preview</h1><p>Aim the camera so every product label is visible.</p></header>
<main><img src="stream.mjpg" alt="Live camera feed"></main></body></html>
"""


class StreamingOutput(io.BufferedIOBase):
    """Holds the latest JPEG frame and wakes up every connected viewer."""

    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


class StreamingHandler(server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            content = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b"--FRAME\r\n")
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except ConnectionError:
                pass  # viewer closed the page
        else:
            self.send_error(404)

    def log_message(self, *args):
        pass  # keep the terminal quiet


class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


logging.basicConfig(level=logging.INFO, format="%(message)s")
picam2 = Picamera2()
# Full-range colour, so the browser doesn't show the stream washed-out and grey
picam2.configure(picam2.create_video_configuration(main={"size": SIZE}, colour_space=ColorSpace.Sycc()))
output = StreamingOutput()
picam2.start_recording(MJPEGEncoder(), FileOutput(output))
try:
    # Keep refocusing while you move the camera around.
    picam2.set_controls({"AfMode": controls.AfModeEnum.Continuous})
except Exception:
    pass  # camera without autofocus

try:
    logging.info("Preview running. Open http://<this-pi's-ip>:%d in a browser. Ctrl+C to stop.", PORT)
    StreamingServer(("", PORT), StreamingHandler).serve_forever()
except KeyboardInterrupt:
    pass
finally:
    picam2.stop_recording()
    logging.info("Preview stopped. Restart ShelfEye with: sudo systemctl start shelfeye")
