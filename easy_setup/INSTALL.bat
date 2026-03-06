@echo off
title GBPJPY EMA + Supertrend Auto Trading - Easy Installer
color 0A
echo.
echo ============================================================
echo   GBPJPY EMA + Supertrend - Auto Trading Setup
echo ============================================================
echo.
echo This will set up the TradingView to MT4 bridge on your PC.
echo.
pause

echo.
echo [Step 1/4] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo Python is NOT installed on your PC.
    echo.
    echo Please download and install Python from:
    echo https://www.python.org/downloads/
    echo.
    echo IMPORTANT: During installation, CHECK the box that says
    echo "Add Python to PATH" at the bottom of the installer!
    echo.
    echo After installing Python, run this installer again.
    pause
    exit /b
)
echo Python found!
python --version

echo.
echo [Step 2/4] Creating signals folder...
mkdir "%~dp0signals" 2>nul
echo Signals folder ready!

echo.
echo [Step 3/4] Finding MT4 installation...
set MT4_FOUND=0
set EA_DEST=

rem Check common XM MT4 locations
for /d %%i in ("%APPDATA%\MetaQuotes\Terminal\*") do (
    if exist "%%i\MQL4\Experts" (
        set MT4_FOUND=1
        set EA_DEST=%%i\MQL4\Experts
    )
)

if %MT4_FOUND%==1 (
    echo MT4 found! Copying EA file...
    copy "%~dp0EMA_Supertrend_Bridge.mq4" "%EA_DEST%\" /Y
    echo EA copied to: %EA_DEST%
    echo.
    echo IMPORTANT: Restart MT4 for the EA to appear!
) else (
    echo.
    echo MT4 data folder not found automatically.
    echo You need to manually copy the EA file:
    echo.
    echo 1. Open MT4
    echo 2. Click File -^> Open Data Folder
    echo 3. Go to MQL4 -^> Experts
    echo 4. Copy "EMA_Supertrend_Bridge.mq4" into that folder
    echo 5. Restart MT4
)

echo.
echo [Step 4/4] Setup complete!
echo.
echo ============================================================
echo   WHAT TO DO NEXT:
echo ============================================================
echo.
echo 1. RESTART MT4 if it's open
echo.
echo 2. In MT4: Attach "EMA_Supertrend_Bridge" EA to GBPJPY chart
echo    - Make sure AutoTrading button is GREEN (enabled)
echo    - In EA settings, allow DLL imports
echo.
echo 3. Run START_BRIDGE.bat to start the webhook bridge
echo.
echo 4. In TradingView: Add the Pine Script and create an alert
echo    with webhook URL (see QUICK_GUIDE.txt for details)
echo.
echo ============================================================
echo.
pause
