@echo off
REM NOTE: keep this file ASCII-only. The project path contains Chinese
REM characters; UTF-8 batch files are mis-parsed by cmd.exe (GBK console),
REM which breaks "cd /d" and reports "is not recognized as a command".
setlocal

set "ROOT=%~dp0"
set "REDIS_DIR=%ROOT%_redis\Redis-7.4.1-Windows-x64-msys2"
set "APP_DIR=%ROOT%express_station"

title Redis CLI

if not exist "%REDIS_DIR%\redis-cli.exe" (
    echo [ERROR] redis-cli.exe not found:
    echo         %REDIS_DIR%
    pause
    exit /b 1
)

echo ============================================
echo   Redis CLI  (raw mode, UTF-8 friendly)
echo   Try:  HGETALL parcel:P000001
echo   Exit: type  exit
echo ============================================
echo.

cd /d "%REDIS_DIR%"
redis-cli.exe --raw
pause
