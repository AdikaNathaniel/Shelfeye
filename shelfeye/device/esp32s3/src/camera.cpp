#include "camera.h"

#include <esp_camera.h>
#include <esp_log.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <img_converters.h>

#include "board_pins.h"
#include "imaging.h"

namespace camera {

static SemaphoreHandle_t lock = nullptr;  // one user of the camera at a time
static volatile bool isPreviewing = false;
static framesize_t stillSize = FRAMESIZE_UXGA;
static const framesize_t PREVIEW_SIZE = FRAMESIZE_VGA;  // 640x480 keeps live view light on Wi-Fi
static bool sensorMakesJpeg = true;
static camera_config_t activeConfig;  // how the camera was started, for restarts at another size
static int softwareJpegQuality = 85;  // 0-100, for sensors without JPEG

static framesize_t parseFrameSize(const String& name) {
  if (name == "QXGA") return FRAMESIZE_QXGA;  // 2048x1536 (OV3660 only)
  if (name == "UXGA") return FRAMESIZE_UXGA;  // 1600x1200
  if (name == "SXGA") return FRAMESIZE_SXGA;  // 1280x1024
  if (name == "HD") return FRAMESIZE_HD;      // 1280x720
  if (name == "XGA") return FRAMESIZE_XGA;    // 1024x768
  if (name == "SVGA") return FRAMESIZE_SVGA;  // 800x600
  return FRAMESIZE_UXGA;
}

static camera_config_t baseConfig() {
  camera_config_t config = {};
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.ledc_timer = LEDC_TIMER_0;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.fb_count = 1;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  return config;
}

// Throws away the first frames after the camera starts: exposure and white balance
// are still adjusting, which made two photos 10 s apart look 75% different.
static void warmUp(int frames = 3) {
  for (int i = 0; i < frames; i++) {
    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) break;
    esp_camera_fb_return(fb);
    delay(100);
  }
}

// Restarts the camera at a new frame size. Changing size on the fly crashes some
// sensors (the GC2145 overflows the driver's task), so it's stopped and started again.
// For video, two buffers that always hold the newest frame (as ESP32-CAM_MJPEG2SD
// does) let the camera keep capturing while the last frame is converted and sent.
// Still photos use one buffer, filled on request, so a photo is never stale.
static bool restartAt(framesize_t size, bool video) {
  esp_camera_deinit();
  delay(50);
  camera_config_t config = activeConfig;
  config.frame_size = size;
  config.fb_count = video ? 2 : 1;
  config.grab_mode = video ? CAMERA_GRAB_LATEST : CAMERA_GRAB_WHEN_EMPTY;
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK && video) {  // not enough memory for two? one still works
    esp_camera_deinit();
    delay(50);
    config.fb_count = 1;
    config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
    err = esp_camera_init(&config);
  }
  if (err != ESP_OK) {
    Serial.printf("Camera restart failed: 0x%x\n", err);
    return false;
  }
  sensor_t* s = esp_camera_sensor_get();
  if (s->id.PID == OV3660_PID) s->set_vflip(s, 1);
  warmUp();
  return true;
}

bool begin(const String& frameSize, int jpegQuality) {
  lock = xSemaphoreCreateMutex();
  // The camera driver logs from a task with a tiny stack; with Arduino's log hook
  // that can overflow it and crash the board. Its warnings (e.g. "EV-EOF-OVF", a
  // dropped frame, which is normal here) aren't needed, so silence it entirely.
  esp_log_level_set("cam_hal", ESP_LOG_NONE);
  esp_log_level_set("camera", ESP_LOG_ERROR);
  stillSize = parseFrameSize(frameSize);
  // Camera JPEG quality runs 4 (best) to 63; software JPEG quality runs 100 (best) to 0.
  softwareJpegQuality = constrain(100 - (jpegQuality - 4) * 3 / 2, 40, 95);

  // 1. Find out which sensor is fitted, using a small raw format every sensor supports.
  camera_config_t probe = baseConfig();
  probe.pixel_format = PIXFORMAT_RGB565;
  probe.frame_size = FRAMESIZE_QVGA;
  esp_err_t err = esp_camera_init(&probe);
  if (err != ESP_OK) {
    Serial.printf("Camera not found: 0x%x (check the pins in board_pins.h)\n", err);
    return false;
  }
  sensor_t* s = esp_camera_sensor_get();
  camera_sensor_info_t* info = esp_camera_sensor_get_info(&s->id);
  const uint16_t pid = s->id.PID;
  sensorMakesJpeg = info ? info->support_jpeg : (pid == OV2640_PID || pid == OV3660_PID || pid == OV5640_PID);
  if (info && stillSize > info->max_size) stillSize = info->max_size;  // don't ask for more than it can do
  Serial.printf("Camera sensor: %s (PID 0x%x), %s\n", info ? info->name : "unknown", pid,
                sensorMakesJpeg ? "makes JPEGs itself" : "raw images, converted to JPEG in software");
  esp_camera_deinit();
  delay(100);

  // 2. Start it for real, at full size.
  camera_config_t config = baseConfig();
  config.pixel_format = sensorMakesJpeg ? PIXFORMAT_JPEG : PIXFORMAT_RGB565;
  // Raw frames are several times bigger than JPEGs; a slower clock gives PSRAM time to keep up.
  if (!sensorMakesJpeg) config.xclk_freq_hz = 10000000;
  config.frame_size = stillSize;  // buffers are sized for the largest frame we use
  config.jpeg_quality = jpegQuality;
  err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    return false;
  }
  activeConfig = config;
  s = esp_camera_sensor_get();
  if (pid == OV3660_PID) s->set_vflip(s, 1);  // OV3660 modules are usually mounted upside down
  delay(1000);  // let exposure and white balance settle
  warmUp();
  Serial.println("Camera ready");
  return true;
}

