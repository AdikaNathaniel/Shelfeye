#include "live_view.h"

#include <ArduinoJson.h>
#include <Preferences.h>
#include <WiFi.h>
#include <esp_http_server.h>

#include "camera.h"
#include "net.h"
#include "ws_client.h"

namespace live_view {

static const uint32_t RETRY_MS = 10000;            // after the server couldn't be reached
static const uint32_t LIMIT_COOLDOWN_MS = 30000;   // pause after the time limit before streaming again
static const uint32_t IDLE_STOP_MS = 2000;         // stop the camera this long after the last viewer leaves
static const uint32_t FIRST_FRAME_WAIT_MS = 90000;  // covers a count in progress (holdOff)
static const uint32_t NEXT_FRAME_WAIT_MS = 5000;
static const uint32_t STATS_EVERY_MS = 5000;

static const Config* config = nullptr;
static net::Connection conn("live");
static volatile bool held = false;
static volatile bool remoteWanted = false;
static volatile int localViewers = 0;
static String key;

void holdOff(bool on) { held = on; }
String localKey() { return key; }

// ---- The newest frame, shared by the capture task and the senders ----

static SemaphoreHandle_t frameLock = nullptr;
static uint8_t* latest = nullptr;  // JPEG in PSRAM
static size_t latestLen = 0;
static volatile uint32_t latestSeq = 0;
static volatile bool capturing = false;

static void publish(camera::Photo& photo) {
  xSemaphoreTake(frameLock, portMAX_DELAY);
  free(latest);
  latest = photo.jpeg;  // take ownership
  latestLen = photo.len;
  latestSeq++;
  xSemaphoreGive(frameLock);
  photo.jpeg = nullptr;
}

// Copies the first frame newer than `seen` into `buf` (grown as needed).
// Waits up to `waitMs`; returns false if no new frame arrived in time.
static bool nextFrame(uint32_t& seen, uint8_t*& buf, size_t& cap, size_t& len, uint32_t waitMs) {
  const uint32_t started = millis();
  while (millis() - started < waitMs) {
    if (latestSeq != seen) {
      bool ok = false;
      xSemaphoreTake(frameLock, portMAX_DELAY);
      if (latest && latestLen) {
        if (latestLen > cap) {
          uint8_t* bigger = static_cast<uint8_t*>(ps_realloc(buf, latestLen));
          if (bigger) {
            buf = bigger;
            cap = latestLen;
          }
        }
        if (latestLen <= cap) {
          memcpy(buf, latest, latestLen);
          len = latestLen;
          seen = latestSeq;
          ok = true;
        }
      }
      xSemaphoreGive(frameLock);
      if (ok) return true;
    }
    delay(5);
  }
  return false;
}

// ---- Timing, logged every few seconds so the slow step is obvious ----

struct Stats {
  uint32_t frames = 0, captureMs = 0, convertMs = 0, bytes = 0;  // capture task
  uint32_t remoteFrames = 0, remoteMs = 0;                       // remote sender
  uint32_t localFrames = 0, localMs = 0;                         // local sender
};
static Stats stats;
static portMUX_TYPE statsMux = portMUX_INITIALIZER_UNLOCKED;
static const char* remoteMode = "";

static void logStats(uint32_t periodMs) {
  portENTER_CRITICAL(&statsMux);
  Stats s = stats;
  stats = Stats();
  portEXIT_CRITICAL(&statsMux);
  const float secs = periodMs / 1000.0f;
  String line = "Live view: camera " + String(s.frames / secs, 1) + " fps";
  if (s.frames) {
    line += " (capture " + String(s.captureMs / s.frames) + " ms, convert to JPEG " + String(s.convertMs / s.frames) +
            " ms, " + String(s.bytes / s.frames / 1024) + " KB a frame)";
  }
  if (remoteWanted) {
    line += " | remote " + String(s.remoteFrames / secs, 1) + " fps";
    if (s.remoteFrames) line += ", upload " + String(s.remoteMs / s.remoteFrames) + " ms";
    line += String(" (") + remoteMode + ")";
  }
  if (localViewers > 0) {
    line += " | local " + String(s.localFrames / secs, 1) + " fps";
    if (s.localFrames) line += ", send " + String(s.localMs / s.localFrames) + " ms";
  }
  Serial.println(line);
}

// ---- Capture task: runs the camera while anyone (remote or local) is watching ----

static void captureTask(void*) {
  uint32_t lastWanted = 0, sessionStart = 0, lastStats = 0, lastFrame = 0, cooldownUntil = 0;
  const uint32_t intervalMs = (uint32_t)(1000.0f / max(config->liveViewFps, 0.2f));
  const uint32_t limitMs = config->liveViewMaxMinutes * 60000UL;
  while (true) {
    const bool wanted = (remoteWanted || localViewers > 0) && (int32_t)(millis() - cooldownUntil) >= 0;
    if (wanted) lastWanted = millis();
    if (!wanted || held) {
      if (capturing && (held || millis() - lastWanted > IDLE_STOP_MS)) {
        capturing = false;
        camera::stopPreview();
        Serial.println("Live view ended, counting resumed");
      }
      delay(50);
      continue;
    }
    if (!capturing) {
      Serial.println("Live view started, counting paused");
      if (!camera::startPreview()) {
        delay(2000);
        continue;
      }
      capturing = true;
      sessionStart = lastStats = millis();
      portENTER_CRITICAL(&statsMux);
      stats = Stats();
      portEXIT_CRITICAL(&statsMux);
    }
    if (millis() - sessionStart >= limitMs) {
      // The dashboard closes its view at the same limit; pause so counting gets a turn.
      Serial.printf("Live view reached its %u-minute limit\n", config->liveViewMaxMinutes);
      capturing = false;
      camera::stopPreview();
      Serial.println("Live view ended, counting resumed");
      cooldownUntil = millis() + LIMIT_COOLDOWN_MS;
      continue;
    }

    const uint32_t sinceLast = millis() - lastFrame;
    if (sinceLast < intervalMs) delay(intervalMs - sinceLast);  // LIVE_VIEW_FPS is an upper limit
    lastFrame = millis();
    camera::Photo photo;
    uint32_t captureMs = 0, convertMs = 0;
    if (camera::capturePreview(photo, &captureMs, &convertMs)) {
      const size_t len = photo.len;
      publish(photo);
      camera::freePhoto(photo);
      portENTER_CRITICAL(&statsMux);
      stats.frames++;
      stats.captureMs += captureMs;
      stats.convertMs += convertMs;
      stats.bytes += len;
      portEXIT_CRITICAL(&statsMux);
    } else {
      delay(20);
    }
    if (millis() - lastStats >= STATS_EVERY_MS) {
      logStats(millis() - lastStats);
      lastStats = millis();
    }
  }
}

// ---- Remote sender: through the server, over one WebSocket ----

static bool watchingIn(const String& body) {
  JsonDocument doc;
  return !deserializeJson(doc, body) && (doc["watching"] | false);
}

static bool stoppedIn(const String& body) {
  JsonDocument doc;
  return !deserializeJson(doc, body) && doc["watching"].is<bool>() && !doc["watching"].as<bool>();
}

static void streamRemote(const String& base) {
  conn.close();  // free the long-poll connection's memory before opening the stream
  const String auth = "Bearer " + config->deviceToken;
  WsClient ws;
  bool useWs = ws.connect(base + "/ws", auth, 15000);
  remoteMode = useWs ? "WebSocket" : "one request per frame";
  if (!useWs) Serial.printf("Live view: WebSocket unavailable (%s), sending frames one by one\n", ws.lastError().c_str());
  remoteWanted = true;

  uint8_t* buf = nullptr;
  size_t cap = 0, len = 0;
  uint32_t seen = latestSeq;  // don't resend a frame from an earlier session
  bool first = true;
  while (true) {
    if (!nextFrame(seen, buf, cap, len, first ? FIRST_FRAME_WAIT_MS : NEXT_FRAME_WAIT_MS)) {
      Serial.println("Live view: no new frames, ending remote view");
      break;
    }
    first = false;
    const uint32_t t0 = millis();
    bool keepGoing;
    if (useWs) {
      keepGoing = ws.sendBinary(buf, len);
      String msg;
      while (keepGoing && ws.pollText(msg)) {
        if (stoppedIn(msg)) keepGoing = false;  // the last viewer left
      }
      if (keepGoing && !ws.connected()) {
        Serial.printf("Live view: WebSocket closed (%s)\n", ws.lastError().c_str());
        keepGoing = false;
      }
    } else {
      HTTPClient http;
      keepGoing = false;
      if (conn.begin(http, base + "/frame", 15000, true /* keep open between frames */)) {
        http.addHeader("Authorization", auth);
        http.addHeader("Content-Type", "image/jpeg");
        int status = http.POST(buf, len);
        keepGoing = status == 200 && watchingIn(http.getString());
        http.end();
      }
    }
    portENTER_CRITICAL(&statsMux);
    stats.remoteFrames++;
    stats.remoteMs += millis() - t0;
    portEXIT_CRITICAL(&statsMux);
    if (!keepGoing) break;
  }
  ws.close();
  conn.close();
  free(buf);
  remoteWanted = false;
}

static void remoteTask(void*) {
  const String base = config->serverUrl + "/api/nodes/" + config->nodeId + "/live";
  while (true) {
    if (!net::ensureWifi(*config)) {
      delay(RETRY_MS);
      continue;
    }
    HTTPClient http;
    if (!conn.begin(http, base + "/wait", 40000, true /* keep open between checks */)) {
      delay(RETRY_MS);
      continue;
    }
    http.addHeader("Authorization", "Bearer " + config->deviceToken);
    int status = http.GET();
    String body = status > 0 ? http.getString() : "";
    http.end();
    if (status != 200) {
      conn.close();
      Serial.printf("Live view: server unreachable (%d), will retry\n", status);
      delay(RETRY_MS);
      continue;
    }
    if (!watchingIn(body)) continue;
    if (held) Serial.println("Live view requested; waiting for the current count to finish");
    streamRemote(base);
  }
}

// ---- Local view: http://<board IP>/ on the same Wi-Fi ----

static bool keyMatches(httpd_req_t* req) {
  char query[96], given[40];
  return httpd_req_get_url_query_str(req, query, sizeof(query)) == ESP_OK &&
         httpd_query_key_value(query, "key", given, sizeof(given)) == ESP_OK && key == given;
}

static esp_err_t pageHandler(httpd_req_t* req) {
  if (!keyMatches(req)) {
    httpd_resp_set_status(req, "403 Forbidden");
    return httpd_resp_sendstr(req, "Open this from the ShelfEye dashboard's Cameras page.");
  }
  String html =
      "<!doctype html><html><head><meta name=viewport content='width=device-width,initial-scale=1'>"
      "<title>ShelfEye " + config->nodeId + " (local)</title>"
      "<style>body{margin:0;background:#000;color:#ccc;font:14px sans-serif;text-align:center}"
      "img{display:block;width:100%;max-width:960px;margin:0 auto}p{margin:10px}</style></head><body>"
      "<img src='/stream?key=" + key + "' alt='Live view'>"
      "<p>ShelfEye " + config->nodeId + ", local live view. Counting pauses while this page is open.</p>"
      "</body></html>";
  httpd_resp_set_type(req, "text/html");
  return httpd_resp_send(req, html.c_str(), html.length());
}

static esp_err_t streamHandler(httpd_req_t* req) {
  if (!keyMatches(req)) {
    httpd_resp_set_status(req, "403 Forbidden");
    return httpd_resp_sendstr(req, "Wrong or missing key");
  }
  httpd_resp_set_type(req, "multipart/x-mixed-replace;boundary=FRAME");
  httpd_resp_set_hdr(req, "Cache-Control", "no-cache, no-store");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  localViewers++;
  Serial.println("Local live view: viewer connected");

  uint8_t* buf = nullptr;
  size_t cap = 0, len = 0;
  uint32_t seen = latestSeq;
  bool first = true;
  char head[96];
  while (nextFrame(seen, buf, cap, len, first ? FIRST_FRAME_WAIT_MS : NEXT_FRAME_WAIT_MS)) {
    first = false;
    const uint32_t t0 = millis();
    int n = snprintf(head, sizeof(head), "--FRAME\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", (unsigned)len);
    if (httpd_resp_send_chunk(req, head, n) != ESP_OK ||
        httpd_resp_send_chunk(req, reinterpret_cast<const char*>(buf), len) != ESP_OK ||
        httpd_resp_send_chunk(req, "\r\n", 2) != ESP_OK) {
      break;  // the viewer closed the page
    }
    portENTER_CRITICAL(&statsMux);
    stats.localFrames++;
    stats.localMs += millis() - t0;
    portEXIT_CRITICAL(&statsMux);
  }
  free(buf);
  localViewers--;
  Serial.println("Local live view: viewer left");
  return ESP_OK;
}

static void startLocalServer() {
  Preferences prefs;  // the link key is made once and kept, so dashboard links stay valid
  prefs.begin("liveview", false);
  key = prefs.getString("key", "");
  if (key.length() != 20) {
    uint8_t b[10];
    esp_fill_random(b, sizeof(b));
    char hex[21];
    for (int i = 0; i < 10; i++) sprintf(hex + i * 2, "%02x", b[i]);
    key = hex;
    prefs.putString("key", key);
  }
  prefs.end();

  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.stack_size = 8192;
  cfg.lru_purge_enable = true;  // a viewer who vanished doesn't block the next one
  cfg.send_wait_timeout = 5;
  httpd_handle_t server = nullptr;
  if (httpd_start(&server, &cfg) != ESP_OK) {
    Serial.println("Local live view couldn't start");
    key = "";
    return;
  }
  httpd_uri_t page = {.uri = "/", .method = HTTP_GET, .handler = pageHandler, .user_ctx = nullptr};
  httpd_uri_t stream = {.uri = "/stream", .method = HTTP_GET, .handler = streamHandler, .user_ctx = nullptr};
  httpd_register_uri_handler(server, &page);
  httpd_register_uri_handler(server, &stream);
}

void start(const Config& cfg) {
  config = &cfg;
  if (!cfg.liveView && !cfg.localView) return;
  frameLock = xSemaphoreCreateMutex();
  // Converting frames is the heavy part: give it core 1 (shared with the mostly
  // idle counting loop) and keep the network senders on core 0 with Wi-Fi.
  xTaskCreatePinnedToCore(captureTask, "live-capture", 8192, nullptr, 1, nullptr, 1);
  if (cfg.liveView) {
    xTaskCreatePinnedToCore(remoteTask, "live-remote", 12288, nullptr, 1, nullptr, 0);
    Serial.printf("Live view ready, sent through %s\n", cfg.serverUrl.c_str());
  }
  if (cfg.localView) {
    startLocalServer();
    if (!key.isEmpty()) {
      Serial.printf("Local live view ready at http://%s/?key=%s (also linked on the dashboard's Cameras page)\n",
                    WiFi.localIP().toString().c_str(), key.c_str());
    }
  }
}

}  // namespace live_view
