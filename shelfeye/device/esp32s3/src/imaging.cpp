#include "imaging.h"

#include <img_converters.h>

namespace imaging {

bool fingerprint(const camera::Photo& photo, uint8_t* out) {
  if (photo.grey) {  // raw sensor: already made from the raw frame
    memcpy(out, photo.grey, FP_SIZE);
    return true;
  }
  // Decoding at 1/8 scale is fast and already averages away most noise.
  const int w = photo.width / 8;
  const int h = photo.height / 8;
  if (w < 1 || h < 1) return false;
  uint8_t* rgb = static_cast<uint8_t*>(ps_malloc((size_t)w * h * 2));
  if (!rgb) return false;
  bool ok = jpg2rgb565(photo.jpeg, photo.len, rgb, JPG_SCALE_8X);
  if (ok) {
    // Resample to a fixed size, converting RGB565 to grey.
    for (int y = 0; y < FP_HEIGHT; y++) {
      const int sy = y * h / FP_HEIGHT;
      for (int x = 0; x < FP_WIDTH; x++) {
        const int sx = x * w / FP_WIDTH;
        const uint8_t* p = rgb + ((size_t)sy * w + sx) * 2;
        const uint16_t px = (uint16_t)(p[0] << 8) | p[1];  // jpg2rgb565 writes big-endian
        const int r = ((px >> 11) & 0x1F) << 3;
        const int g = ((px >> 5) & 0x3F) << 2;
        const int b = (px & 0x1F) << 3;
        out[y * FP_WIDTH + x] = (uint8_t)((r * 77 + g * 150 + b * 29) >> 8);
      }
    }
  }
  free(rgb);
  if (!ok) Serial.println("Couldn't read the photo back to check for shelf changes");
  return ok;
}

float changedFraction(const uint8_t* a, const uint8_t* b) {
  size_t changed = 0;
  for (size_t i = 0; i < FP_SIZE; i++) {
    if (abs((int)a[i] - (int)b[i]) > PIXEL_DIFF_LEVEL) changed++;
  }
  return (float)changed / FP_SIZE;
}

}  // namespace imaging
