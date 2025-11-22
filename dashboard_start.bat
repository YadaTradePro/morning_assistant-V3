@echo off
title TSE-Assistant Dashboard (Streamlit)

REM --- تنظیمات ---
SET PROJECT_DIR=E:\BourseAnalysis\V-3\morning_assistant
REM 💡 تغییر مسیر VENV از venv به venv-dashboard
SET VENV_ACTIVATE=%PROJECT_DIR%\venv-dashboard\Scripts\activate.bat
SET DASHBOARD_SCRIPT=dashboard.py
REM ----------------

echo.
echo === شروع ربات داشبورد Streamlit ===
echo مسیر پروژه: %PROJECT_DIR%
echo فعال سازی محیط مجازی داشبورد...

call "%VENV_ACTIVATE%"

if exist "%DASHBOARD_SCRIPT%" (
echo در حال اجرای Streamlit...

REM 'start' این دستور را در یک پنجره جدید اجرا می کند.
start "TSE Dashboard" cmd /k streamlit run %DASHBOARD_SCRIPT%

echo.
echo Streamlit در حال اجرا در مرورگر است.
echo برای توقف، پنجره ترمینال جدید را ببندید.

) else (
echo خطا: اسکریپت داشبورد "%DASHBOARD_SCRIPT%" یافت نشد.
)

pause