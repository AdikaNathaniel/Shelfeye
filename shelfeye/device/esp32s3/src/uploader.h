// Talks to the ShelfEye server (the Pi's uploader.py): heartbeat and readings.
#pragma once
#include <Arduino.h>

#include "config.h"

namespace uploader {

// Tells the server this camera is alive; applies the dashboard's settings it sends back.
bool sendHeartbeat(const Config& cfg);

// Sends queued readings, oldest first. Anything unsent stays queued for next time.
void flushOutbox(const Config& cfg);

}  // namespace uploader
