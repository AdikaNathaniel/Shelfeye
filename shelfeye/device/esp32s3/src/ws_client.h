// A minimal WebSocket client over TLS (wss://), just enough for live view: one
// connection held open for the whole session, binary JPEG frames up, short text
// messages down. Saves the request-and-reply round trip per frame that plain
// HTTP POSTs need.
#pragma once
#include <Arduino.h>
#include <WiFiClientSecure.h>

class WsClient {
 public:
  // `url` is https://host/path (sent as wss://). `authorization` is the full header value.
  bool connect(const String& url, const String& authorization, uint32_t timeoutMs);
  bool sendBinary(const uint8_t* data, size_t len);
  // A text message from the server, if one has arrived. Never blocks for long.
  bool pollText(String& out);
  bool connected();
  void close();
  String lastError() const { return error_; }

 private:
  bool writeAll(const uint8_t* data, size_t len);
  bool sendFrame(uint8_t opcode, const uint8_t* data, size_t len);

  WiFiClientSecure client_;
  String error_;
  bool open_ = false;
};
