"""Thin wrapper around Picamera2 for the Raspberry Pi Camera Module 3.

The camera is shared by the counting loop (still photos) and the live view
(an MJPEG video stream). While live view is on, still captures are refused.
"""
import threading
import time


class Camera:
    def __init__(self, size=(2304, 1296), preview_size=(1280, 720)):
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

        self._cam.configure(self._still_config)
        self._cam.start()
        time.sleep(2)  # let exposure and white balance settle
        self._focus_once()

    def _focus_once(self):
        try:
            # Focus once and keep the lens there, so frames stay comparable.
            self._cam.autofocus_cycle()
        except Exception:
            pass  # camera without autofocus

    def capture(self, path):
        """Take a still photo. Returns False if live view is using the camera."""
        with self._lock:
            if self.previewing:
                return False
            self._cam.capture_file(str(path))
            return True

    def start_preview(self, output):
        """Switch to video mode and stream MJPEG frames into `output`."""
        from libcamera import controls
        from picamera2.encoders import MJPEGEncoder
        from picamera2.outputs import FileOutput

        with self._lock:
            if self.previewing:
                return
            self._cam.stop()
            try:
                self._cam.configure(self._video_config)
                self._cam.start_recording(MJPEGEncoder(), FileOutput(output))
            except Exception:
                # Leave the camera running in still mode, otherwise the next
                # capture waits forever on a stopped camera.
                self._restart_still()
                raise
            try:
                # Keep refocusing while someone re-aims the camera.
                self._cam.set_controls({"AfMode": controls.AfModeEnum.Continuous})
            except Exception:
                pass
            self.previewing = True

    def stop_preview(self):
        """Go back to still mode for counting."""
        with self._lock:
            if not self.previewing:
                return
            try:
                self._cam.stop_recording()
            finally:
                self._restart_still()
                self.previewing = False

    def _restart_still(self):
        self._cam.stop()
        self._cam.configure(self._still_config)
        self._cam.start()
        time.sleep(1)
        self._focus_once()

    def close(self):
        self._cam.close()
