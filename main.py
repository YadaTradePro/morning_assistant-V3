# main.py
# سرور اصلی Flask برای اجرای تحلیل‌های فاز ۲ و ارسال سیگنال

from flask import Flask, jsonify
import requests
from datetime import datetime
from sqlalchemy import text
from db_connector import get_db_session
from analysis_engine import analyze_symbol_combined, escape_markdown
from notifier import TelegramNotifier
import os
import logging
import json
import redis
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
from typing import Dict, Any, Optional

# --- تنظیمات اولیه ---
load_dotenv()

# راه‌اندازی Flask
app = Flask(__name__)

# تنظیمات لاگ
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

notifier = TelegramNotifier()
TEHRAN_TZ = ZoneInfo("Asia/Tehran")

# تنظیمات Redis (مشابه Orchestrator)
REALTIME_CACHE_KEY = "market:realtime:tickers" 
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# ==========================
# توابع کمکی (Helper Functions)
# ==========================

def fetch_potential_symbols_with_phase1_data(db_session) -> Dict[str, Any]:
    """
    واکشی نمادهای منتخب از جداول فاز ۱ (GoldenKey, Watchlist, BuyQueue)
    به همراه داده‌های تکنیکال ذخیره شده.
    """
    # کوئری اصلاح شده برای سازگاری با ستون‌های db_connector.py (مخصوصاً jentry_date)
    query = text("""
        WITH LatestTech AS (
            SELECT *, ROW_NUMBER() OVER(PARTITION BY symbol_id ORDER BY jdate DESC) as rn
            FROM technical_indicator_data
        ),
        LatestCandle AS (
            SELECT *, ROW_NUMBER() OVER(PARTITION BY symbol_id ORDER BY jdate DESC) as rn
            FROM candlestick_pattern_detection
        ),
        AllCandidates AS (
            SELECT symbol_id, score AS golden_key_score, jdate, 'GoldenKey' AS source_table FROM golden_key_results WHERE score > 26
            UNION
            SELECT symbol_id, probability_percent AS golden_key_score, jdate, 'BuyQueue' AS source_table FROM potential_buy_queue_results WHERE probability_percent > 50
            UNION
            SELECT symbol_id, 100 as golden_key_score, jentry_date AS jdate, 'Watchlist' AS source_table FROM weekly_watchlist_results
            UNION
            SELECT symbol_id, 100 as golden_key_score, analysis_date As jdate, 'DynamicSupport' AS source_table FROM dynamic_support_opportunities
        )
        SELECT DISTINCT
            ac.symbol_id,
            csd.symbol_name,
            ac.golden_key_score,
            ac.source_table,
            tech.RSI,
            tech.halftrend_signal,
            candle.pattern_name
        FROM AllCandidates ac
        INNER JOIN comprehensive_symbol_data csd ON ac.symbol_id = csd.symbol_id
        LEFT JOIN LatestTech tech ON ac.symbol_id = tech.symbol_id AND tech.rn = 1
        LEFT JOIN LatestCandle candle ON ac.symbol_id = candle.symbol_id AND candle.rn = 1
        ORDER BY ac.golden_key_score DESC
        LIMIT 100;
    """)
    
    try:
        result = db_session.execute(query)
        # خروجی: دیکشنری با کلید symbol_id
        symbols_data = {row.symbol_id: dict(row._mapping) for row in result}
        logger.info(f"✅ Found {len(symbols_data)} potential symbols from DB.")
        return symbols_data
    except Exception as e:
        logger.error(f"❌ SQL Query Failed: {e}")
        return {}

def fetch_live_market_data_from_cache() -> Optional[Dict[str, Dict[str, Any]]]:
    """
    داده‌های لحظه‌ای را از Redis می‌خواند.
    خروجی: دیکشنری که کلید آن 'نام نماد' (فارسی) است.
    """
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_timeout=2)
        raw_data = r.get(REALTIME_CACHE_KEY)
        
        if not raw_data:
            logger.warning("⚠️ Redis cache is empty. Is the Orchestrator running?")
            return None
        
        data_list = json.loads(raw_data)
        # تبدیل لیست به دیکشنری با کلید نام نماد (مثلاً 'فولاد')
        return {item['symbol']: item for item in data_list if item.get('symbol')}
        
    except Exception as e:
        logger.error(f"❌ Redis Error: {e}")
        return None

# ==========================
# تابع ذخیره لاگ (اصلاح‌شده برای داشبورد)
# ==========================

