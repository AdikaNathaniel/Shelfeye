// Wi-Fi, clock and HTTP(S) connections.
#pragma once
#include <Arduino.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>

#include "config.h"

namespace net {

bool connectWifi(const Config& cfg, uint32_t timeoutMs = 20000);
bool ensureWifi(const Config& cfg);    // reconnect if the connection dropped
bool syncClock(uint32_t timeoutMs = 15000);
bool clockIsSet();

String nowIso();          // UTC, e.g. 2026-11-05T15:00:34+00:00
String today();           // UTC date, e.g. 2026-11-05
String timeOfDay();       // UTC, e.g. 150034
String dateDaysAgo(uint32_t days);

// One connection per task (the live view runs in its own task). HTTPS
// certificates are checked against the roots in certs.h, or /ca.pem in storage if present.
class Connection {
 public:
  explicit Connection(const char* name) : name_(name) {}
  // Starts a request to `url` on `http`; picks plain or TLS transport from the URL.
  // With keepOpen, the connection stays open after http.end() and the next request
  // reuses it, skipping the slow (seconds-long) TLS handshake.
  bool begin(HTTPClient& http, const String& url, uint32_t timeoutMs, bool keepOpen = false);
  void close();  // drop a kept-open connection, e.g. after an error

 private:
  const char* name_;
  WiFiClientSecure secure_;
  WiFiClient plain_;
};

void loadCustomCa();  // reads /ca.pem from storage if present

// Sets the trusted certificates and timeout on a TLS client used directly.
void setupTls(WiFiClientSecure& client, uint32_t timeoutMs);

}  // namespace net
