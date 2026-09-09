import csv
import io
import os
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

try:
    from ultralytics import YOLO
except Exception:
    YOLO = None

BASE = Path(__file__).resolve().parent
UPLOADS = BASE / "uploads"
UPLOADS.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024

CITIES = {
    "Dubai": {"capacity": 60, "junction": "Sheikh Zayed Road / Interchange"},
    "Riyadh": {"capacity": 60, "junction": "King Fahd Road / Road Junction A"},
    "Kuwait City": {"capacity": 55, "junction": "Gulf Road / City Junction"},
    "Doha": {"capacity": 55, "junction": "Al Corniche / Central Junction"},
    "Muscat": {"capacity": 45, "junction": "Sultan Qaboos Street"},
    "Manama": {"capacity": 45, "junction": "Shaikh Khalifa Highway"},
}

# COCO IDs used by YOLO.
VEHICLE_CLASSES = {2: "cars", 3: "motorcycles", 5: "buses", 7: "trucks"}

model = None
model_error = None

def get_model():
    global model, model_error
    if model is None and model_error is None and YOLO is not None:
        try:
            model = YOLO("yolo11n.pt")
        except Exception as exc:
            model_error = str(exc)
    return model

def density_info(total, city):
    capacity = CITIES.get(city, CITIES["Riyadh"])["capacity"]
    pct = min(100, round(total / capacity * 100))
    if pct < 35:
        level = "LOW"
    elif pct < 65:
        level = "MEDIUM"
    else:
        level = "HIGH"
    if pct >= 75:
        green, red = 60, 20
    elif pct >= 50:
        green, red = 45, 30
    else:
        green, red = 30, 40
    return pct, level, green, red

