// Cheap on-device image checks, so we only pay for an OpenAI call when the shelf changes.
#pragma once
#include <Arduino.h>
#include "camera.h"

namespace imaging {

constexpr int FP_WIDTH = 160;
constexpr int FP_HEIGHT = 120;
constexpr size_t FP_SIZE = FP_WIDTH * FP_HEIGHT;
constexpr int PIXEL_DIFF_LEVEL = 30;  // 0-255; smaller differences are sensor noise

// A small greyscale copy of a photo (FP_SIZE bytes in `out`).
bool fingerprint(const camera::Photo& photo, uint8_t* out);

// Fraction (0.0-1.0) of pixels that differ noticeably between two fingerprints.
float changedFraction(const uint8_t* a, const uint8_t* b);

}  // namespace imaging
