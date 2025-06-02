import torch
import torch.nn as nn
import numpy as np
import serial

# 🔹 시리얼 포트 설정
SERIAL_PORT = "COM11"  # 사용 중인 포트로 변경하세요
BAUD_RATE = 9600

# 🔹 클래스 라벨 정의
class_labels = {0: "펀치", 1: "노말", 2: "쓰다듬기", 3: "꼬집기"}

# 🔹 저장된 LSTM 모델 불러오기
class PunchDetectionLSTM(nn.Module):
    def __init__(self, num_classes=4):
        super(PunchDetectionLSTM, self).__init__()
        self.lstm = nn.LSTM(input_size=2, hidden_size=64, num_layers=2, batch_first=True)
        self.fc1 = nn.Linear(64, 32)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(32, num_classes)
    
    def forward(self, x):
        lstm_out, _ = self.lstm(x)
        x = self.fc1(lstm_out[:, -1, :])  # 마지막 타임스텝 사용
        x = self.relu(x)
        x = self.fc2(x)
        return x

# 🔹 모델 초기화 및 가중치 로드
model = PunchDetectionLSTM()
model.load_state_dict(torch.load("please.pth"))
model.eval()  # 평가 모드

def process_lstm_model(values):
    """
    LSTM 모델을 사용하여 실시간 데이터 분류
    """
    # 평균값 계산 후 feature 추가
    avg = np.mean(values)
    new_data = np.array(values).reshape(1, 13, 1)  # (1, 13, 1)
    avg_feature = np.full((1, 13, 1), avg)  # 평균값을 모든 타임스텝에 추가 (1, 13, 1)

    # 🔹 입력 데이터 변환 (샘플 1개, 타임스텝 13, Feature 2개)
    input_data = np.concatenate([new_data, avg_feature], axis=-1)  # (1, 13, 2)
    input_tensor = torch.tensor(input_data, dtype=torch.float32)

    # 🔹 모델 예측
    with torch.no_grad():
        outputs = model(input_tensor)
        predicted_class = torch.argmax(outputs, dim=1).item()

    print(f"예측 결과: {class_labels[predicted_class]}\n")

# 🔹 시리얼 데이터 수신
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    print(f"시리얼 포트 {SERIAL_PORT} 연결됨!")

    while True:
        line = ser.readline().decode('utf-8').strip().rstrip(",")  # 시리얼 데이터 읽기

        if line:
            try:
                values = [float(x) for x in line.split(',')]  # 숫자로 변환

                if len(values) == 13:
                    process_lstm_model(values)  # LSTM 모델로 예측 수행
                else:
                    print(f"데이터 길이 오류 (13개 필요, 현재: {len(values)}) → {values}")

            except ValueError:
                print(f"변환 오류: {line}")

except serial.SerialException as e:
    print(f"시리얼 포트 연결 실패: {e}")
except KeyboardInterrupt:
    print("프로그램 종료")
finally:
    if 'ser' in locals() and ser.is_open:
        ser.close()
        print(f"시리얼 포트 {SERIAL_PORT} 닫힘")