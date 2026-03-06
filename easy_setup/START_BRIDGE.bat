@echo off
title TradingView-MT4 Bridge Server (DO NOT CLOSE THIS WINDOW)
color 0B
echo.
echo ============================================================
echo   TradingView to MT4 Bridge Server
echo ============================================================
echo.
echo This window MUST stay open while you are trading!
echo Closing this window will stop the auto-trading.
echo.
echo ============================================================
echo.
echo Starting bridge server on port 5000...
echo.

cd /d "%~dp0"
python server.py --signals-dir "%APPDATA%\MetaQuotes\Terminal" 2>nul

rem If the above fails (MT4 path not found), use local signals folder
if %errorlevel% neq 0 (
    echo.
    echo Using local signals folder...
    python server.py --signals-dir "%~dp0signals"
)

pause
