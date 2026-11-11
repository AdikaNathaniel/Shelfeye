// ShelfEye firmware for the ESP32-S3: capture -> detect change -> count with OpenAI
// -> store in flash -> push to the server. A port of device/shelfeye_device/main.py.
//
// Every CAPTURE_INTERVAL_SECONDS it takes a photo and compares a small greyscale
// fingerprint with the last counted photo. When the shelf changed (or a recount
// is due), it takes a second photo SETTLE_SECONDS later and counts it only if the
// shelf has settled, so a hand reaching in isn't counted.
#include <Arduino.h>
#include <ArduinoJson.h>
#include <WiFi.h>
#include <esp_sleep.h>
#include <esp_task_wdt.h>

#include "camera.h"
#include "config.h"
#include "imaging.h"
#include "live_view.h"
#include "net.h"
#include "storage.h"
#include "store.h"
#include "uploader.h"
#include "vision.h"

static const uint32_t SETTLE_SECONDS = 10;      // gap between the photo showing a change and the one confirming it
static const uint32_t HEARTBEAT_SECONDS = 300;
static const uint32_t RETRY_SECONDS = 30;       // after a skipped count, try again this soon
// The settle check only has to catch a hand or box in motion, which changes far
// more than this; smaller differences are sensor noise (the GC2145 is noisy).
static const float SETTLE_THRESHOLD = 0.05f;
static bool retrySoon = false;
static const uint32_t WATCHDOG_SECONDS = 180;   // restart if the loop hangs longer than this
static const char* IMAGES_DIR = "/shelfeye/images";

static Config cfg;

// Kept in RTC memory, so it survives deep sleep (but not a power cut).
RTC_DATA_ATTR static time_t lastAnalysisAt = 0;
RTC_DATA_ATTR static time_t lastHeartbeatAt = 0;
RTC_DATA_ATTR static bool haveLastAnalyzed = false;

static uint8_t* lastAnalyzed = nullptr;  // fingerprint of the last photo we sent to OpenAI
static uint8_t* current = nullptr;
static uint8_t* settled = nullptr;

static void log(const char* fmt, ...) {
  char buf[256];
  va_list args;
  va_start(args, fmt);
  vsnprintf(buf, sizeof(buf), fmt, args);
  va_end(args);
  Serial.printf("%s %s\n", net::clockIsSet() ? net::nowIso().c_str() : "--", buf);
}

static void fail(const String& why) {
  // Nothing useful can run without config or a camera; say why, retry in a minute.
  for (int i = 0; i < 6; i++) {
    Serial.printf("ShelfEye can't start: %s\n", why.c_str());
    delay(10000);
  }
  ESP.restart();
}

static void watchdogInit() {
#if ESP_IDF_VERSION_MAJOR >= 5
  esp_task_wdt_config_t wdt = {.timeout_ms = WATCHDOG_SECONDS * 1000, .idle_core_mask = 0, .trigger_panic = true};
  esp_task_wdt_reconfigure(&wdt);
#else
  esp_task_wdt_init(WATCHDOG_SECONDS, true);
#endif
  esp_task_wdt_add(nullptr);  // watch the loop task
}

static String uuid4() {
  uint8_t b[16];
  esp_fill_random(b, sizeof(b));
  b[6] = (b[6] & 0x0F) | 0x40;
  b[8] = (b[8] & 0x3F) | 0x80;
  char s[37];
  snprintf(s, sizeof(s), "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x", b[0], b[1], b[2],
           b[3], b[4], b[5], b[6], b[7], b[8], b[9], b[10], b[11], b[12], b[13], b[14], b[15]);
  return s;
}

// Takes a photo and fingerprints it. With `jpeg`, also hands back the JPEG
// (in PSRAM, caller frees); the camera is already free again for the slow upload.
static bool takePhoto(uint8_t* fp, uint8_t** jpeg = nullptr, size_t* len = nullptr) {
  camera::Photo photo;
  if (!camera::captureStill(photo)) {
    if (!camera::previewing()) log("Couldn't take a photo, will try again next time");
    return false;
  }
  bool ok = imaging::fingerprint(photo, fp);
  if (!ok) log("Couldn't check the photo for changes, will try again next time");
  if (ok && jpeg) {
    *jpeg = photo.jpeg;  // the caller frees it
    *len = photo.len;
    photo.jpeg = nullptr;
  }
  camera::freePhoto(photo);
  return ok;
}

