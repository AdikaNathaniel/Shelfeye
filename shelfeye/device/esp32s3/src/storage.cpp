#include "storage.h"

#include <LittleFS.h>
#include <SD_MMC.h>

#include "board_pins.h"

namespace storage {

static fs::FS* mounted = nullptr;
static bool sd = false;

bool begin() {
  SD_MMC.setPins(SD_CLK_PIN, SD_CMD_PIN, SD_D0_PIN);
  if (SD_MMC.begin("/sdcard", true /* 1-bit mode */) && SD_MMC.cardType() != CARD_NONE) {
    mounted = &SD_MMC;
    sd = true;
    return true;
  }
  if (LittleFS.begin(true /* format if it has never been used */)) {
    mounted = &LittleFS;
    return true;
  }
  return false;
}

fs::FS& filesystem() { return *mounted; }
bool hasSdCard() { return sd; }
const char* name() { return sd ? "SD card" : "flash"; }

bool ensureDir(const String& path) {
  if (path.isEmpty() || path == "/" || filesystem().exists(path)) return true;
  int slash = path.lastIndexOf('/');
  if (slash > 0 && !ensureDir(path.substring(0, slash))) return false;
  return filesystem().mkdir(path);
}

bool readFile(const String& path, String& out) {
  if (!filesystem().exists(path)) return false;  // optional files (catalog.json, ca.pem) may be absent
  File f = filesystem().open(path, FILE_READ);
  if (!f || f.isDirectory()) return false;
  out = f.readString();
  f.close();
  return true;
}

bool writeFile(const String& path, const String& text) {
  return writeBytes(path, reinterpret_cast<const uint8_t*>(text.c_str()), text.length());
}

bool writeBytes(const String& path, const uint8_t* data, size_t len) {
  int slash = path.lastIndexOf('/');
  if (slash > 0) ensureDir(path.substring(0, slash));
  // Write to a temporary file first, so a power cut never leaves a half-written file.
  String tmp = path + ".tmp";
  File f = filesystem().open(tmp, FILE_WRITE);
  if (!f) return false;
  size_t written = f.write(data, len);
  f.close();
  if (written != len) {
    filesystem().remove(tmp);
    return false;
  }
  filesystem().remove(path);
  return filesystem().rename(tmp, path);
}

bool readBytes(const String& path, uint8_t* data, size_t len) {
  if (!filesystem().exists(path)) return false;
  File f = filesystem().open(path, FILE_READ);
  if (!f) return false;
  size_t got = f.read(data, len);
  f.close();
  return got == len;
}

void removeTree(const String& path) {
  File dir = filesystem().open(path);
  if (!dir) return;
  if (!dir.isDirectory()) {
    dir.close();
    filesystem().remove(path);
    return;
  }
  for (File entry = dir.openNextFile(); entry; entry = dir.openNextFile()) {
    String child = path + "/" + String(entry.name()).substring(String(entry.name()).lastIndexOf('/') + 1);
    bool isDir = entry.isDirectory();
    entry.close();
    if (isDir) removeTree(child);
    else filesystem().remove(child);
  }
  dir.close();
  filesystem().rmdir(path);
}

}  // namespace storage
