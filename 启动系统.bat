@echo off
REM NOTE: keep this file ASCII-only. The project path contains Chinese
REM characters; UTF-8 batch files are mis-parsed by cmd.exe (GBK console),
REM which breaks "cd /d" and reports "is not recognized as a command".
setlocal

set "ROOT=%~dp0"
set "REDIS_DIR=%ROOT%_redis\Redis-7.4.1-Windows-x64-msys2"
set "APP_DIR=%ROOT%express_station"

title Campus Express Station - Launcher

if not exist "%REDIS_DIR%\redis-server.exe" (
    echo [ERROR] redis-server.exe not found: %REDIS_DIR%
    pause
    exit /b 1
)

echo ============================================
echo   Campus Express Station (Redis + Flask)
echo ============================================
echo.

echo [1/3] Starting Redis on port 6379 ...
start "" /min /D "%REDIS_DIR%" "%REDIS_DIR%\redis-server.exe" --port 6379
timeout /t 2 >nul

echo [2/3] Checking Redis connection ...
"%REDIS_DIR%\redis-cli.exe" ping
echo.

echo [3/3] Starting Flask API on port 5000 ...
start "" /D "%APP_DIR%" cmd /k python app.py
timeout /t 3 >nul

echo.
echo Done.
echo   Redis : 127.0.0.1:6379
echo   API   : http://127.0.0.1:5000
echo.
echo Next steps:
echo   1. WeChat DevTools - import the "miniprogram" folder
echo   2. Details - Local Settings - check "do not verify legal domain"
echo   3. Optional demo data: cd express_station ^&^& python seed_demo.py
echo.
pause
