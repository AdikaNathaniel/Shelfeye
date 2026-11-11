#include "uploader.h"

#include <ArduinoJson.h>

#include <WiFi.h>

#include "live_view.h"
#include "net.h"
#include "store.h"

namespace uploader {

static net::Connection conn("server");

bool sendHeartbeat(const Config& cfg) {
  if (cfg.serverUrl.isEmpty()) return false;
  HTTPClient http;
  if (!conn.begin(http, cfg.serverUrl + "/api/nodes/" + cfg.nodeId + "/heartbeat", 20000)) return false;
  http.addHeader("Authorization", "Bearer " + cfg.deviceToken);
  http.addHeader("Content-Type", "application/json");
  JsonDocument hb;
  hb["live_view"] = cfg.liveView;
  // For the dashboard's "Fast local view" link (same Wi-Fi only). The address can
  // change when the router or hotspot restarts, so it's sent with every check-in.
  const String key = live_view::localKey();
  if (!key.isEmpty()) {
    hb["local_ip"] = WiFi.localIP().toString();
    hb["local_view_key"] = key;
  }
  String hbBody;
  serializeJson(hb, hbBody);
  int status = http.POST(hbBody);
  String body = status > 0 ? http.getString() : "";
  http.end();
  if (status != 200) {
    Serial.printf("Heartbeat failed: %d %s\n", status, status < 0 ? HTTPClient::errorToString(status).c_str() : body.c_str());
    return false;
  }
  Serial.println("Checked in with the server");
  JsonDocument doc;
  if (!deserializeJson(doc, body)) {
    int days = doc["settings"]["keep_images_days"] | 0;
    if (days >= 1) store::setKeepImagesDays(days);
  }
  return true;
}

void flushOutbox(const Config& cfg) {
  if (cfg.serverUrl.isEmpty()) return;
  for (const String& id : store::pendingIds()) {
    String payload;
    if (!store::readPending(id, payload)) {
      store::removePending(id);  // unreadable file; don't let it block the queue
      continue;
    }
    HTTPClient http;
    if (!conn.begin(http, cfg.serverUrl + "/api/nodes/" + cfg.nodeId + "/readings", 30000)) return;
    http.addHeader("Authorization", "Bearer " + cfg.deviceToken);
    http.addHeader("Content-Type", "application/json");
    int status = http.POST(payload);
    String body = status > 0 ? http.getString() : "";
    http.end();
    if (status >= 200 && status < 300) {
      Serial.println("Reading sent to the dashboard");
      store::removePending(id);
    } else if (status == 400 || status == 422) {
      // The server will never accept this one, so don't let it block the queue.
      Serial.printf("Server rejected reading %s: %s\n", id.c_str(), body.c_str());
      store::removePending(id);
    } else {
      Serial.printf("Server unreachable (%d), will retry later\n", status);
      return;
    }
  }
}

}  // namespace uploader
