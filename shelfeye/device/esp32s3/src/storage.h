// Where the device keeps its files: the microSD card if one is inserted,
// otherwise the small LittleFS partition in flash (no photos are kept then).
#pragma once
#include <Arduino.h>
#include <FS.h>

namespace storage {

bool begin();           // mount the SD card, or LittleFS as a fallback
fs::FS& filesystem();   // the mounted filesystem
bool hasSdCard();       // photos are only stored on a card
const char* name();     // "SD card" or "flash", for the log

bool ensureDir(const String& path);       // create a folder and its parents
bool readFile(const String& path, String& out);
bool writeFile(const String& path, const String& text);
bool writeBytes(const String& path, const uint8_t* data, size_t len);
bool readBytes(const String& path, uint8_t* data, size_t len);
void removeTree(const String& path);      // delete a folder and everything in it

}  // namespace storage
