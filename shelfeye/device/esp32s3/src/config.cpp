#include "config.h"

#include <ArduinoJson.h>
#include <map>

#include "storage.h"

static const char* ENV_PATH = "/.env";
static const char* CATALOG_PATH = "/catalog.json";

// Parses KEY=VALUE lines, ignoring blank lines and # comments (same format as the Pi's env file).
static std::map<String, String> parseEnv(const String& text) {
  std::map<String, String> values;
  int start = 0;
  while (start < (int)text.length()) {
    int end = text.indexOf('\n', start);
    if (end < 0) end = text.length();
    String line = text.substring(start, end);
    start = end + 1;
    line.trim();
    if (line.isEmpty() || line.startsWith("#")) continue;
    int eq = line.indexOf('=');
    if (eq <= 0) continue;
    String key = line.substring(0, eq);
    String value = line.substring(eq + 1);
    key.trim();
    value.trim();
    if (value.length() >= 2 && (value[0] == '"' || value[0] == '\'') && value[value.length() - 1] == value[0]) {
      value = value.substring(1, value.length() - 1);
    }
    values[key] = value;
  }
  return values;
}

static bool isOn(String value) {
  value.toLowerCase();
  return !(value == "off" || value == "0" || value == "false" || value == "no" || value.isEmpty());
}

bool loadConfig(Config& cfg, String& error) {
  String text;
  if (!storage::readFile(ENV_PATH, text)) {
    error = String("No ") + ENV_PATH + " found on the " + storage::name() + ". Copy .env.example there and fill it in.";
    return false;
  }
  std::map<String, String> env = parseEnv(text);
  auto get = [&](const char* key, const char* fallback) -> String {
    auto it = env.find(key);
    return it == env.end() || it->second.isEmpty() ? String(fallback) : it->second;
  };

  cfg.nodeId = get("SHELFEYE_NODE_ID", "shelf-1");
  cfg.wifiSsid = get("WIFI_SSID", "");
  cfg.wifiPassword = get("WIFI_PASSWORD", "");
  cfg.openaiApiKey = get("OPENAI_API_KEY", "");
  cfg.openaiModel = get("OPENAI_MODEL", "gpt-4.1-mini");
  cfg.serverUrl = get("SHELFEYE_SERVER_URL", "");
  while (cfg.serverUrl.endsWith("/")) cfg.serverUrl.remove(cfg.serverUrl.length() - 1);
  cfg.deviceToken = get("SHELFEYE_DEVICE_TOKEN", "");
  cfg.captureIntervalSeconds = get("CAPTURE_INTERVAL_SECONDS", "180").toInt();
  cfg.changeThreshold = get("CHANGE_THRESHOLD", "0.01").toFloat();
  cfg.recheckMinutes = get("RECHECK_MINUTES", "30").toInt();
  cfg.keepImagesDays = get("KEEP_IMAGES_DAYS", "365").toInt();
  cfg.deepSleep = isOn(get("DEEP_SLEEP", "off"));
  // Live view needs the device awake, so deep sleep turns it off.
  cfg.liveView = isOn(get("LIVE_VIEW", "on")) && !cfg.deepSleep && !cfg.serverUrl.isEmpty();
  cfg.liveViewFps = get("LIVE_VIEW_FPS", "10").toFloat();  // an upper limit; the camera sets the real rate
  cfg.liveViewMaxMinutes = get("LIVE_VIEW_MAX_MINUTES", "10").toInt();
  cfg.localView = isOn(get("LOCAL_VIEW", "on")) && !cfg.deepSleep;
  cfg.frameSize = get("FRAME_SIZE", "UXGA");
  cfg.frameSize.toUpperCase();
  cfg.jpegQuality = constrain(get("JPEG_QUALITY", "10").toInt(), 4, 63);

  // Product list: /catalog.json (a JSON list, as on the Pi) or CATALOG=a,b,c in the env file.
  cfg.catalog.clear();
  String catalogText;
  if (storage::readFile(CATALOG_PATH, catalogText)) {
    JsonDocument doc;
    if (!deserializeJson(doc, catalogText) && doc.is<JsonArray>()) {
      for (JsonVariant name : doc.as<JsonArray>()) cfg.catalog.push_back(name.as<String>());
    }
  } else {
    String list = get("CATALOG", "");
    int start = 0;
    while (start < (int)list.length()) {
      int comma = list.indexOf(',', start);
      if (comma < 0) comma = list.length();
      String name = list.substring(start, comma);
      name.trim();
      if (!name.isEmpty()) cfg.catalog.push_back(name);
      start = comma + 1;
    }
  }

  if (cfg.wifiSsid.isEmpty()) error = "WIFI_SSID is not set in .env";
  else if (cfg.openaiApiKey.isEmpty()) error = "OPENAI_API_KEY is not set in .env";
  else if (cfg.captureIntervalSeconds < 10) error = "CAPTURE_INTERVAL_SECONDS must be at least 10";
  return error.isEmpty();
}
