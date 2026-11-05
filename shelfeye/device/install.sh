#!/bin/bash
# Installs ShelfEye on the Pi. Copy the whole device/ folder (with your filled-in
# shelfeye.env and catalog.json) to the SD card's boot partition as "shelfeye", then run:
#   sudo bash /boot/firmware/shelfeye/install.sh
set -e

SRC="$(cd "$(dirname "$0")" && pwd)"
PI_USER="${SHELFEYE_USER:-${SUDO_USER:-$(ls /home | head -n 1)}}"
HOME_DIR="/home/$PI_USER"

echo "Installing packages..."
apt-get update
apt-get install -y --no-install-recommends python3-picamera2 python3-pil python3-requests

echo "Copying ShelfEye to $HOME_DIR/shelfeye/device..."
mkdir -p "$HOME_DIR/shelfeye/device"
cp -r "$SRC/shelfeye_device" "$HOME_DIR/shelfeye/device/"
chown -R "$PI_USER:$PI_USER" "$HOME_DIR/shelfeye"

echo "Installing config to /etc/shelfeye..."
mkdir -p /etc/shelfeye
if [ -f "$SRC/shelfeye.env" ]; then
    sed "s#/home/pi/#$HOME_DIR/#g" "$SRC/shelfeye.env" > /etc/shelfeye/shelfeye.env
    # The env file holds the API key: readable only by the ShelfEye user, and
    # removed from the boot partition, which anyone with the card can read.
    chown "$PI_USER:$PI_USER" /etc/shelfeye/shelfeye.env
    chmod 600 /etc/shelfeye/shelfeye.env
    rm -f "$SRC/shelfeye.env"
else
    echo "WARNING: no shelfeye.env found. Copy shelfeye.env.example to /etc/shelfeye/shelfeye.env and edit it."
fi
[ -f "$SRC/catalog.json" ] && cp "$SRC/catalog.json" /etc/shelfeye/catalog.json

echo "Enabling the ShelfEye service..."
sed -e "s#User=pi#User=$PI_USER#" -e "s#/home/pi/#$HOME_DIR/#g" \
    "$SRC/shelfeye.service" > /etc/systemd/system/shelfeye.service
systemctl daemon-reload
systemctl enable --now shelfeye

echo "Done. Watch the logs with: journalctl -u shelfeye -f"
