#include "vision.h"

#include <ArduinoJson.h>

#include <WiFiClientSecure.h>
#include <esp_task_wdt.h>

#include "net.h"

static const char* IMAGE_MARKER = "@@IMAGE@@";

// Same instructions as the Pi (device/shelfeye_device/vision.py).
static String buildPrompt(const std::vector<String>& catalog) {
  String p =
      "You count stock on a shop shelf from a photo.\n"
      "For each distinct product, count the individual units you can see (boxes, bottles, packs).\n"
      "Read the product name from its label and copy the most legible label text into label_text.\n"
      "Only count units that are actually visible. Do not guess about rows hidden behind others.";
  if (!catalog.empty()) {
    p += "\nProducts expected on this shelf. Use these exact names when a product matches, "
         "and include every one of them, with count 0 if none are visible:";
    for (const String& name : catalog) p += "\n- " + name;
    p += "\nIf you see a product that is not in this list, add it using the name on its label.";
  }
  return p;
}

static const char* B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

// Base64 of `n` bytes into `out` (4 chars per 3 bytes, padded at the end).
static size_t base64(const uint8_t* in, size_t n, char* out) {
  size_t o = 0, i = 0;
  for (; i + 2 < n; i += 3) {
    const uint32_t v = (uint32_t)in[i] << 16 | (uint32_t)in[i + 1] << 8 | in[i + 2];
    out[o++] = B64[(v >> 18) & 63];
    out[o++] = B64[(v >> 12) & 63];
    out[o++] = B64[(v >> 6) & 63];
    out[o++] = B64[v & 63];
  }
  if (i < n) {
    const uint32_t v = (uint32_t)in[i] << 16 | (i + 1 < n ? (uint32_t)in[i + 1] << 8 : 0);
    out[o++] = B64[(v >> 18) & 63];
    out[o++] = B64[(v >> 12) & 63];
    out[o++] = i + 1 < n ? B64[(v >> 6) & 63] : '=';
    out[o++] = '=';
  }
  return o;
}

// Writes all of `data`, waiting out a full send buffer (HTTPClient gives up after one retry).
static bool writeAll(WiFiClientSecure& c, const uint8_t* data, size_t len, uint32_t deadline) {
  size_t sent = 0;
  while (sent < len) {
    if (!c.connected() || (int32_t)(millis() - deadline) > 0) return false;
    size_t n = c.write(data + sent, len - sent);
    if (n == 0) {
      delay(20);
      continue;
    }
    sent += n;
  }
  return true;
}

static String tlsError(WiFiClientSecure& c) {
  char buf[100] = "";
  int code = c.lastError(buf, sizeof(buf));
  return code ? String(buf) + " (" + String(code) + ")" : String("connection closed");
}

// One HTTPS POST to OpenAI with the JSON body prefix + base64(jpeg) + suffix,
// streamed so the ~0.5 MB body is never held in memory. Returns the HTTP status
// (or -1) and the response body.
static int postToOpenAI(const Config& cfg, const String& prefix, const uint8_t* jpeg, size_t len,
                        const String& suffix, String& response, String& error) {
  WiFiClientSecure c;
  net::setupTls(c, 90000);
  if (!c.connect("api.openai.com", 443)) {
    error = "couldn't connect to OpenAI: " + tlsError(c);
    return -1;
  }
  const size_t bodyLen = prefix.length() + ((len + 2) / 3) * 4 + suffix.length();
  String head = String("POST /v1/chat/completions HTTP/1.1\r\nHost: api.openai.com\r\n") +
                "Authorization: Bearer " + cfg.openaiApiKey + "\r\nContent-Type: application/json\r\n" +
                "Content-Length: " + String((unsigned)bodyLen) + "\r\nConnection: close\r\n\r\n";
  const uint32_t deadline = millis() + 120000;
  bool ok = writeAll(c, (const uint8_t*)head.c_str(), head.length(), deadline) &&
            writeAll(c, (const uint8_t*)prefix.c_str(), prefix.length(), deadline);
  static char chunk[4096];  // base64 of 3072 bytes
  size_t done = 0;
  while (ok && done < len) {
    size_t n = min<size_t>(3072, len - done);
    size_t out = base64(jpeg + done, n, chunk);
    ok = writeAll(c, (const uint8_t*)chunk, out, deadline);
    if (ok) done += n;
    esp_task_wdt_reset();
  }
  ok = ok && writeAll(c, (const uint8_t*)suffix.c_str(), suffix.length(), deadline);
  if (!ok) {
    error = "upload to OpenAI broke off after " + String((unsigned)(done / 1024)) + " of " +
            String((unsigned)(len / 1024)) + " KB: " + tlsError(c);
    c.stop();
    return -1;
  }

  // OpenAI takes a while to look at the photo; wait for the first byte of the reply.
  const uint32_t sentAt = millis();
  while (!c.available() && c.connected() && millis() - sentAt < 90000) {
    delay(100);
    esp_task_wdt_reset();
  }
  if (!c.available()) {
    error = c.connected() ? String("OpenAI didn't answer within 90 s")
                          : "OpenAI closed the connection without answering: " + tlsError(c);
    c.stop();
    return -1;
  }

  // Response: status line, headers, then the body (plain or chunked).
  String status = c.readStringUntil('\n');
  if (status.length() < 12) {
    error = "OpenAI's reply was cut off: " + tlsError(c);
    c.stop();
    return -1;
  }
  const int code = status.substring(9, 12).toInt();
  bool chunked = false;
  long contentLength = -1;
  while (c.connected() || c.available()) {
    String line = c.readStringUntil('\n');
    line.trim();
    if (line.isEmpty()) break;
    line.toLowerCase();
    if (line.startsWith("transfer-encoding:") && line.indexOf("chunked") >= 0) chunked = true;
    if (line.startsWith("content-length:")) contentLength = line.substring(15).toInt();
  }
  response = "";
  char buf[512];
  if (chunked) {
    while (true) {
      String sizeLine = c.readStringUntil('\n');
      sizeLine.trim();
      long size = strtol(sizeLine.c_str(), nullptr, 16);
      if (size <= 0) break;
      while (size > 0) {
        size_t got = c.readBytes(buf, min<long>(size, sizeof(buf)));
        if (got == 0) break;
        response.concat(buf, got);
        size -= got;
      }
      if (size > 0) break;  // timed out mid-chunk
      c.readStringUntil('\n');  // the CRLF after each chunk
    }
  } else {
    while ((contentLength < 0 || (long)response.length() < contentLength) && (c.connected() || c.available())) {
      size_t got = c.readBytes(buf, sizeof(buf));
      if (got == 0) break;
      response.concat(buf, got);
    }
  }
  c.stop();
  return code;
}