// A growing PSRAM buffer the software JPEG encoder writes into. (frame2jpg()
// uses a fixed 128 KB buffer and silently cuts off bigger images, which a
// 1600x1200 photo easily is.)
struct JpegSink {
  uint8_t* buf = nullptr;
  size_t len = 0;
  size_t cap = 0;
  bool failed = false;
};

static size_t writeToSink(void* arg, size_t index, const void* data, size_t len) {
  JpegSink* sink = static_cast<JpegSink*>(arg);
  if (sink->failed) return 0;
  if (index + len > sink->cap) {
    size_t cap = max(sink->cap * 2, index + len + 64 * 1024);
    uint8_t* bigger = static_cast<uint8_t*>(ps_realloc(sink->buf, cap));
    if (!bigger) {
      sink->failed = true;
      return 0;
    }
    sink->buf = bigger;
    sink->cap = cap;
  }
  memcpy(sink->buf + index, data, len);
  sink->len = max(sink->len, index + len);
  return len;
}

// Turns a camera frame into a JPEG in PSRAM (copied, or encoded for raw sensors).
static bool toPhoto(camera_fb_t* fb, Photo& out, bool wantGrey) {
  out = Photo();
  out.width = fb->width;
  out.height = fb->height;
  if (fb->format == PIXFORMAT_JPEG) {
    out.jpeg = static_cast<uint8_t*>(ps_malloc(fb->len));
    if (!out.jpeg) return false;
    memcpy(out.jpeg, fb->buf, fb->len);
    out.len = fb->len;
    return true;
  }
  // The fingerprint comes from the raw pixels: decoding our own software JPEG
  // fails on this library ("JPG Decompression Failed"), and this is faster anyway.
  if (wantGrey) out.grey = static_cast<uint8_t*>(ps_malloc(imaging::FP_SIZE));
  if (out.grey) {
    for (int y = 0; y < imaging::FP_HEIGHT; y++) {
      const size_t sy = (size_t)y * fb->height / imaging::FP_HEIGHT;
      for (int x = 0; x < imaging::FP_WIDTH; x++) {
        const size_t sx = (size_t)x * fb->width / imaging::FP_WIDTH;
        const uint8_t* p = fb->buf + (sy * fb->width + sx) * 2;
        const uint16_t px = (uint16_t)(p[0] << 8) | p[1];  // RGB565, high byte first
        const int r = ((px >> 11) & 0x1F) << 3;
        const int g = ((px >> 5) & 0x3F) << 2;
        const int b = (px & 0x1F) << 3;
        out.grey[y * imaging::FP_WIDTH + x] = (uint8_t)((r * 77 + g * 150 + b * 29) >> 8);
      }
    }
  }
  JpegSink sink;
  sink.cap = (size_t)fb->width * fb->height / 4;  // a typical JPEG fits; grows if not
  sink.buf = static_cast<uint8_t*>(ps_malloc(sink.cap));
  if (!sink.buf || !frame2jpg_cb(fb, softwareJpegQuality, writeToSink, &sink) || sink.failed || sink.len == 0) {
    Serial.println("Couldn't convert the camera image to JPEG");
    free(sink.buf);
    free(out.grey);
    out = Photo();
    return false;
  }
  out.jpeg = sink.buf;
  out.len = sink.len;
  return true;
}

bool captureStill(Photo& out) {
  if (xSemaphoreTake(lock, pdMS_TO_TICKS(5000)) != pdTRUE) return false;
  bool ok = false;
  if (!isPreviewing) {
    // With one buffer the driver may hand back a frame taken earlier; drop it.
    camera_fb_t* stale = esp_camera_fb_get();
    if (stale) esp_camera_fb_return(stale);
    camera_fb_t* fb = esp_camera_fb_get();
    if (fb) {
      ok = toPhoto(fb, out, true);
      esp_camera_fb_return(fb);
    } else {
      Serial.println("Camera capture failed");
    }
  }
  xSemaphoreGive(lock);
  return ok;
}

bool startPreview() {
  if (xSemaphoreTake(lock, pdMS_TO_TICKS(30000)) != pdTRUE) return false;
  bool ok = restartAt(PREVIEW_SIZE, true);
  if (ok) {
    isPreviewing = true;
  } else {
    restartAt(stillSize, false);  // leave the camera usable for counting
  }
  xSemaphoreGive(lock);
  return ok;
}

bool capturePreview(Photo& out, uint32_t* captureMs, uint32_t* convertMs) {
  if (!isPreviewing) return false;
  const uint32_t t0 = millis();
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) return false;
  const uint32_t t1 = millis();
  bool ok = toPhoto(fb, out, false);  // live frames don't need a fingerprint
  esp_camera_fb_return(fb);
  if (captureMs) *captureMs = t1 - t0;
  if (convertMs) *convertMs = millis() - t1;
  return ok;
}

void stopPreview() {
  if (!isPreviewing) return;
  xSemaphoreTake(lock, portMAX_DELAY);
  restartAt(stillSize, false);
  isPreviewing = false;
  xSemaphoreGive(lock);
}

bool previewing() { return isPreviewing; }

void freePhoto(Photo& photo) {
  free(photo.jpeg);
  free(photo.grey);
  photo = Photo();
}

}  // namespace camera