// Counts the products in one photo, saves the result and queues it for the server.
static bool analyze(const uint8_t* jpeg, size_t len) {
  String capturedAt = net::nowIso();
  String image;
  if (storage::hasSdCard()) {
    image = String("images/") + net::today() + "/" + net::timeOfDay() + ".jpg";
    storage::writeBytes(String("/shelfeye/") + image, jpeg, len);
  }

  std::vector<Item> items;
  String error;
  live_view::holdOff(true);
  bool analyzed = analyzeImage(cfg, jpeg, len, items, error);
  live_view::holdOff(false);
  if (!analyzed) {
    log("Analysis failed, will retry on the next photo: %s", error.c_str());
    if (!image.isEmpty()) storage::filesystem().remove(String("/shelfeye/") + image);  // only counted photos are kept
    return false;
  }

  log("OpenAI read %u product(s):", (unsigned)items.size());
  for (const Item& item : items) {
    log("  %s x%d  (label: \"%s\")", item.name.c_str(), item.count, item.labelText.c_str());
  }
  std::vector<Change> changes = store::applyReading(items, capturedAt);
  JsonDocument doc;
  doc["reading_id"] = uuid4();
  doc["node_id"] = cfg.nodeId;
  doc["captured_at"] = capturedAt;
  doc["image"] = image;
  JsonArray outItems = doc["items"].to<JsonArray>();
  for (auto& kv : store::currentCounts()) {
    JsonObject o = outItems.add<JsonObject>();
    o["name"] = kv.first;
    o["count"] = kv.second;
    String label;
    for (const Item& item : items) if (item.name == kv.first) label = item.labelText;
    o["label_text"] = label;
  }
  JsonArray outChanges = doc["changes"].to<JsonArray>();
  for (const Change& c : changes) {
    JsonObject o = outChanges.add<JsonObject>();
    o["name"] = c.name;
    o["previous"] = c.previous;
    o["current"] = c.current;
    o["delta"] = c.current - c.previous;
    log("%s: %d -> %d (%+d)", c.name.c_str(), c.previous, c.current, c.current - c.previous);
  }
  if (changes.empty()) log("No change in counts");
  String payload;
  serializeJson(doc, payload);
  store::queue(doc["reading_id"].as<String>(), payload);
  return true;
}

static void deleteOldImages() {
  if (!storage::hasSdCard() || !net::clockIsSet()) return;
  String cutoff = net::dateDaysAgo(store::keepImagesDays(cfg.keepImagesDays));
  File dir = storage::filesystem().open(IMAGES_DIR);
  if (!dir || !dir.isDirectory()) return;
  std::vector<String> old;
  for (File f = dir.openNextFile(); f; f = dir.openNextFile()) {
    String name = String(f.name()).substring(String(f.name()).lastIndexOf('/') + 1);
    if (f.isDirectory() && name < cutoff) old.push_back(name);  // folders are named YYYY-MM-DD
    f.close();
  }
  dir.close();
  for (const String& name : old) storage::removeTree(String(IMAGES_DIR) + "/" + name);
}

static void countIfNeeded() {
  if (!takePhoto(current)) {
    retrySoon = true;  // live view has the camera, or the photo failed
    return;
  }

  String reason;
  float diff = 0;
  time_t now = time(nullptr);
  if (!haveLastAnalyzed) {
    reason = "first photo since start-up";
  } else if ((diff = imaging::changedFraction(current, lastAnalyzed)) > cfg.changeThreshold) {
    reason = String("shelf changed (") + String(diff * 100, 1) + "% of the image)";
  } else if (now - lastAnalysisAt > (time_t)cfg.recheckMinutes * 60) {
    reason = String(cfg.recheckMinutes) + "-minute recount";
  }
  if (reason.isEmpty()) {
    log("Shelf checked: no change (%.1f%% of the image differs), next photo in %u s", diff * 100,
        cfg.captureIntervalSeconds);
    return;
  }

  delay(SETTLE_SECONDS * 1000);
  esp_task_wdt_reset();
  uint8_t* jpeg = nullptr;
  size_t len = 0;
  if (!takePhoto(settled, &jpeg, &len)) return;
  float moving = imaging::changedFraction(settled, current);
  if (moving > max(cfg.changeThreshold, SETTLE_THRESHOLD)) {
    log("Counting: %s, but the shelf is still moving (%.1f%% changed in %u s), will try again in %u s",
        reason.c_str(), moving * 100, SETTLE_SECONDS, RETRY_SECONDS);
    retrySoon = true;
  } else {
    log("Counting: %s", reason.c_str());
    if (!analyze(jpeg, len)) retrySoon = true;
    else {
      memcpy(lastAnalyzed, settled, imaging::FP_SIZE);
      haveLastAnalyzed = true;
      lastAnalysisAt = time(nullptr);
      if (cfg.deepSleep) store::saveFingerprint(lastAnalyzed);
    }
  }
  free(jpeg);
}

