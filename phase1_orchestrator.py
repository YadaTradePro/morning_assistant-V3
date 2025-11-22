# phase1_orchestrator.py
# Phase 1 - TSETMC WebAPI Layer & Real-time Caching (Orchestrator)

import pytse_client as tse
from typing import Dict, Any, List, Optional
import logging
import redis
import json
import os
from dotenv import load_dotenv

# --- Import DB Components ---
# فرض بر این است که db_connector در کنار همین فایل قرار دارد
from db_connector import (
    get_db_session, 
    WeeklyWatchlistResult, 
    GoldenKeyResult, 
    PotentialBuyQueueResult, 
    DynamicSupportOpportunity
)

logger = logging.getLogger(__name__)

# --- تنظیمات Redis ---
load_dotenv()
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REALTIME_CACHE_KEY = "market:realtime:tickers" 

class Phase1Orchestrator:
    """
    این کلاس به عنوان Orchestrator عمل می‌کند و وظایف زیر را انجام می‌دهد:
    1. دریافت لیست نمادها از دیتابیس Backend (چهار جدول اصلی).
    2. دریافت داده‌های کاملاً لحظه‌ای از TSETMC (شامل حقیقی/حقوقی لحظه‌ای).
    3. ذخیره داده‌های یکپارچه‌شده در Redis برای مصرف فازهای بعدی.
    """

    def __init__(self):
        # 1. اتصال به Redis
        try:
            self.redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_timeout=5)
            self.redis_client.ping()
            logger.info(f"📡 Redis connection successful: {REDIS_HOST}:{REDIS_PORT}")
        except redis.exceptions.ConnectionError as e:
            logger.error(f"❌ Could not connect to Redis: {e}. Caching feature will be disabled.")
            self.redis_client = None

    # ---------------------------------------------------------
    # 0) واکشی لیست نمادها از دیتابیس (Database Fetcher)
    # ---------------------------------------------------------
    def get_unique_symbols_from_db(self) -> List[str]:
        """
        این متد نام نمادها (مثلاً 'مانی'، 'فولاد') را از دیتابیس می‌گیرد.
        چون pytse-client با نام نماد کار می‌کند، نه با کد عددی (TSETMC ID).
        """
        session = get_db_session()
        unique_names = set() # استفاده از Set برای حذف تکراری‌ها
        
        try:
            logger.info("🗄️ Querying database for watchlist symbol NAMES...")
            

            weekly = session.query(WeeklyWatchlistResult.symbol_name).all()
            for r in weekly: 
                if r.symbol_name: unique_names.add(r.symbol_name)
            

            # اعمال فیلتر: GoldenKeyResult.score > 24
            golden = (
                session.query(GoldenKeyResult.symbol_name)
                .filter(GoldenKeyResult.score > 24)
                .all()
            )

            for r in golden: 
                # توجه: اگر symbol_name تنها فیلد در کوئری باشد، r یک تاپل یا یک شیء تک‌عضوی است.
                # برای دسترسی به مقدار آن، بهتر است از r[0] یا r.symbol_name استفاده کنید.
                # r.symbol_name در حالت .all() درست است اگر یک شیء result برگردانده شود.
                if r.symbol_name:
                    unique_names.add(r.symbol_name)
            
            # 3. Potential Buy Queue
            buy_queue = session.query(PotentialBuyQueueResult.symbol_name).all()
            for r in buy_queue: 
                if r.symbol_name: unique_names.add(r.symbol_name)
            
            # 4. Dynamic Support
            dynamic = session.query(DynamicSupportOpportunity.symbol_name).all()
            for r in dynamic: 
                if r.symbol_name: unique_names.add(r.symbol_name)
            
            logger.info(f"✅ Found {len(unique_names)} unique symbol names (e.g., 'مانی') to monitor.")
            return list(unique_names)
            
        except AttributeError as e:
            logger.error(f"❌ Database Schema Error: One of your tables assumes 'symbol_name' exists but it might be missing. Details: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Database Query Error: {e}")
            return []
        finally:
            session.close()

    # ---------------------------------------------------------
    # تابع کمکی جدید: دریافت مطمئن داده‌های حقیقی/حقوقی
    # ---------------------------------------------------------
    def _safe_get_trade_summary(self, rt_data, summary_type: str) -> Dict[str, Any]:
        """
        💡 اصلاح شده: اطمینان حاصل می‌کند که مقادیر همیشه float یا int هستند تا خطای NoneType در عملیات ریاضی رخ ندهد.
        """
        attr_name = f'{summary_type}_trade_summary'
        summary = getattr(rt_data, attr_name, None)
    
        # مقادیر پیش‌فرض را به صورت Dictionary آماده می‌کنیم
        default_values = {
            f'{summary_type}_buy_vol': 0.0,
            f'{summary_type}_buy_count': 0,
            f'{summary_type}_sell_vol': 0.0,
            f'{summary_type}_sell_count': 0,
        }
    
        # بررسی می‌کنیم که summary وجود داشته باشد و attributeهای لازم را داشته باشد.
        if summary and hasattr(summary, 'buy_vol') and hasattr(summary, 'sell_vol'):
            # ❗ تبدیل صریح به float و int برای اطمینان از نوع داده
            # از float() و int() استفاده می‌کنیم تا هر مقدار غیر عددی (مثل None) که با or 0.0 به صفر تبدیل شده، 
            # به نوع درستی تبدیل شود.
            buy_vol = float(summary.buy_vol or 0.0)
            buy_count = int(summary.buy_count or 0)
            sell_vol = float(summary.sell_vol or 0.0)
            sell_count = int(summary.sell_count or 0)
        
            return {
                f'{summary_type}_buy_vol': buy_vol, 
                f'{summary_type}_buy_count': buy_count,
                f'{summary_type}_sell_vol': sell_vol,
                f'{summary_type}_sell_count': sell_count,
            }
        else:
            # در صورت عدم وجود آبجکت summary، مقادیر پیش‌فرض را برمی‌گرداند.
            return default_values

    # ---------------------------------------------------------
    # 1) یکپارچه‌سازی داده‌های لحظه‌ای (Live Data Mapper)
    # ---------------------------------------------------------
    def _map_live_data(self, ticker: tse.Ticker) -> Optional[Dict[str, Any]]:
        """
        داده‌های لحظه‌ای را با استفاده از متد get_ticker_real_time_info_response استخراج می‌کند 
        و مقادیر Null را ایمن‌سازی می‌کند.
        """
        try:
            # طبق مستندات: دریافت آبجکت لحظه‌ای
            rt_data = ticker.get_ticker_real_time_info_response()
            
            # بررسی وضعیت مجاز/ممنوع (State)
            # معمولاً state یه استرینگ است. اگر نیاز به فیلتر وضعیت دارید اینجا اضافه کنید.
            
            result = {
                'symbol': ticker.symbol,  # نام نماد (مثل فولاد)
                'symbol_name': ticker.title, # نام کامل شرکت
                
                # --- قیمت‌ها و حجم‌های اصلی: با استفاده از 'or 0.0' ایمن‌سازی می‌شوند ---
                'last_price': rt_data.last_price or 0.0,      # قیمت آخرین معامله
                'adj_close': rt_data.adj_close or 0.0,        # قیمت پایانی
                'open_price': rt_data.open_price or 0.0,
                'yesterday_price': rt_data.yesterday_price or 0.0,
                'high_price': rt_data.high_price or 0.0,
                'low_price': rt_data.low_price or 0.0,
                'volume': rt_data.volume or 0,               # حجم معاملات لحظه‌ای
                'value': rt_data.value or 0.0,                 # ارزش معاملات
                'base_volume': ticker.base_volume or 0,      # حجم مبنا از آبجکت اصلی ticker گرفته می‌شود
                'count': rt_data.count or 0,                 # تعداد معاملات
                
                # --- اطلاعات تابلوخوانی (بهترین عرضه و تقاضا) ---
                'best_demand_price': rt_data.best_demand_price or 0.0, # قیمت بهترین خرید (سرخط)
                'best_demand_vol': rt_data.best_demand_vol or 0,       # حجم بهترین خرید
                'best_supply_price': rt_data.best_supply_price or 0.0, # قیمت بهترین فروش
                'best_supply_vol': rt_data.best_supply_vol or 0,       # حجم بهترین فروش
                
                # --- حقیقی / حقوقی (با استفاده از تابع کمکی ایمن) ---
                # طبق مستندات، این آبجکت‌ها داخل individual_trade_summary و corporate_trade_summary هستند
            }
            
            # نگاشت داده‌های حقیقی (Individual)
            result.update(self._safe_get_trade_summary(rt_data, 'individual'))

            # نگاشت داده‌های حقوقی (Corporate)
            result.update(self._safe_get_trade_summary(rt_data, 'corporate'))

            # محاسبه قدرت خریدار حقیقی (Optional - محاسبه در لحظه)
            # اگر بخواهید همینجا محاسبه کنید:
            # buy_power = (ind_buy_vol / ind_buy_count) if ind_buy_count > 0 else 0
            
            return result

        except RuntimeError:
            # این ارور طبق مستندات یعنی دیتای لحظه‌ای موجود نیست (نماد بسته یا قدیمی)
            logger.warning(f"⚠️ Real-time data not available for {ticker.symbol} (Stopped or Old).")
            return None
        except Exception as e:
            # خطای 'unsupported operand type(s) for *: 'NoneType' and 'float'' دیگر نباید اینجا رخ دهد، 
            # بلکه در مراحل بعدی تحلیل (فاز 2) که از این داده‌ها استفاده می‌کند، رخ می‌دهد.
            logger.error(f"❌ Error mapping data for {ticker.symbol}: {e}")
            return None

    # ---------------------------------------------------------
    # 2) واکشی و ذخیره داده‌های لحظه‌ای (Main Loop)
    # ---------------------------------------------------------
    def fetch_and_cache_all_realtime(self):
        """
        متد اصلی که توسط Task Scheduler یا Loop فراخوانی می‌شود.
        1. لیست نمادها را از DB می‌گیرد.
        2. دیتای TSETMC را می‌گیرد.
        3. در Redis کش می‌کند.
        """
        if not self.redis_client:
            logger.error("❌ Caching failed: Redis client not initialized.")
            return

        # الف) دریافت لیست نمادها از دیتابیس
        symbol_list = self.get_unique_symbols_from_db()
        
        if not symbol_list:
            logger.warning("⚠️ Watchlist is empty. No symbols to fetch.")
            return

        all_tickers_data = []
        logger.info(f"📡 Starting real-time fetch for {len(symbol_list)} symbols...")

        # ب) دریافت دیتای لحظه‌ای
        for symbol in symbol_list:
            try:
                # ساخت آبجکت Ticker
                ticker = tse.Ticker(symbol)
                
                # واکشی دیتای مپ شده
                live_mapped_data = self._map_live_data(ticker)
                
                if live_mapped_data:
                    all_tickers_data.append(live_mapped_data)

            except Exception as e:
                logger.error(f"❌ Unexpected error processing {symbol}: {e}")
                continue

        # ج) ذخیره در Redis
        if all_tickers_data:
            try:
                # ذخیره با فرمت JSON
                self.redis_client.set(REALTIME_CACHE_KEY, json.dumps(all_tickers_data))
                # می‌توانیم Expiration هم بگذاریم که دیتا بیات نشود (مثلا 2 دقیقه)
                self.redis_client.expire(REALTIME_CACHE_KEY, 120) 
                
                logger.info(f"✅ Successfully cached real-time data for {len(all_tickers_data)} symbols in Redis.")
            except Exception as e:
                logger.error(f"❌ Failed to write data to Redis: {e}")
        else:
            logger.warning("⚠️ No valid live data was collected to cache.")

# --- (بخش تست دستی) ---
if __name__ == "__main__":
    # تنظیم لاگ برای مشاهده خروجی
    logging.basicConfig(level=logging.INFO)
    
    orchestrator = Phase1Orchestrator()
    orchestrator.fetch_and_cache_all_realtime()