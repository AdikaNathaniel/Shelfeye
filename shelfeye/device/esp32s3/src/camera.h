// The camera, shared by the counting loop (still photos) and the live view.
// While live view is on, still photos are refused, as on the Pi.
//
// Works with sensors that make JPEGs themselves (OV2640, OV3660, OV5640) and
// with ones that only give raw images (e.g. GC2145, often fitted to cheap
// "ESP32-S3 CAM" boards); raw images are converted to JPEG in software.
#pragma once
#include <Arduino.h>

namespace camera {

// A JPEG photo in PSRAM. Free it with freePhoto().
struct Photo {
  uint8_t* jpeg = nullptr;
  size_t len = 0;
  int width = 0;
  int height = 0;
  // For raw sensors: the shelf fingerprint (imaging::FP_SIZE bytes of grey),
  // made from the raw frame before JPEG encoding. Null for JPEG sensors.
  uint8_t* grey = nullptr;
};

bool begin(const String& frameSize, int jpegQuality);

// A fresh full-resolution photo for counting. Returns false if live view has
// the camera or the capture failed.
bool captureStill(Photo& out);

// Live view: switch to a small frame size, take frames, then switch back.
bool startPreview();
// The newest live frame, as a JPEG. Optionally reports how long the camera took
// to hand it over and how long converting it to JPEG took (both in ms).
bool capturePreview(Photo& out, uint32_t* captureMs = nullptr, uint32_t* convertMs = nullptr);
void stopPreview();
bool previewing();

void freePhoto(Photo& photo);

}  // namespace camera