def save_json_log(alerts):
    """
    💡 اصلاح شده: ذخیره لاگ با نام روز جاری، حتی اگر alerts خالی باشد، 
    تا Dashboard مطمئن باشد که فرآیند تحلیل امروز اجرا شده است.
    """
    # ❗ این شرط حذف می‌شود: if not alerts: return 
    
    now = datetime.now(TEHRAN_TZ)
    # 1. نام فایل: phase2_alerts_YYYYMMDD_HHMM.json
    # اگر در یک دقیقه چندین بار اجرا شود، فایل قبلی بازنویسی می‌شود که مشکلی نیست.
    filename = os.path.join(LOG_DIR, f"phase2_alerts_{now.strftime('%Y%m%d_%H%M')}.json")
    
    # 2. ساختار: { 'timestamp': '...', 'alerts': [...] }
    log_data = {
        "timestamp": now.strftime('%Y-%m-%d %H:%M:%S'),
        "alerts_count": len(alerts),
        "alerts": alerts 
    }
    
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
        logger.info(f"📝 Dashboard Log Saved ({len(alerts)} alerts): {filename}")
    except Exception as e:
        logger.error(f"❌ Failed to save log: {e}")


# ==========================
# منطق اصلی تحلیل (Core Logic)
# ==========================

def process_market_analysis():
    """
    منطق اصلی: ترکیب دیتابیس و ردیس، تحلیل و ارسال پیام.
    """
    now = datetime.now(TEHRAN_TZ)
    logger.info("🔄 Starting Analysis Cycle...")
    
    db_session = get_db_session()
    alerts_sent = 0
    
    try:
        # 1. واکشی دیتا از DB
        potential_symbols = fetch_potential_symbols_with_phase1_data(db_session)
        if not potential_symbols:
            return {"status": "skipped", "message": "No symbols in watchlist DB"}

        # 2. واکشی دیتا از Redis
        live_data = fetch_live_market_data_from_cache()
        if not live_data:
            return {"status": "error", "message": "No live data in Redis"}

        strong_buy_alerts = []

        # 3. حلقه تحلیل
        for p1_id, p1_data in potential_symbols.items():
            sym_name = p1_data.get('symbol_name')
            
            if sym_name and sym_name in live_data:
                live_ticker = live_data[sym_name]
                analysis_result = analyze_symbol_combined(live_ticker, p1_data)
                
                if analysis_result.get("is_strong_buy"):
                    strong_buy_alerts.append(analysis_result)
            else:
                continue

        # 4. ارسال نتایج به تلگرام
        if strong_buy_alerts:
            message_lines = [f"🚨 **Strong Buy Signals Detected** ({now.strftime('%H:%M')})\n"]
            
            for alert in strong_buy_alerts:
                # ❗ توجه: آدرس‌دهی مستقیم به کلیدهای فلت شده (مثل power_ratio و target)
                # از آنجایی که analysis_engine.py را مسطح کردیم، این اصلاح ضروری است.
                row = (
                    f"💎 *{escape_markdown(alert.get('symbol_name', 'N/A'))}*\n"
                    f"📈 Score: `{alert.get('score')}` | Power: `{alert.get('power_ratio')}`\n"
                    f"💰 Price: `{alert.get('last_price')}` | Target: `{alert.get('target')}`\n"
                    f"📜 Reasons: {', '.join(alert.get('reasons', []))}\n"
                    f"------------------"
                )
                message_lines.append(row)
            
            full_msg = "\n".join(message_lines)
            
            try:
                notifier.send_message(full_msg)
                logger.info(f"📨 Sent {len(strong_buy_alerts)} alerts to Telegram.")
            except Exception as e:
                logger.error(f"❌ Failed to send Telegram message: {e}")
            
            alerts_sent = len(strong_buy_alerts)
        
        # 5. ذخیره لاگ جیسون (فراخوانی تابع اصلاح‌شده)
        save_json_log(strong_buy_alerts)
        
        return {
            "status": "success", 
            "symbols_checked": len(potential_symbols),
            "alerts_generated": alerts_sent
        }

    finally:
        db_session.close()

# ==========================
# مسیرهای Flask (Routes)
# ==========================

@app.route('/')
def index():
    return "<h1>🤖 Morning Assistant API is Running</h1><p>Use /run to trigger analysis.</p>"

@app.route('/run', methods=['GET', 'POST'])
def manual_run():
    """
    این اندپوینت را می‌توانید هر دقیقه (توسط زمان‌بند خارجی) یا دستی صدا بزنید.
    """
    result = process_market_analysis()
    return jsonify(result)

@app.route('/health')
def health_check():
    # بررسی ساده اتصال به ردیس
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, socket_timeout=1)
        r.ping()
        redis_status = "UP"
    except:
        redis_status = "DOWN"
        
    return jsonify({"status": "ok", "redis": redis_status, "time": datetime.now().isoformat()})

if __name__ == "__main__":
    # اجرا روی پورت 5000
    logger.info("🚀 Flask Server Starting on port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=False)
