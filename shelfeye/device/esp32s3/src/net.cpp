#include "net.h"

#include <WiFi.h>
#include <time.h>

#include "certs.h"
#include "storage.h"

namespace net {

static String customCa;  // kept alive for as long as the clients use it

void loadCustomCa() {
  String pem;
  if (storage::readFile("/ca.pem", pem) && pem.indexOf("BEGIN CERTIFICATE") >= 0) {
    customCa = pem;
    Serial.println("Using /ca.pem for HTTPS certificates");
  }
}

bool connectWifi(const Config& cfg, uint32_t timeoutMs) {
  if (WiFi.status() == WL_CONNECTED) return true;
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(true);  // modem sleep between packets saves battery
  WiFi.setAutoReconnect(true);
  WiFi.begin(cfg.wifiSsid.c_str(), cfg.wifiPassword.c_str());
  uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < timeoutMs) delay(250);
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("Wi-Fi connected to %s, IP %s\n", cfg.wifiSsid.c_str(), WiFi.localIP().toString().c_str());
    return true;
  }
  Serial.printf("Wi-Fi: couldn't connect to %s\n", cfg.wifiSsid.c_str());
  return false;
}

bool ensureWifi(const Config& cfg) {
  if (WiFi.status() == WL_CONNECTED) return true;
  WiFi.disconnect();
  return connectWifi(cfg);
}

bool clockIsSet() { return time(nullptr) > 1700000000; }  // after Nov 2023

bool syncClock(uint32_t timeoutMs) {
  configTime(0, 0, "pool.ntp.org", "time.google.com", "time.cloudflare.com");
  uint32_t started = millis();
  while (!clockIsSet() && millis() - started < timeoutMs) delay(200);
  return clockIsSet();
}

static String format(const char* pattern, time_t t) {
  struct tm tm;
  gmtime_r(&t, &tm);
  char buf[40];
  strftime(buf, sizeof(buf), pattern, &tm);
  return buf;
}

String nowIso() { return format("%Y-%m-%dT%H:%M:%S+00:00", time(nullptr)); }
String today() { return format("%Y-%m-%d", time(nullptr)); }
String timeOfDay() { return format("%H%M%S", time(nullptr)); }
String dateDaysAgo(uint32_t days) { return format("%Y-%m-%d", time(nullptr) - (time_t)days * 86400); }

bool Connection::begin(HTTPClient& http, const String& url, uint32_t timeoutMs, bool keepOpen) {
  http.setReuse(keepOpen);
  http.setConnectTimeout(15000);
  http.setTimeout(min<uint32_t>(timeoutMs, 65000));  // HTTPClient takes a 16-bit value
  if (url.startsWith("https://")) {
    secure_.setCACert(customCa.isEmpty() ? ROOT_CA_BUNDLE : customCa.c_str());
    secure_.setTimeout(timeoutMs / 1000);
    return http.begin(secure_, url);
  }
  return http.begin(plain_, url);
}

void setupTls(WiFiClientSecure& client, uint32_t timeoutMs) {
  client.setCACert(customCa.isEmpty() ? ROOT_CA_BUNDLE : customCa.c_str());
  client.setTimeout(timeoutMs / 1000);  // seconds; only covers connecting
  // The read timeout (readBytes, readStringUntil) is separate and defaults to 1 s.
  static_cast<Stream&>(client).setTimeout(timeoutMs);
}

void Connection::close() {
  secure_.stop();
  plain_.stop();
}

}  // namespace net
