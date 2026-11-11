// Sends a shelf photo to the OpenAI API and gets back product names and counts.
#pragma once
#include <Arduino.h>
#include <vector>

#include "config.h"

struct Item {
  String name;
  int count;
  String labelText;
};

// Fills `items` (duplicates merged). Returns false and sets `error` on failure.
bool analyzeImage(const Config& cfg, const uint8_t* jpeg, size_t len, std::vector<Item>& items, String& error);
