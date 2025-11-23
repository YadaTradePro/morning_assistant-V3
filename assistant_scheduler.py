# assistant_scheduler.py
# وظیفه: ارسال درخواست به سرور Flask برای اجرای تحلیل (Trigger)

import time
import logging
import requests # 💡 استفاده از ریکوئست به جای ایمپورت مستقیم
from datetime import datetime
from zoneinfo import ZoneInfo

# --- تنظیمات ---
TEHRAN_TZ = ZoneInfo("Asia/Tehran")
SERVER_URL = "http://localhost:5000/run"  # آدرس سرور Flask
POLL_INTERVAL_SECONDS = 220 # هر 220 ثانیه یکبار تحلیل کن
MARKET_START_HOUR = 9
MARKET_END_HOUR = 16

# --- تنظیمات لاگ ---
logger = logging.getLogger("SchedulerClient")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def is_market_time():
    now = datetime.now(TEHRAN_TZ)
    if now.weekday() in [3, 4]: return False # پنجشنبه/جمعه
    current_hour = now.hour
    # بازه تقریبی ۹ تا ۱۳:۳۰
    return MARKET_START_HOUR <= current_hour <= MARKET_END_HOUR

def run_scheduler_client():
    logger.info(f"📡 Scheduler started. Targeting: {SERVER_URL}")
    
    # یک مکث اولیه برای اینکه مطمئن شویم سرور Flask بالا آمده است
    time.sleep(5)

    while True:
        try:
            if is_market_time():
                logger.info("⏰ Triggering analysis...")
                
                # ارسال درخواست به main.py
                response = requests.get(SERVER_URL, timeout=60)
                
                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status")
                    alerts = data.get("alerts_generated", 0)
                    logger.info(f"✅ Success: {status} | Alerts Sent: {alerts}")
                else:
                    logger.warning(f"⚠️ Server Error: {response.status_code}")
                
                time.sleep(POLL_INTERVAL_SECONDS)
            else:
                logger.info("💤 Market closed. Waiting...")
                time.sleep(300) # در زمان بسته بودن بازار، هر ۵ دقیقه چک کن

        except requests.exceptions.ConnectionError:
            logger.error("❌ Connection Failed. Is main.py (Flask) running?")
            time.sleep(10)
        except KeyboardInterrupt:
            logger.info("🛑 Scheduler stopped.")
            break
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_scheduler_client()
