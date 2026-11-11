// Device settings, read at start-up from /.env in flash (or on an optional SD card).
// Nothing secret is compiled into the firmware. See .env.example for every key.
#pragma once
#include <Arduino.h>
#include <vector>

struct Config {
  String nodeId;
  String wifiSsid;
  String wifiPassword;
  String openaiApiKey;
  String openaiModel;
  String serverUrl;
  String deviceToken;
  std::vector<String> catalog;  // product names expected on this shelf
  uint32_t captureIntervalSeconds;
  float changeThreshold;
  uint32_t recheckMinutes;
  uint32_t keepImagesDays;
  bool liveView;
  float liveViewFps;
  uint32_t liveViewMaxMinutes;
  bool localView;     // fast video at http://<board IP>/ for viewers on the same Wi-Fi
  bool deepSleep;     // sleep between photos to save battery (turns live view off)
  String frameSize;   // camera resolution for counting photos, e.g. UXGA
  int jpegQuality;    // 4 (best) .. 63
};

// Loads the config. Returns false (and explains why in `error`) if a required key is missing.
bool loadConfig(Config& cfg, String& error);
