@echo off
setlocal

cd /d "%~dp0"
echo [1/3] Checking Node.js and npm...
where node >nul 2>nul || (echo Node.js is not installed. & exit /b 1)
where npm >nul 2>nul || (echo npm is not installed. & exit /b 1)

echo [2/3] Installing Electron dependencies...
call npm.cmd install
if errorlevel 1 exit /b %errorlevel%

echo [3/3] Building the Windows installer...
call npm.cmd run dist:win
if errorlevel 1 exit /b %errorlevel%

echo.
echo Build complete. Check the desktop\dist folder for the NSIS installer.
pause
endlocal
