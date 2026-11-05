# ShelfEye

A camera on the shelf counts the stock, so nobody has to count by hand.

```
Pi Zero W + Camera Module 3                         Server                Dashboard
┌─────────────────────────────────────┐   HTTPS   ┌──────────────┐  API  ┌──────────┐
│ capture → changed? → still? → OpenAI│ ────────► │ FastAPI +    │ ◄──── │ Next.js  │
│ count → compare → save to SD → queue│  readings │ SQLite       │       │          │
└─────────────────────────────────────┘           └──────────────┘       └──────────┘
```

## How it works

1. The Pi takes a photo every `CAPTURE_INTERVAL_SECONDS`.
2. It compares a tiny greyscale copy with the last analysed photo. If less than
   `CHANGE_THRESHOLD` of the image changed, it skips the OpenAI call.
3. It waits until two frames in a row match, so a hand reaching in isn't counted.
4. It sends the photo and the shelf's product list (`catalog.json`) to OpenAI
   and gets back JSON: product name, count and the label text it read.
5. It compares the result with the last counts in its SQLite database on the SD
   card, records the changes (e.g. "Paracetamol 6 → 5") and queues the reading.
6. The queue is pushed to the server. If the network is down, readings wait on
   the SD card and are sent later.
7. Every `RECHECK_MINUTES` it re-counts anyway, to correct any drift.

## Folders

- `device/` runs on the Pi
- `server/` holds the API that the Pis post readings to (FastAPI + SQLite)
- `dashboard/` holds the web dashboard (Next.js)

## Run the server

```bash
cd server
pip install -r requirements.txt
SHELFEYE_DEVICE_TOKEN=change-me uvicorn app:app --host 0.0.0.0 --port 8000
```

## Run the dashboard

```bash
cd dashboard
npm install
cp .env.example .env.local     # set SHELFEYE_API_URL if the server isn't on localhost:8000
npm run dev                    # or: npm run build && npm start
```

Open http://localhost:3000 and create an account on the Register page. The
dashboard forwards `/api/*` calls to the server, so the server needs no CORS
setup. It refreshes every 10 seconds.

Pages: Overview, Inventory, Activity and Cameras (with live view). Every page
and dashboard API call requires a login. Accounts are stored in the server's
SQLite database with scrypt-hashed passwords, and sessions last 30 days.
Anyone who can open the dashboard can register, so keep it on a private
network until invite-only sign-up is added.

## Test the device code on a laptop (no camera needed)

```bash
cd device
pip install -r requirements.txt
cp shelfeye.env.example shelfeye.env      # fill in your OpenAI key; set SHELFEYE_DATA_DIR=./shelfeye-data
cp catalog.example.json catalog.json      # set SHELFEYE_CATALOG=./catalog.json
python -m shelfeye_device --config shelfeye.env --image path/to/shelf-photo.jpg
```

Run it on two photos (before and after taking an item) to see a change
reach the dashboard.

## Set up the Pi

Use a **Pi Zero W or Zero 2 W**, because the plain Pi Zero has no Wi-Fi. Camera
Module 3 needs the Pi Zero camera cable (22-pin to 15-pin).

1. Flash **Raspberry Pi OS Lite** with Raspberry Pi Imager, setting Wi-Fi and SSH
   in the imager's settings.
2. Install the dependencies (use apt, since pip builds are very slow on the Zero):
   ```bash
   sudo apt update
   sudo apt install -y python3-picamera2 python3-pil python3-requests --no-install-recommends
   ```
3. Check the camera works: `rpicam-still -o test.jpg`
4. Copy the `device/` folder to `/home/pi/shelfeye/device`, then:
   ```bash
   sudo mkdir -p /etc/shelfeye
   sudo cp shelfeye.env.example /etc/shelfeye/shelfeye.env    # then edit it
   sudo cp catalog.example.json /etc/shelfeye/catalog.json     # list your products
   sudo chmod 600 /etc/shelfeye/shelfeye.env                   # it holds your API key
   ```
5. Start it on boot:
   ```bash
   sudo cp shelfeye.service /etc/systemd/system/
   sudo systemctl enable --now shelfeye
   journalctl -u shelfeye -f    # watch the logs
   ```

## Tips for accurate counts

- Mount the camera firmly. If it moves, every frame looks like a change.
- Light the shelf evenly, and keep labels facing the camera.
- Use one camera per shelf section, so items aren't too small in the photo.
- Items hidden behind the front row can't be counted. Treat the count as
  visible stock.