static void addSchema(JsonObject format) {
  format["type"] = "json_schema";
  JsonObject js = format["json_schema"].to<JsonObject>();
  js["name"] = "shelf_count";
  js["strict"] = true;
  JsonObject schema = js["schema"].to<JsonObject>();
  schema["type"] = "object";
  schema["additionalProperties"] = false;
  schema["required"].add("items");
  JsonObject items = schema["properties"]["items"].to<JsonObject>();
  items["type"] = "array";
  JsonObject item = items["items"].to<JsonObject>();
  item["type"] = "object";
  item["additionalProperties"] = false;
  item["properties"]["name"]["type"] = "string";
  item["properties"]["count"]["type"] = "integer";
  item["properties"]["label_text"]["type"] = "string";
  JsonArray required = item["required"].to<JsonArray>();
  required.add("name");
  required.add("count");
  required.add("label_text");
}

bool analyzeImage(const Config& cfg, const uint8_t* jpeg, size_t len, std::vector<Item>& items, String& error) {
  // Build the JSON around a marker, then split it where the image goes.
  JsonDocument req;
  req["model"] = cfg.openaiModel;
  JsonArray messages = req["messages"].to<JsonArray>();
  JsonObject system = messages.add<JsonObject>();
  system["role"] = "system";
  system["content"] = buildPrompt(cfg.catalog);
  JsonObject user = messages.add<JsonObject>();
  user["role"] = "user";
  JsonArray content = user["content"].to<JsonArray>();
  JsonObject text = content.add<JsonObject>();
  text["type"] = "text";
  text["text"] = "Count the products on this shelf.";
  JsonObject image = content.add<JsonObject>();
  image["type"] = "image_url";
  image["image_url"]["url"] = String("data:image/jpeg;base64,") + IMAGE_MARKER;
  image["image_url"]["detail"] = "high";
  addSchema(req["response_format"].to<JsonObject>());

  String json;
  serializeJson(req, json);
  int at = json.indexOf(IMAGE_MARKER);
  String prefix = json.substring(0, at);
  String suffix = json.substring(at + strlen(IMAGE_MARKER));
  json = String();

  Serial.printf("Sending the photo to OpenAI (%u KB)\n", (unsigned)(len / 1024));
  String response;
  int status = -1;
  for (int attempt = 1; attempt <= 2 && status < 0; attempt++) {
    status = postToOpenAI(cfg, prefix, jpeg, len, suffix, response, error);
    if (status < 0 && attempt == 1) Serial.printf("%s; trying once more\n", error.c_str());
  }
  if (status < 0) return false;
  if (status != 200) {
    error = "OpenAI returned " + String(status) + " " + response.substring(0, 300);
    return false;
  }

  JsonDocument reply;
  if (deserializeJson(reply, response)) {
    error = "OpenAI sent a reply that isn't JSON";
    return false;
  }
  JsonObject message = reply["choices"][0]["message"];
  if (!message["refusal"].isNull()) {
    error = "Model refused: " + message["refusal"].as<String>();
    return false;
  }
  JsonDocument result;
  if (deserializeJson(result, message["content"].as<const char*>())) {
    error = "The model's answer isn't the expected JSON";
    return false;
  }

  // The model occasionally lists the same product twice; merge those.
  items.clear();
  for (JsonObject entry : result["items"].as<JsonArray>()) {
    String name = entry["name"].as<String>();
    name.trim();
    int count = max(0, entry["count"].as<int>());
    bool merged = false;
    for (Item& existing : items) {
      if (existing.name == name) {
        existing.count += count;
        merged = true;
        break;
      }
    }
    if (!merged) items.push_back({name, count, entry["label_text"].as<String>()});
  }
  return true;
}