void setup() {
  Serial.setTxBufferSize(4096);  // room for bursts of log lines, so none get cut off
  Serial.begin(115200);
  // Over native USB, give the computer a moment to reconnect so the first lines aren't lost.
  for (int i = 0; i < 30 && !Serial; i++) delay(100);
  delay(500);
  Serial.println("\nShelfEye (ESP32-S3) starting");

  if (!psramFound()) fail("no PSRAM found; check board_build.arduino.memory_type in platformio.ini");
  lastAnalyzed = static_cast<uint8_t*>(ps_malloc(imaging::FP_SIZE));
  current = static_cast<uint8_t*>(ps_malloc(imaging::FP_SIZE));
  settled = static_cast<uint8_t*>(ps_malloc(imaging::FP_SIZE));

  if (!storage::begin()) fail("couldn't open the flash storage; run: python -m platformio run -t uploadfs");
  Serial.printf("Storage: %s\n", storage::name());
  String error;
  if (!loadConfig(cfg, error)) fail(error);
  net::loadCustomCa();
  store::begin();

  // After deep sleep, carry on comparing with the last counted photo. After a
  // power-on or reset, count the first photo, as the Pi does.
  if (esp_sleep_get_wakeup_cause() != ESP_SLEEP_WAKEUP_TIMER) {
    haveLastAnalyzed = false;  // RTC memory survives a software reset, so clear it
    lastHeartbeatAt = 0;
  }
  if (haveLastAnalyzed && !store::loadFingerprint(lastAnalyzed)) haveLastAnalyzed = false;

  if (!camera::begin(cfg.frameSize, cfg.jpegQuality)) fail("camera didn't start");
  net::connectWifi(cfg);
  if (!net::syncClock()) log("Clock not set yet (needed for HTTPS); will keep trying");

  watchdogInit();
  live_view::start(cfg);  // remote and/or local live view, as configured
  log("ShelfEye %s ready: photo every %u s, %s", cfg.nodeId.c_str(), cfg.captureIntervalSeconds,
      cfg.deepSleep ? "deep sleep between photos" : "staying awake");
}

void loop() {
  esp_task_wdt_reset();
  bool online = net::ensureWifi(cfg) && (net::clockIsSet() || net::syncClock());

  if (online && time(nullptr) - lastHeartbeatAt >= (time_t)HEARTBEAT_SECONDS) {
    uploader::sendHeartbeat(cfg);
    lastHeartbeatAt = time(nullptr);
  }
  esp_task_wdt_reset();

  if (net::clockIsSet()) countIfNeeded();  // readings need a real timestamp
  esp_task_wdt_reset();

  if (online) uploader::flushOutbox(cfg);
  deleteOldImages();
  esp_task_wdt_reset();

  if (cfg.deepSleep) {
    log("Sleeping %u s", cfg.captureIntervalSeconds);
    Serial.flush();
    WiFi.disconnect(true);
    esp_sleep_enable_timer_wakeup((uint64_t)cfg.captureIntervalSeconds * 1000000ULL);
    esp_deep_sleep_start();  // wakes up in setup()
  }
  // Wait for the next photo, feeding the watchdog while we do.
  const uint32_t wait = retrySoon ? min(RETRY_SECONDS, cfg.captureIntervalSeconds) : cfg.captureIntervalSeconds;
  retrySoon = false;
  for (uint32_t waited = 0; waited < wait; waited += 10) {
    delay(min<uint32_t>(10, wait - waited) * 1000);
    esp_task_wdt_reset();
  }
}
