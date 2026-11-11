#include "store.h"

#include <ArduinoJson.h>
#include <Preferences.h>
#include <algorithm>
#include <set>

#include "imaging.h"
#include "storage.h"

namespace store {

static const char* COUNTS_PATH = "/shelfeye/counts.json";
static const char* OUTBOX_DIR = "/shelfeye/outbox";
static const char* FINGERPRINT_PATH = "/shelfeye/last.fp";
static Preferences prefs;

void begin() {
  storage::ensureDir(OUTBOX_DIR);
  prefs.begin("shelfeye", false);
}

std::map<String, int> currentCounts() {
  std::map<String, int> counts;
  String text;
  if (!storage::readFile(COUNTS_PATH, text)) return counts;
  JsonDocument doc;
  if (deserializeJson(doc, text)) return counts;
  for (JsonPair kv : doc.as<JsonObject>()) counts[kv.key().c_str()] = kv.value().as<int>();
  return counts;
}

std::vector<Change> applyReading(const std::vector<Item>& items, const String& capturedAt) {
  std::map<String, int> previous = currentCounts();
  std::map<String, int> current;
  for (const Item& item : items) current[item.name] = item.count;

  std::set<String> names;
  for (auto& kv : previous) names.insert(kv.first);
  for (auto& kv : current) names.insert(kv.first);

  std::vector<Change> changes;
  JsonDocument doc;
  for (const String& name : names) {  // std::set keeps them sorted, like the Pi
    int before = previous.count(name) ? previous[name] : 0;
    int after = current.count(name) ? current[name] : 0;
    if (before != after) changes.push_back({name, before, after});
    doc[name] = after;
  }
  String text;
  serializeJson(doc, text);
  storage::writeFile(COUNTS_PATH, text);
  return changes;
}

void queue(const String& readingId, const String& payloadJson) {
  // Filenames start with the time, so sorting them gives the oldest first. They're
  // kept short: flash (LittleFS) refuses paths over 64 characters, and the full
  // reading id is inside the file anyway.
  String path = String(OUTBOX_DIR) + "/" + String((uint32_t)time(nullptr)) + "_" + readingId.substring(0, 8) + ".json";
  if (!storage::writeFile(path, payloadJson)) Serial.printf("Couldn't save the reading to %s\n", path.c_str());
}

std::vector<String> pendingIds() {
  std::vector<String> ids;
  File dir = storage::filesystem().open(OUTBOX_DIR);
  if (!dir || !dir.isDirectory()) return ids;
  for (File f = dir.openNextFile(); f; f = dir.openNextFile()) {
    String name = String(f.name()).substring(String(f.name()).lastIndexOf('/') + 1);
    f.close();
    if (name.endsWith(".json")) ids.push_back(name.substring(0, name.length() - 5));
  }
  dir.close();
  std::sort(ids.begin(), ids.end());
  return ids;
}

bool readPending(const String& id, String& payload) {
  return storage::readFile(String(OUTBOX_DIR) + "/" + id + ".json", payload);
}

void removePending(const String& id) { storage::filesystem().remove(String(OUTBOX_DIR) + "/" + id + ".json"); }

uint32_t keepImagesDays(uint32_t fallback) { return prefs.getUInt("keep_days", fallback); }

void setKeepImagesDays(uint32_t days) {
  if (prefs.getUInt("keep_days", 0) != days) {
    Serial.printf("Dashboard set photo retention to %u days\n", days);
    prefs.putUInt("keep_days", days);
  }
}

bool saveFingerprint(const uint8_t* fp) { return storage::writeBytes(FINGERPRINT_PATH, fp, imaging::FP_SIZE); }
bool loadFingerprint(uint8_t* fp) { return storage::readBytes(FINGERPRINT_PATH, fp, imaging::FP_SIZE); }

}  // namespace store
