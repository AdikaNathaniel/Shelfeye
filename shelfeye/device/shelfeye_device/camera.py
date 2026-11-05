"""Thin wrapper around Picamera2 for the Raspberry Pi Camera Module 3.

The camera is shared by the counting loop (still photos) and the live view
(MJPEG video frames sent to the server). While live view is on, still captures are refused.

Every camera operation runs under a watchdog: if libcamera ever hangs, the
service exits and systemd restarts it, instead of counting silently stopping.
"""
import logging
import os
import threading
import time
from contextlib import contextmanager

log = logging.getLogger(__name__)

STUCK_SECONDS = 60  # no camera operation should take anywhere near this long
FOCUS_SECONDS = 10


@contextmanager
def watchdog(what):
    def stuck():
        log.error("Camera stuck %s for %d s, restarting ShelfEye", what, STUCK_SECONDS)
        os._exit(1)  # systemd (Restart=always) starts us again

    timer = threading.Timer(STUCK_SECONDS, stuck)
    timer.daemon = True
    timer.start()
    try:
        yield
    finally:
        timer.cancel()


class Camera:
    def __init__(self, size=(2304, 1296), preview_size=(960, 540)):
        # Imported here so the rest of the app can run on a laptop without a camera.
        from libcamera import ColorSpace
        from picamera2 import Picamera2

        self._cam = Picamera2()
        self._still_config = self._cam.create_still_configuration(main={"size": size})
        # Video defaults to limited-range Rec709, which browsers show as washed-out
        # grey in an MJPEG stream. Full-range sYCC is what JPEG expects.
        self._video_config = self._cam.create_video_configuration(
            main={"size": preview_size}, colour_space=ColorSpace.Sycc(),
            buffer_count=3,  # the default 6 can run the Pi Zero out of camera memory
        )
        self._lock = threading.Lock()  # one user of the camera at a time
        self.previewing = False

        with watchdog("starting up"):
            self._cam.configure(self._still_config)
            self._cam.start()
            time.sleep(2)  # let exposure and white balance settle
            self._focus_once()

    def _focus_once(self):
        """Focus once and keep the lens there, so frames stay comparable."""
        try:
            from libcamera import controls

            # Live view leaves the lens in continuous mode, where a one-off focus
            # never completes; switch to auto first, and never wait forever.
            self._cam.set_controls({"AfMode": controls.AfModeEnum.Auto})
            job = self._cam.autofocus_cycle(wait=False)
            self._cam.wait(job, timeout=FOCUS_SECONDS)
        except TimeoutError:
            log.warning("Autofocus didn't finish within %d s, keeping the current focus", FOCUS_SECONDS)
        except Exception:
            pass  # camera without autofocus

    def capture(self, path):
        """Take a still photo. Returns False if live view is using the camera."""
        with self._lock:
            if self.previewing:
                return False
            with watchdog("taking a photo"):
                self._cam.capture_file(str(path))
            return True

    def start_preview(self, output):
        """Switch to video mode and stream MJPEG frames into `output`."""
        from libcamera import controls
        from picamera2.encoders import MJPEGEncoder
        from picamera2.outputs import FileOutput

        with self._lock, watchdog("switching to live view"):
            if self.previewing:
                return
            self._cam.stop()
            try:
                self._cam.configure(self._video_config)
                self._cam.start_recording(MJPEGEncoder(), FileOutput(output))
            except Exception:
                # Leave the camera running in still mode, otherwise the next
                # capture waits forever on a stopped camera.
                self._restart_still()  # the lens hasn't moved, so focus is unchanged
                raise
            try:
                # Keep refocusing while someone re-aims the camera.
                self._cam.set_controls({"AfMode": controls.AfModeEnum.Continuous})
            except Exception:
                pass
            self.previewing = True

    def stop_preview(self):
        """Go back to still mode for counting."""
        with self._lock, watchdog("switching back to photos"):
            if not self.previewing:
                return
            lens_position = None
            try:
                # Live view kept the lens focused; remember where, so stills can
                # use it. A fresh autofocus after video never completes on this camera.
                lens_position = self._cam.capture_metadata().get("LensPosition")
                self._cam.stop_recording()
            finally:
                self._restart_still(lens_position)
                self.previewing = False

    def _restart_still(self, lens_position=None):
        self._cam.stop()
        self._cam.configure(self._still_config)
        self._cam.start()
        self._hold_focus(lens_position)
        time.sleep(1)  # let exposure settle

    def _hold_focus(self, lens_position):
        """Stop the lens moving (live view leaves it in continuous autofocus)."""
        try:
            from libcamera import controls

            fixed = {"AfMode": controls.AfModeEnum.Manual}
            if lens_position is not None:
                fixed["LensPosition"] = lens_position
            self._cam.set_controls(fixed)
        except Exception:
            pass  # camera without autofocus

    def close(self):
        self._cam.close()
