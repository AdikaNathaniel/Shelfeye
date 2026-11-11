// Live view, two ways:
//
//  * Remote, through the server, so it works from any network (the Pi's
//    live_view.py). A background task keeps asking the server "is anyone
//    watching?" (each request is held open for up to 25 s). When someone is, it
//    opens one WebSocket and streams frames over it until the last viewer leaves
//    (falling back to one HTTP request per frame if WebSockets are unavailable).
//
//  * Local, straight from the board at http://<board IP>/?key=..., for viewers on
//    the same Wi-Fi: no internet, no encryption, much less delay. The dashboard's
//    Cameras page links to it (the board reports its address with each check-in).
//
// One capture task takes and converts frames while the senders upload the
// previous one, so capturing and sending overlap instead of taking turns. Every
// 5 s the log shows where the time goes. Counting pauses while anyone watches.
#pragma once
#include "config.h"

namespace live_view {

void start(const Config& cfg);

// While on, live view waits instead of starting. Counting turns it on while it
// talks to OpenAI: a camera restart and a second upload at the same time make
// that request fail on this board.
void holdOff(bool on);

// For the heartbeat: the local view's link key ("" if local view is off).
String localKey();

}  // namespace live_view
