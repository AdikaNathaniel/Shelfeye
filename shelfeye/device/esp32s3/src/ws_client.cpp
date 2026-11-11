#include "ws_client.h"

#include "net.h"

static const uint32_t WRITE_TIMEOUT_MS = 10000;

static String base64(const uint8_t* in, size_t n) {
  static const char* B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  String out;
  for (size_t i = 0; i < n; i += 3) {
    uint32_t v = (uint32_t)in[i] << 16 | (i + 1 < n ? (uint32_t)in[i + 1] << 8 : 0) | (i + 2 < n ? in[i + 2] : 0);
    out += B64[(v >> 18) & 63];
    out += B64[(v >> 12) & 63];
    out += i + 1 < n ? B64[(v >> 6) & 63] : '=';
    out += i + 2 < n ? B64[v & 63] : '=';
  }
  return out;
}

bool WsClient::connect(const String& url, const String& authorization, uint32_t timeoutMs) {
  close();
  error_ = "";
  if (!url.startsWith("https://")) {
    error_ = "needs an https:// server";
    return false;
  }
  String rest = url.substring(8);
  int slash = rest.indexOf('/');
  String host = slash < 0 ? rest : rest.substring(0, slash);
  String path = slash < 0 ? "/" : rest.substring(slash);
  uint16_t port = 443;
  int colon = host.indexOf(':');
  if (colon >= 0) {
    port = host.substring(colon + 1).toInt();
    host = host.substring(0, colon);
  }

  net::setupTls(client_, timeoutMs);
  if (!client_.connect(host.c_str(), port)) {
    error_ = "couldn't connect to " + host;
    return false;
  }
  uint8_t keyBytes[16];
  esp_fill_random(keyBytes, sizeof(keyBytes));
  String request = "GET " + path + " HTTP/1.1\r\nHost: " + host +
                   "\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\n" +
                   "Sec-WebSocket-Key: " + base64(keyBytes, sizeof(keyBytes)) + "\r\n" +
                   "Authorization: " + authorization + "\r\n\r\n";
  if (!writeAll(reinterpret_cast<const uint8_t*>(request.c_str()), request.length())) {
    error_ = "couldn't send the WebSocket request";
    client_.stop();
    return false;
  }
  String status = client_.readStringUntil('\n');
  if (status.indexOf(" 101") < 0) {
    status.trim();
    error_ = "server answered \"" + status + "\"";
    client_.stop();
    return false;
  }
  while (client_.connected()) {  // skip the rest of the reply's headers
    String line = client_.readStringUntil('\n');
    line.trim();
    if (line.isEmpty()) break;
  }
  open_ = true;
  return true;
}

bool WsClient::writeAll(const uint8_t* data, size_t len) {
  const uint32_t started = millis();
  size_t sent = 0;
  while (sent < len) {
    if (!client_.connected() || millis() - started > WRITE_TIMEOUT_MS) return false;
    size_t n = client_.write(data + sent, len - sent);
    if (n == 0) {
      delay(5);
      continue;
    }
    sent += n;
  }
  return true;
}

// Client-to-server frames must be masked: XORed with a random 4-byte key.
bool WsClient::sendFrame(uint8_t opcode, const uint8_t* data, size_t len) {
  if (!open_) return false;
  uint8_t head[14];
  size_t h = 0;
  head[h++] = 0x80 | opcode;  // final fragment
  if (len < 126) {
    head[h++] = 0x80 | len;
  } else if (len < 65536) {
    head[h++] = 0x80 | 126;
    head[h++] = len >> 8;
    head[h++] = len & 0xFF;
  } else {
    head[h++] = 0x80 | 127;
    for (int i = 7; i >= 0; i--) head[h++] = i < 4 ? (uint64_t)len >> (8 * i) & 0xFF : 0;
  }
  uint8_t mask[4];
  esp_fill_random(mask, sizeof(mask));
  memcpy(head + h, mask, 4);
  h += 4;
  if (!writeAll(head, h)) return false;

  static uint8_t chunk[1436];  // one TLS record's worth at a time
  for (size_t done = 0; done < len;) {
    size_t n = min(sizeof(chunk), len - done);
    for (size_t i = 0; i < n; i++) chunk[i] = data[done + i] ^ mask[(done + i) & 3];
    if (!writeAll(chunk, n)) return false;
    done += n;
  }
  return true;
}

bool WsClient::sendBinary(const uint8_t* data, size_t len) {
  if (sendFrame(0x2, data, len)) return true;
  error_ = "sending a frame failed";
  open_ = false;
  return false;
}

bool WsClient::pollText(String& out) {
  while (open_ && client_.available() >= 2) {
    uint8_t b0 = client_.read();
    uint8_t b1 = client_.read();
    uint64_t len = b1 & 0x7F;
    if (len == 126) {
      len = (uint64_t)client_.read() << 8;
      len |= client_.read();
    } else if (len == 127) {
      len = 0;
      for (int i = 0; i < 8; i++) len = len << 8 | client_.read();
    }
    if (b1 & 0x80) {  // servers don't mask, but skip a mask key if one is sent
      uint8_t ignored[4];
      client_.readBytes(ignored, 4);
    }
    if (len > 4096) {  // live view only gets short status messages
      error_ = "unexpected large message from the server";
      close();
      return false;
    }
    String payload;
    for (uint64_t i = 0; i < len; i++) {
      int c = client_.read();
      if (c < 0) {
        uint8_t one;
        if (client_.readBytes(&one, 1) != 1) break;  // waits up to the read timeout
        c = one;
      }
      payload += (char)c;
    }
    const uint8_t opcode = b0 & 0x0F;
    if (opcode == 0x1) {
      out = payload;
      return true;
    }
    if (opcode == 0x8) {  // the server closed the connection
      error_ = "the server closed the connection";
      close();
      return false;
    }
    if (opcode == 0x9) sendFrame(0xA, reinterpret_cast<const uint8_t*>(payload.c_str()), payload.length());  // ping -> pong
  }
  return false;
}

bool WsClient::connected() {
  if (open_ && !client_.connected()) {
    open_ = false;
    if (error_.isEmpty()) error_ = "the connection dropped";
  }
  return open_;
}

void WsClient::close() {
  if (open_) {
    sendFrame(0x8, nullptr, 0);
    open_ = false;
  }
  client_.stop();
}
