@echo off
title TSE-Assistant Trinity Runner (Writer + Server + Scheduler)

REM --- تنظیمات مسیر ---
SET PROJECT_DIR=E:\BourseAnalysis\V-3\morning_assistant
SET VENV_ACTIVATE=%PROJECT_DIR%\venv\Scripts\activate.bat

REM نام اسکریپت ها
SET WRITER_SCRIPT=realtime_writer.py
SET SERVER_SCRIPT=main.py
SET SCHEDULER_SCRIPT=assistant_scheduler.py

echo.
echo =========================================================
echo === Starting Trinity Runner (Realtime + Flask + Cron) ===
echo =========================================================
echo.

REM 1. فعال‌سازی محیط مجازی
call "%VENV_ACTIVATE%"

REM 2. اجرای دیتای لحظه‌ای (Writer)
if exist "%WRITER_SCRIPT%" (
    echo [1/3] Launching Realtime Writer...
    start "1- DATA WRITER (Redis)" cmd /k python "%WRITER_SCRIPT%"
) else (
    echo ERROR: Writer script not found.
)

REM 3. اجرای سرور Flask (Server)
if exist "%SERVER_SCRIPT%" (
    echo [2/3] Launching Flask Server...
    start "2- FLASK SERVER (Brain)" cmd /k python "%SERVER_SCRIPT%"
) else (
    echo ERROR: Server script not found.
)

REM *************************************************************
REM 💡 اصلاح زمان تاخیر: افزایش زمان انتظار برای پر شدن دیتای Redis توسط Writer
timeout /t 218 > NUL
REM *************************************************************

REM 4. اجرای زمان‌بندی (Scheduler)
if exist "%SCHEDULER_SCRIPT%" (
    echo [3/3] Launching Scheduler...
    start "3- SCHEDULER (Trigger)" cmd /k python "%SCHEDULER_SCRIPT%"
) else (
    echo ERROR: Scheduler script not found.
)

echo.
echo ===================================================
echo ** All systems are GO. **
echo 1. Writer updates Redis.
echo 2. Server waits for requests.
echo 3. Scheduler sends requests every minute.
echo ===================================================
timeout /t 5 > NUL

exit
