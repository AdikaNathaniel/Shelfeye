# ShelfEye on the ESP32-S3

The same shelf camera as the Raspberry Pi version (`../shelfeye_device`), as
firmware for an ESP32-S3 camera board: it photographs the shelf, counts the
products with OpenAI when the shelf changes, keeps unsent readings in its
flash storage, and reports to the same ShelfEye server and dashboard.

Written for a generic **ESP32-S3 CAM** board (ESP32-S3, 8 MB flash, 8 MB PSRAM,
OV3660 or OV2640 camera, microSD slot) with the ESP32-S3-EYE pin layout.

## Secrets stay off the firmware

Wi-Fi, the OpenAI key and the device token are read at start-up from a `.env`
file, never from the source code, and they are not compiled into the firmware.
They live in the board's flash storage (sent separately from the firmware), or
on a microSD card if one is inserted. `.env` files are in `.gitignore`; only
`.env.example` is committed.

## Set up (no SD card)

1. Install [PlatformIO](https://platformio.org/) (the VS Code extension, or `pip install platformio`).
2. Copy `.env.example` to `data/.env` and fill it in (Wi-Fi, OpenAI key, device token).
3. Connect the board over USB-C and, from this folder, run:
   ```
   pio run -t uploadfs     # sends data/.env to the board's flash storage
   pio run -t upload       # builds and flashes the firmware
   pio device monitor      # shows the log
   ```
   The log should show `Storage: flash`, then `ShelfEye shelf-1 ready`,
   `Counting: first photo since start-up` and the counts a few seconds later.

**Changing a setting later:** edit `data/.env` and run `pio run -t uploadfs`
again. The firmware isn't rebuilt or replaced.

Without a card no photos are kept (the flash storage is only about 1.5 MB);
counting, live view and unsent-reading retries all work as normal.

### With a microSD card instead

Format it as FAT32 (up to 32 GB), put the filled-in `.env` in its root, insert it
and restart the board. The card then takes over from flash, and every counted
photo is kept on it for the retention period set on the dashboard.

## How it maps to the Pi version

| Pi (`shelfeye_device/`) | ESP32-S3 (`src/`) |
|---|---|
| `config.py` + `/etc/shelfeye/shelfeye.env` | `config.cpp` + `/.env` in flash (from `data/.env`) |
| `camera.py` (Picamera2) | `camera.cpp` (esp32-camera) |
| `imaging.py` (Pillow fingerprint) | `imaging.cpp` (decode at 1/8 scale, 160x120 grey) |
| `vision.py` | `vision.cpp` (streams the base64 image, no big buffer) |
| `store.py` (SQLite) | `store.cpp` (JSON files in flash + Preferences) |
| `uploader.py` | `uploader.cpp` |
| `live_view.py` | `live_view.cpp` (background task on core 0) |
| `main.py` | `main.cpp` |
| systemd restart + camera watchdog | ESP task watchdog: restarts if the loop hangs 3 minutes |

## Battery

Set `DEEP_SLEEP=on` in `.env` to sleep between photos: the board then draws a
few milliamps instead of ~100 mA while waiting, at the cost of live view. The
last counted photo's fingerprint is saved to flash, so change detection carries
on across sleeps.

## If something's wrong

- **`Camera init failed`**: the pins in `src/board_pins.h` don't match your board.
- **No log at all**: your board may use a separate USB-to-serial chip; set `-DARDUINO_USB_CDC_ON_BOOT=0` in `platformio.ini` and reflash.
- **`No /.env found on the flash`**: run `pio run -t uploadfs` (the file must be `data/.env`).
  With a card, it must be in the card's root, named exactly `.env`.
- **HTTPS errors (`-1`)**: the clock isn't set yet, or a server changed certificate
  authority. Put that authority's root certificate (PEM) at `/ca.pem` on the card.
