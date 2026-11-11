# Raspberry Pi vs ESP32-S3: why live video is harder on the ESP32

Notes from moving the ShelfEye shelf camera from a Raspberry Pi to an
ESP32-S3 camera board.

## Hardware compared

| | Raspberry Pi (Zero W / Zero 2 W) | ESP32-S3 CAM board |
|---|---|---|
| Fast memory | 512 MB | 512 KB (about 1000x less), plus 8 MB slower PSRAM |
| Processor | Zero W: 1 core, 1 GHz. Zero 2 W: 4 cores, 1 GHz | 2 cores, 240 MHz |
| Camera | Camera Module 3; the Pi has a hardware video encoder and enough power to make JPEGs quickly | GC2145 gives raw images: each 640x480 frame is about 600 KB, which the ESP32 converts to JPEG itself |

## What this means for ShelfEye

- **Counting works on both.** It needs one photo every 3 minutes, converted
  and sent once, which is light work even for the ESP32.
- **Live view is slow on the ESP32.** For every frame it must grab a raw
  image, convert it to JPEG and send it over an encrypted connection (about
  40 KB of the fast memory) through Render, while Wi-Fi, the camera and
  counting keep running. Expect roughly 1-3 frames a second at 640x480 with
  the GC2145 (an estimate, not yet measured).
- **Smooth video (25-30 frames a second) from anywhere** needs Pi-class
  hardware and a video streaming service, which uses far more power than a
  battery-run ESP32.

## The camera module

The board was sold as having an **OV3660**, but it reports a **GC2145**
(chip ID 0x2145), and it can't produce JPEG images.

| | OV3660 (advertised) | GC2145 (received) |
|---|---|---|
| Resolution | 3 MP (2048x1536) | 2 MP (1600x1200) |
| JPEG made by the camera | Yes | No; the ESP32 converts each image |
| Image quality | Better | Lower, especially in dim light |
| Live view speed on ESP32 | Several times faster | Slow |

An OV2640 or OV3660 module fits the same socket. The firmware detects the
camera at start-up, so swapping modules needs no code changes.
