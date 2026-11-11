// Local storage of counts, unsent readings and settings (the Pi's store.py).
//
//   /shelfeye/counts.json          {"Product": count, ...}
//   /shelfeye/outbox/<id>.json     readings waiting to be sent to the server
//   /shelfeye/last.fp              fingerprint of the last counted photo (for deep sleep)
//   Preferences "shelfeye"         settings from the dashboard (photo retention)
#pragma once
#include <Arduino.h>
#include <map>
#include <vector>

#include "vision.h"

struct Change {
  String name;
  int previous;
  int current;
};

namespace store {

void begin();

std::map<String, int> currentCounts();
// Saves new counts and returns what changed. Products missing from `items` count as 0.
std::vector<Change> applyReading(const std::vector<Item>& items, const String& capturedAt);

void queue(const String& readingId, const String& payloadJson);
std::vector<String> pendingIds();   // oldest first
bool readPending(const String& id, String& payload);
void removePending(const String& id);

uint32_t keepImagesDays(uint32_t fallback);  // the dashboard's value if it ever sent one
void setKeepImagesDays(uint32_t days);

bool saveFingerprint(const uint8_t* fp);
bool loadFingerprint(uint8_t* fp);

}  // namespace store