def simulated_fallback(frame):
    """Fallback when YOLO cannot load: deterministic demo estimate from image texture.
    This keeps the application runnable, but clearly labels it as DEMO."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mean = float(np.mean(gray))
    std = float(np.std(gray))
    total = int(max(8, min(52, 18 + (std * 0.45) + ((255 - mean) * 0.05))))
    cars = round(total * 0.72)
    buses = max(1, round(total * 0.08))
    trucks = max(1, round(total * 0.16))
    motorcycles = max(0, total - cars - buses - trucks)
    return {
        "total": total, "cars": cars, "buses": buses,
        "trucks": trucks, "motorcycles": motorcycles,
        "detections": [], "engine": "DEMO FALLBACK"
    }

def detect_frame(frame):
    mdl = get_model()
    if mdl is None:
        return simulated_fallback(frame)

    try:
        result = mdl.predict(frame, imgsz=640, conf=0.35, verbose=False)[0]
        counts = {"cars": 0, "buses": 0, "trucks": 0, "motorcycles": 0}
        detections = []
        names = result.names

        if result.boxes is not None:
            for box in result.boxes:
                cls = int(box.cls[0])
                if cls not in VEHICLE_CLASSES:
                    continue
                label = VEHICLE_CLASSES[cls]
                conf = float(box.conf[0])
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                counts[label] += 1
                detections.append({
                    "label": label[:-1] if label.endswith("s") else label,
                    "confidence": round(conf * 100, 1),
                    "box": [x1, y1, x2, y2]
                })

        counts["total"] = sum(counts.values())
        counts["detections"] = detections
        counts["engine"] = "YOLO"
        return counts
    except Exception:
        return simulated_fallback(frame)

def draw_detections(frame, data):
    for d in data.get("detections", []):
        x1, y1, x2, y2 = d["box"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (30, 230, 170), 2)
        text = f'{d["label"]} {d["confidence"]:.0f}%'
        cv2.rectangle(frame, (x1, max(0, y1-24)), (x1+150, y1), (15, 25, 35), -1)
        cv2.putText(frame, text, (x1+5, y1-7),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255,255,255), 1, cv2.LINE_AA)
    return frame

def detect_accident(prev_gray, gray, detections):
    """Demo accident heuristic: sudden global frame change + clustered vehicle boxes.
    Not a safety-certified accident detector."""
    if prev_gray is None:
        return False, 0.0
    small_prev = cv2.resize(prev_gray, (320, 180))
    small_now = cv2.resize(gray, (320, 180))
    diff = cv2.absdiff(small_prev, small_now)
    motion = float(np.mean(diff))
    clustered = len(detections) >= 2
    score = min(99.0, motion * 3.0 + (18 if clustered else 0))
    detected = score >= 68 and clustered
    return detected, round(score, 1)

@app.route("/")
def index():
    return render_template("index.html", cities=list(CITIES.keys()))

@app.get("/api/status")
def status():
    city = request.args.get("city", "Riyadh")
    demo_total = 47
    pct, level, green, red = density_info(demo_total, city)
    return jsonify({
        "city": city,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "vehicles": {"total": 47, "cars": 34, "buses": 5, "trucks": 8, "motorcycles": 0},
        "density": pct, "traffic_level": level,
        "signal": {"current": "GREEN", "remaining": 42, "recommended_green": green, "recommended_red": red},
        "accident": {"detected": False, "confidence": 0, "location": CITIES.get(city, CITIES["Riyadh"])["junction"],
                     "time": "--:--", "alerts": False},
        "engine": "DEMO"
    })

@app.post("/api/process-image")
def process_image():
    if "file" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400
    f = request.files["file"]
    city = request.form.get("city", "Riyadh")
    raw = f.read()
    arr = np.frombuffer(raw, np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        return jsonify({"error": "Invalid image"}), 400

    data = detect_frame(frame)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    accident, conf = detect_accident(None, gray, data["detections"])
    pct, level, green, red = density_info(data["total"], city)

    frame = draw_detections(frame, data)
    cv2.putText(frame, f"AI TRAFFIC | {city} | {data['engine']}", (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (50, 240, 180), 2, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        return jsonify({"error": "Encoding failed"}), 500

    payload = {
        "city": city,
        "vehicles": {k: data[k] for k in ["total","cars","buses","trucks","motorcycles"]},
        "density": pct, "traffic_level": level,
        "signal": {"recommended_green": green, "recommended_red": red},
        "accident": {
            "detected": accident, "confidence": conf,
            "location": CITIES[city]["junction"],
            "time": datetime.now().strftime("%I:%M:%S %p"),
            "alerts": accident
        },
        "engine": data["engine"],
        "image": "data:image/jpeg;base64," + __import__("base64").b64encode(encoded).decode()
    }
    return jsonify(payload)

@app.post("/api/process-video")
def process_video():
    if "file" not in request.files:
        return jsonify({"error": "No video uploaded"}), 400
    f = request.files["file"]
    city = request.form.get("city", "Riyadh")
    safe = secure_filename(f.filename or "traffic.mp4")
    path = UPLOADS / f"{int(time.time())}_{safe}"
    f.save(path)
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return jsonify({"error": "Could not open video"}), 400

    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 720)
    out_path = UPLOADS / f"processed_{path.stem}.mp4"
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))

    prev_gray = None
    latest = None
    frames = 0
    accident_seen = False
    peak = 0
    start = time.time()

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        data = detect_frame(frame)
        peak = max(peak, data["total"])
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        accident, conf = detect_accident(prev_gray, gray, data["detections"])
        accident_seen = accident_seen or accident
        prev_gray = gray
        latest = (data, conf)
        frame = draw_detections(frame, data)
        label = f"{city} | Vehicles {data['total']} | {data['engine']}"
        if accident:
            cv2.putText(frame, "ACCIDENT ALERT - DEMO", (20, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (40, 60, 255), 3, cv2.LINE_AA)
        cv2.putText(frame, label, (20, height-20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (50, 240, 180), 2, cv2.LINE_AA)
        writer.write(frame)
        frames += 1

    cap.release()
    writer.release()
    elapsed = max(0.1, time.time() - start)
    if latest is None:
        return jsonify({"error": "No readable frames"}), 400

    data, conf = latest
    pct, level, green, red = density_info(data["total"], city)
    return jsonify({
        "video_url": f"/uploads/{out_path.name}",
        "city": city,
        "vehicles": {k: data[k] for k in ["total","cars","buses","trucks","motorcycles"]},
        "density": pct, "traffic_level": level,
        "signal": {"recommended_green": green, "recommended_red": red},
        "accident": {"detected": accident_seen, "confidence": conf if accident_seen else 0,
                     "location": CITIES[city]["junction"],
                     "time": datetime.now().strftime("%I:%M:%S %p"),
                     "alerts": accident_seen},
        "engine": data["engine"],
        "processed_fps": round(frames / elapsed, 1),
        "peak_vehicles": peak
    })

@app.get("/uploads/<name>")
def uploaded(name):
    return send_file(UPLOADS / secure_filename(name))

@app.get("/api/analytics.csv")
def analytics_csv():
    city = request.args.get("city", "Riyadh")
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["timestamp","city","vehicles","cars","buses","trucks","motorcycles","density","traffic_level"])
    now = datetime.now()
    for i in range(12):
        total = max(8, 25 + ((i * 11) % 30))
        pct, level, _, _ = density_info(total, city)
        writer.writerow([(now).strftime("%Y-%m-%d %H:%M:%S"), city, total,
                         round(total*.72), round(total*.08), round(total*.16), 0, pct, level])
    mem = io.BytesIO(out.getvalue().encode())
    return send_file(mem, mimetype="text/csv", as_attachment=True,
                     download_name=f"{city.replace(' ','_')}_traffic_analytics.csv")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
