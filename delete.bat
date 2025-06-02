@echo off
echo SOLIDWORKS 흔적 자동 제거 스크립트 시작
echo 관리자 권한 확인...

:: 관리자 권한 확인
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo 관리자 권한으로 실행해 주세요.
    pause
    exit /b
)

:: 서비스 삭제
echo FLEXnet 서비스 제거 중...
sc delete "SolidWorks Flexnet Server"

:: 폴더 삭제
echo 프로그램 폴더 삭제 중...
rd /s /q "C:\Program Files\SOLIDWORKS"
rd /s /q "C:\ProgramData\SOLIDWORKS"
rd /s /q "C:\Program Files\Common Files\SOLIDWORKS Shared"

:: 레지스트리 삭제
echo 레지스트리 삭제 중...
reg delete "HKLM\SOFTWARE\SolidWorks" /f
reg delete "HKCU\Software\SolidWorks" /f

:: 완료 메시지
echo ----------------------------------------
echo SOLIDWORKS 흔적 제거 완료
echo 재부팅 후 설치를 다시 진행하세요.
echo ----------------------------------------
pause
