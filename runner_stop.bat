@echo off
title TSE-Assistant Stop Runner

echo.
echo === Stopping Runner Bot ===
echo Attempting to terminate the 'TSE Signal Runner' process...

REM پیدا کردن پنجره با عنوان مشخص و بستن آن
taskkill /f /fi "WINDOWTITLE eq TSE Signal Runner"

if errorlevel 1 (
echo.
echo Warning: No running process found with title 'TSE Signal Runner'.
echo Runner might already be stopped or failed to start.
) else (
echo.
echo Successfully terminated the 'TSE Signal Runner'.
echo Signal monitoring is now stopped.
)

pause