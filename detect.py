from flask import Flask, Response, jsonify
from flask_cors import CORS
import cv2
from ultralytics import YOLO
import pytesseract
import re
import threading
import time
import os
import random
import sqlite3
import atexit
import math

# ─── SQLite 연결 및 테이블 생성 ───────────────────────────────────────────────
DB_PATH = "/home/rlaalswns/drone/back/db.sqlite3"
db = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = db.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS myapp_potholedata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    latitude REAL,
    longitude REAL,
    severity INTEGER DEFAULT 3,
    description TEXT,
    region TEXT,
    image TEXT,
    status TEXT DEFAULT 'REPORTED',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
db.commit()

@atexit.register
def close_db():
    cursor.close()
    db.close()
    print("SQLite 연결 종료됨")

# ─── Flask + YOLO + OCR 설정 ───────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

model = YOLO("second.pt")
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"
os.environ["QT_QPA_PLATFORM"] = "xcb"

latest_frame = None
latest_gps = {"latitude": None, "longitude": None}

def preprocess(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 15, 7)
    thresh = cv2.bitwise_not(thresh)
    resized = cv2.resize(thresh, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    return resized

def extract_gps(text):
    match = re.search(r'(\d{2,3}\.\d+)[°]N\s*(\d{3}\.\d+)[°]E', text)
    if match:
        lat, lon = match.groups()
        return float(lat), float(lon)
    return None

def is_duplicate(base_lat, base_lon, threshold=0.0001):
    cursor.execute("""
        SELECT COUNT(*) FROM myapp_potholedata
        WHERE ABS(latitude - ?) < ? AND ABS(longitude - ?) < ?
    """, (base_lat, threshold, base_lon, threshold))
    return cursor.fetchone()[0] > 0

def meters_to_latlon_offset(dy, dx, base_lat):
    dlat = dy / 111320
    dlon = dx / (40075000 * math.cos(math.radians(base_lat)) / 360)
    return dlat, dlon

def calculate_severity(real_w, real_h):
    diameter = max(real_w, real_h)
    if diameter < 0.5:
        return 1  # 낮음
    elif diameter < 2:
        return 2  # 중간
    else:
        return 3  # 높음

def is_valid_gps(lat, lon):
    return 33 <= lat <= 39 and 124 <= lon <= 132

def is_reasonable_gps(new_lat, new_lon, prev_lat, prev_lon, max_diff=0.0009):
    if prev_lat is None or prev_lon is None:
        return True
    return abs(new_lat - prev_lat) < max_diff and abs(new_lon - prev_lon) < max_diff

def yolo_ocr_worker():
    global latest_frame, latest_gps
    cap = cv2.VideoCapture(2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    if not cap.isOpened():
        print(" 카메라 열기 실패!")
        return

    # 카메라 정보 (Mavic 3 Enterprise)
    HFOV = 84
    VFOV = 63
    height = 20  # 드론 고도 (m)
    frame_width = 1920
    frame_height = 1080

    real_width = 2 * height * math.tan(math.radians(HFOV / 2))
    real_height = 2 * height * math.tan(math.radians(VFOV / 2))
    m_per_px_x = real_width / frame_width
    m_per_px_y = real_height / frame_height

    gps_x0, gps_y0 = 272, 272  # OCR 박스 중심 (px), 수동 고정

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        results = model(frame, verbose=False)
        annotated = frame.copy()

        for box in results[0].boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            x, y, w, h = box.xywh[0].tolist()
            cls_id = int(box.cls[0])
            if cls_id not in [0, 1]:
                continue

            real_w = w * m_per_px_x
            real_h = h * m_per_px_y
            severity = calculate_severity(real_w, real_h)

            # 색상 지정
            if severity == 1:
                color = (0, 255, 0)     # 초록 (낮음)
            elif severity == 2:
                color = (0, 165, 255)   # 주황 (중간)
            else:
                color = (0, 0, 255)     # 빨강 (높음)

            # 라벨 (심각도만 표시)
            label = f"Severity {severity}"

            # 바운딩 박스 및 라벨 그리기
            cv2.rectangle(annotated, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
            cv2.putText(annotated, label, (int(x1), int(y1) - 10),
                         cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        latest_frame = annotated

        # 1. OCR로 GPS 시도
        gps_box = frame[255:290, 100:445]
        processed = preprocess(gps_box)
        config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789.NE°'
        text = pytesseract.image_to_string(processed, config=config).strip()
        gps = extract_gps(text)

        if gps:
            lat, lon = gps
            # 유효범위 + 이전값과의 변화폭 체크
            if is_valid_gps(lat, lon) and is_reasonable_gps(lat, lon, latest_gps["latitude"], latest_gps["longitude"]):
                base_lat, base_lon = lat, lon
                latest_gps["latitude"], latest_gps["longitude"] = lat, lon
            else:
                print(" 잘못된/튐 GPS값 무시:", lat, lon)
                time.sleep(0.05)
                continue
        elif latest_gps["latitude"] is not None and latest_gps["longitude"] is not None:
            print("OCR 실패, 이전 GPS 사용")
            base_lat, base_lon = latest_gps["latitude"], latest_gps["longitude"]
        else:
            print("OCR 실패 & 이전 GPS 없음, 저장 스킵")
            time.sleep(0.05)
            continue

        # 2. 현재 프레임의 모든 객체 정보 수집
        timestamp = int(time.time())
        image_path = f"/home/rlaalswns/drone/back/media/frame_{timestamp}.jpg"
        
        frame_objects = []
        for box in results[0].boxes:
            x, y, w, h = box.xywh[0].tolist()
            cls_id = int(box.cls[0])
            if cls_id not in [0,1]:
                continue

            # 각 객체의 실제 GPS 좌표 계산
            dx_px = x - gps_x0
            dy_px = y - gps_y0
            dx_m = dx_px * m_per_px_x
            dy_m = dy_px * m_per_px_y
            dlat, dlon = meters_to_latlon_offset(dy_m, dx_m, base_lat)
            pothole_lat = base_lat   # 수정: offset 적용
            pothole_lon = base_lon   # 수정: offset 적용

            real_w = w * m_per_px_x
            real_h = h * m_per_px_y
            severity = calculate_severity(real_w, real_h)
            
            frame_objects.append({
                'lat': pothole_lat,
                'lon': pothole_lon,
                'severity': severity,
                'description': model.names[cls_id]
            })

        # 3. 기존 DB와만 비교하여 중복 제거 (같은 프레임 내 객체들은 서로 비교하지 않음)
        objects_to_save = []
        for obj in frame_objects:
            if not is_duplicate(obj['lat'], obj['lon']):
                objects_to_save.append(obj)
            else:
                print(f" 중복 생략: {obj['lat']:.6f}, {obj['lon']:.6f}")

        # 4. 저장할 객체가 있으면 이미지 저장 후 모든 객체를 DB에 저장
        if objects_to_save:
            cv2.imwrite(image_path, annotated)
            
            # 트랜잭션으로 모든 객체를 한 번에 저장
            try:
                for obj in objects_to_save:
                    insert_query = """
                        INSERT INTO myapp_potholedata
                        (latitude, longitude, severity, description, region, image, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """
                    values = (obj['lat'], obj['lon'], obj['severity'], obj['description'], 
                             "경기도 안산시", image_path, 'REPORTED')
                    cursor.execute(insert_query, values)
                
                db.commit()  # 모든 객체 저장 후 한 번에 커밋
                
                print(f" 프레임 {timestamp}: {len(objects_to_save)}개 객체 저장됨")
                for obj in objects_to_save:
                    print(f"   - {obj['lat']:.6f}, {obj['lon']:.6f}, 심각도 {obj['severity']}")
                    
            except Exception as err:
                print(f" DB 저장 실패: {err}")
                db.rollback()

        time.sleep(0.05)


@app.route("/video_feed")
def video_feed():
    def generate():
        while True:
            if latest_frame is not None:
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 70]
                _, buffer = cv2.imencode('.jpg', latest_frame, encode_param)
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' +
                       buffer.tobytes() + b'\r\n')
            time.sleep(0.05)
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/gps")
def gps():
    return jsonify(latest_gps)

@app.route("/")
def index():
    return '''
    <html><body>
    <h2>YOLO + OCR 실시간 스트리밍</h2>
    <img src="/video_feed" width="720"><br>
    <a href="/gps" target="_blank">현재 GPS 좌표 보기</a>
    </body></html>
    '''

if __name__ == "__main__":
    thread = threading.Thread(target=yolo_ocr_worker, daemon=True)
    thread.start()
    app.run(host="0.0.0.0", port=5000)