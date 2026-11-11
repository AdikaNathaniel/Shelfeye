// Camera and microSD pins, chosen with a -D flag in platformio.ini.
// To support another board, add a block with its pin numbers.
//
// Most generic "ESP32-S3 CAM" boards (ESP32-S3-WROOM N8R8 + OV3660/OV2640 +
// microSD, like the Freenove kit) use the ESP32-S3-EYE layout below. If the
// camera fails to start, compare these numbers with your board's pinout sheet.
#pragma once

#if defined(CAMERA_MODEL_ESP32S3_EYE)
#define PWDN_GPIO_NUM -1
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 15
#define SIOD_GPIO_NUM 4
#define SIOC_GPIO_NUM 5
#define Y9_GPIO_NUM 16
#define Y8_GPIO_NUM 17
#define Y7_GPIO_NUM 18
#define Y6_GPIO_NUM 12
#define Y5_GPIO_NUM 10
#define Y4_GPIO_NUM 8
#define Y3_GPIO_NUM 9
#define Y2_GPIO_NUM 11
#define VSYNC_GPIO_NUM 6
#define HREF_GPIO_NUM 7
#define PCLK_GPIO_NUM 13
// microSD in 1-bit SD_MMC mode
#define SD_CLK_PIN 39
#define SD_CMD_PIN 38
#define SD_D0_PIN 40

#else
#error "Choose a camera layout in platformio.ini, e.g. -DCAMERA_MODEL_ESP32S3_EYE"
#endif
