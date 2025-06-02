const int escPin = 9;          // ESC가 연결된 핀 번호
const int neutralPulse = 1500; // 중립 (정지) 신호, 1500us
const int forwardPulse = 1700; // 전진 신호, 약 1700us
const int reversePulse = 1300; // 후진 신호, 약 1300us

void setup() {
  pinMode(escPin, OUTPUT);
  
  // ESC 초기화 - 중립 신호로 초기화
  sendPWM(neutralPulse);
  delay(2000);  // ESC 초기화 시간을 위해 2초 대기
}

void loop() {
  // 전진
  sendPWM(forwardPulse);
  delay(2000);  // 2초 동안 전진
  
  // 정지
  sendPWM(neutralPulse);
  delay(2000);  // 2초 동안 정지
  
  // 후진
  sendPWM(reversePulse);
  delay(2000);  // 2초 동안 후진
  
  // 정지
  sendPWM(neutralPulse);
  delay(2000);  // 2초 동안 정지
}

// 펄스 폭을 보내는 함수
void sendPWM(int pulseWidth) {
  digitalWrite(escPin, HIGH);
  delayMicroseconds(pulseWidth);  // 펄스 폭만큼 HIGH 유지
  digitalWrite(escPin, LOW);
  delay(20 - pulseWidth / 1000);  // 20ms 주기 유지
}
