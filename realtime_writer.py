# realtime_writer.py
# وظیفه: اجرای مداوم Orchestrator برای به‌روزرسانی Cache (Redis)
# این فایل فقط مسئول زمان‌بندی است و منطق دیتابیس را به Orchestrator می‌سپارد.

import time
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from phase1_orchestrator import Phase1Orchestrator

# --- تنظیمات ---
TEHRAN_TZ = ZoneInfo("Asia/Tehran")
POLL_INTERVAL_SECONDS = 5      # فاصله بین هر بار واکشی (ثانیه)
MARKET_START_HOUR = 8          # معمولاً بازار از ۸:۴۵ سفارش‌گیری دارد، از ۸ شروع کنیم بهتر است
MARKET_START_MINUTE = 55
MARKET_END_HOUR = 16
MARKET_END_MINUTE = 0         # کمی بعد از ۱۲:۳۰ برای اطمینان از دریافت قیمت‌های پایانی

# --- تنظیمات لاگ ---
logger = logging.getLogger(__name__)
# فرمت لاگ را تمیز می‌کنیم
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout) # چاپ در کنسول
    ]
)

# =========================================================
# منطق زمان‌بندی
# =========================================================

def is_market_time() -> bool:
    """
    بررسی می‌کند که آیا ساعت و روز فعلی در محدوده معاملات بورس تهران قرار دارد یا خیر.
    """
    now = datetime.now(TEHRAN_TZ)
    
    # روزهای پنجشنبه (3) و جمعه (4) تعطیل است
    if now.weekday() in [3, 4]: 
        return False
        
    # تبدیل زمان شروع و پایان به آبجکت time برای مقایسه
    current_time = now.time()
    start_time = now.replace(hour=MARKET_START_HOUR, minute=MARKET_START_MINUTE, second=0, microsecond=0).time()
    end_time = now.replace(hour=MARKET_END_HOUR, minute=MARKET_END_MINUTE, second=0, microsecond=0).time()
    
    return start_time <= current_time <= end_time

def run_orchestrator_writer():
    """
    حلقه اصلی: اجرای متد fetch_and_cache_all_realtime از کلاس ارکستریتور.
    """
    logger.info("🛠️ Initializing Phase 1 Orchestrator Service...")
    
    # ایجاد نمونه از کلاس اصلی (اتصال به ردیس اینجا برقرار می‌شود)
    orchestrator = Phase1Orchestrator()
    
    logger.info("🟢 Service Started. Waiting for market hours or checking immediate tasks...")

    while True:
        try:
            now = datetime.now(TEHRAN_TZ)
            
            # بررسی زمان بازار
            if is_market_time():
                logger.info(f"⚡ Market Open ({now.strftime('%H:%M:%S')}). Syncing data...")
                
                # --- فراخوانی اصلی ---
                # نکته مهم: اینجا هیچ لیست نمادی پاس نمی‌دهیم.
                # خودِ ارکستریتور می‌رود و لیست را از دیتابیس (فیلدهای symbol_name) می‌خواند.
                orchestrator.fetch_and_cache_all_realtime()
                
                # خواب کوتاه بین هر آپدیت
                time.sleep(POLL_INTERVAL_SECONDS)
                
            else:
                # خارج از ساعت بازار
                logger.debug(f"💤 Market Closed ({now.strftime('%H:%M:%S')}). Sleeping for 60s...")
                time.sleep(60) 
                
        except KeyboardInterrupt:
            logger.info("🛑 Service stopped by user (KeyboardInterrupt).")
            break
            
        except Exception as e:
            # اگر خطایی رخ داد (مثلاً قطعی اینترنت)، برنامه نباید بسته شود
            logger.error(f"❌ Unexpected Crash in Main Loop: {e}")
            logger.info("🔄 Restarting loop in 10 seconds...")
            time.sleep(10)

if __name__ == "__main__":
    run_orchestrator_writer()
