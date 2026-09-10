# AI-Based Real-Time Accident Detection System


A runnable Flask + OpenCV + YOLO smart-city traffic dashboard designed for demonstration/prototyping in Dubai, Riyadh, Kuwait City, Doha, Muscat and Manama.

## Features

- Live webcam preview
- Video/image upload
- YOLO vehicle detection (cars, buses, trucks, motorcycles)
- Vehicle counters and animated dashboard
- Traffic density and LOW/MEDIUM/HIGH classification
- Demo accident detection using a motion/collision heuristic
- Simulated emergency alerts (never contacts real emergency services)
- AI-style adaptive traffic-signal recommendation
- Real-time dashboard updates
- CSV analytics export
- Responsive dark smart-city UI

## Requirements

Python 3.10+ is recommended.

## Run

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

On first YOLO use, Ultralytics may download `yolo11n.pt`. An internet connection is needed for that first model download.

## Notes about accident detection

This project intentionally uses a demo heuristic rather than claiming certified accident detection. It looks for abrupt motion/scene changes around tracked vehicle regions and combines them with vehicle overlap/proximity. For production deployment, replace `detect_accident()` with a trained video action-recognition / collision model and validate it on locally representative CCTV data.

Emergency notifications are simulated in the UI and server logs. No real ambulance, police or emergency service is contacted.

## Optional camera

The browser's "Start Camera" button uses the browser webcam for preview. Browser camera access is not sent to the server by default. Uploaded media is processed server-side by OpenCV/YOLO.

## API

- `GET /api/status?city=Riyadh`
- `POST /api/process-image`
- `POST /api/process-video`
- `GET /api/analytics.csv?city=Riyadh`

