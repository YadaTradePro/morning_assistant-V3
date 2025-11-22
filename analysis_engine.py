# analysis_engine.py
# وظیفه: ترکیب داده‌های لحظه‌ای بازار با داده‌های تکنیکال دیتابیس و محاسبه امتیاز خرید

import math
from typing import Dict, Any, Optional
import logging
from db_connector import get_symbol_name_by_id

logger = logging.getLogger(__name__)

# --- تنظیمات استراتژی (قابل تغییر) ---
MIN_POWER_RATIO = 2.0         # حداقل قدرت خریدار (کمی سخت‌گیرانه‌تر کردم)
MIN_VOLUME_TO_BASE_PERCENT = 0.5 # حداقل حجم معامله شده نسبت به مبنا (0.5 یعنی 50 درصد حجم مبنا پر شده باشد)
SCORE_THRESHOLD = 6.0         # حداقل امتیاز برای سیگنال خرید

# ... توابع کمکی ...
def to_float_or_zero(value: Any) -> float:
    """تبدیل مقدار به float و در صورت None یا خالی بودن به 0.0"""
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    """تقسیم ایمن برای جلوگیری از خطای تقسیم بر صفر"""
    try:
        if b == 0 or b is None:
            return default
        return float(a) / float(b)
    except Exception:
        return default

def compute_power_ratio(buy_vol, buy_count, sell_vol, sell_count) -> float:
    """محاسبه سرانه خرید به سرانه فروش (Power Ratio)"""
    buy_avg = safe_div(buy_vol, buy_count, default=0.0)
    sell_avg = safe_div(sell_vol, sell_count, default=1.0)
    
    if sell_avg == 0:
        return 100.0 if buy_avg > 0 else 0.0 # اگر فروشنده صفر بود و خریدار بود، قدرت بالاست
    
    return round(buy_avg / sell_avg, 2)

def estimate_atr_from_live(live: Dict[str, Any]) -> float:
    """تخمین نوسان (ATR) از روی High-Low روز جاری اگر ATR تاریخی نباشد"""
    try:
        high = float(live.get('high_price', 0) or 0)
        low = float(live.get('low_price', 0) or 0)
        if high > 0 and low > 0:
            return max(0.0, high - low)
        return 0.0
    except Exception:
        return 0.0

def escape_markdown(text: str) -> str:
    """اسکیپ کردن کاراکترهای خاص برای تلگرام"""
    if not text: return ""
    replacements = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for ch in replacements:
        text = text.replace(ch, f"\\{ch}")
    return text
    
# --------------------------------------------------------------------------
# 💡 تابع جدید برای ساخت گزارش نهایی قابل نمایش در داشبورد یا تلگرام
# --------------------------------------------------------------------------
def generate_signal_report(signal_result: Dict[str, Any]) -> str:
    """
    گزارش سیگنال نهایی را از دیکشنری خروجی analysis_engine می‌سازد.
    نام نماد را از symbol_id یا symbol_name موجود در نتیجه واکشی می‌کند.
    """
    
    # 1. واکشی نام نماد (اولویت با symbol_name که در مرحله تحلیل تولید شده)
    # اگر symbol_name موجود نباشد، از symbol_id استفاده کرده و آن را به نام تبدیل می کند.
    symbol_name = signal_result.get('symbol_name')
    if not symbol_name:
        symbol_id = signal_result.get('symbol_id')
        if symbol_id:
            symbol_name = get_symbol_name_by_id(symbol_id)
            
    # اگر همچنان نامی پیدا نشد، از symbol_id استفاده می کنیم
    name_display = symbol_name if symbol_name else signal_result.get('symbol_id', 'Unknown Symbol')
    
    # 2. ساخت لیست دلایل با استایل تلگرام
    reasons_list = signal_result.get('reasons', [])
    reasons_str = "، ".join(reasons_list)
    
    # 3. ساخت گزارش نهایی
    report = (
        f"✅ *{escape_markdown(name_display)}* - سیگنال خرید قوی\n"
        f"------------------------------\n"
        f"امتیاز: *{signal_result.get('score', 0.0):.1f} / 10*\n"
        f"دلایل: {reasons_str}\n"
        f"قدرت خریدار: {signal_result.get('power_ratio', 0.0):.2f}\n"
        f"تغییر قیمت: {signal_result.get('percent_change', 0.0):.2f}% \n\n"
        f"💰 *مدیریت ریسک:*\n"
        f"قیمت ورود: {signal_result.get('entry', 0)} ({signal_result.get('last_price', 0)})\n"
        f"حد سود (Target): {signal_result.get('target', 0)}\n"
        f"حد ضرر (Stop Loss): {signal_result.get('stop', 0)}\n"
        f"نسبت ریسک/بازدهی: 1 به {signal_result.get('risk_reward', 0.0):.1f}\n"
    )

    return report
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------

# --- تحلیلگر اصلی ---

def analyze_symbol_combined(live: Dict[str, Any], phase1: Dict[str, Any]) -> Dict[str, Any]:
    """
    live: دیکشنری داده‌های لحظه‌ای (از Redis/Orchestrator)
          Keys: symbol, last_price, volume, individual_buy_vol, ...
    phase1: دیکشنری داده‌های دیتابیس (تکنیکال، واچ‌لیست و ...)
          Keys: symbol_id, symbol_name, golden_key_score, RSI, ...
    
    Returns: دیکشنری شامل امتیاز، حد سود/ضرر و وضعیت خرید
    """

    # 1. استخراج شناسه‌ها
    # live['symbol'] نام فارسی است (طبق فایل phase1_orchestrator)
    symbol_label = live.get('symbol') or phase1.get('symbol_name') or "Unknown"
    tsetmc_id = phase1.get('symbol_id') # کد عددی

    # 2. استخراج قیمت‌ها و حجم‌ها
    # 💡 اصلاح: استفاده از تابع to_float_or_zero برای اطمینان از تبدیل صحیح
    last_price = to_float_or_zero(live.get('last_price'))
    adj_close = to_float_or_zero(live.get('adj_close') or last_price)
    
    # حجم لحظه‌ای
    tvol = to_float_or_zero(live.get('volume'))
    
    # ⚠️ نکته مهم: در فاز 1 باید مطمئن شویم base_volume کش شده است.
    # اگر نبود، پیش‌فرض 1 می‌گذاریم تا تقسیم بر صفر نشود، ولی هشدار دارد.
    bvol = to_float_or_zero(live.get('base_volume') or live.get('bvol') or 1)

    # قیمت‌های بازشایی و پایانی دیروز
    pf = to_float_or_zero(live.get('open_price'))
    py = to_float_or_zero(live.get('yesterday_price'))

    # 3. داده‌های حقیقی/حقوقی (از Orchestrator)
    buy_i_vol = to_float_or_zero(live.get('individual_buy_vol'))
    buy_i_count = to_float_or_zero(live.get('individual_buy_count'))
    sell_i_vol = to_float_or_zero(live.get('individual_sell_vol'))
    sell_i_count = to_float_or_zero(live.get('individual_sell_count'))

    # 4. داده‌های فاز 1 (از دیتابیس)
    # پشتیبانی از نام‌های مختلف ستون‌ها در دیتابیس
    golden_key_score = to_float_or_zero(phase1.get('golden_key_score') or phase1.get('score'))
    rsi_val = to_float_or_zero(phase1.get('RSI') or 50)
    halftrend = int(to_float_or_zero(phase1.get('halftrend_signal') or 0))
    pattern = str(phase1.get('pattern_name') or '').lower()
    
    # 5. محاسبات متریک‌ها
    power_ratio = compute_power_ratio(buy_i_vol, buy_i_count, sell_i_vol, sell_i_count)
    volume_ratio = safe_div(tvol, bvol, default=0.0) # نسبت حجم به مبنا
    
    # بررسی گپ مثبت (قیمت باز شدن بالاتر از قیمت پایانی دیروز)
    gap_positive = (pf > py) if (pf > 0 and py > 0) else False

    # 6. سیستم امتیازدهی (Scoring Engine)
    score = 0.0
    reasons = []

    # A) امتیاز تکنیکال (Golden Key)
    if golden_key_score >= 80:
        score += 3.0
        reasons.append(f"GoldenKey ⭐ ({int(golden_key_score)})")
    elif golden_key_score >= 50:
        score += 1.5
        reasons.append(f"GoldenKey ({int(golden_key_score)})")

    # B) تابلوخوانی - قدرت خریدار
    if power_ratio >= MIN_POWER_RATIO:
        score += 2.5
        reasons.append(f"PowerRatio 🚀 ({power_ratio})")
    elif power_ratio >= 1.5:
        score += 1.0
        reasons.append(f"PowerRatio ({power_ratio})")

    # C) تابلوخوانی - حجم مشکوک
    # اگر حجم بیش از 2 برابر حجم مبنا باشد
    if volume_ratio >= 2.0:
        score += 2.0
        reasons.append(f"HighVolume 📊 (x{volume_ratio:.1f})")
    elif volume_ratio >= 1.0:
        score += 1.0

    # D) وضعیت تکنیکال (RSI & Halftrend)
    if halftrend == 1:
        score += 1.0
        reasons.append("Halftrend Bullish")
    
    if 30 <= rsi_val <= 70:
        pass # منطقه خنثی
    elif rsi_val < 30:
        score += 1.0
        reasons.append(f"RSI Oversold ({int(rsi_val)})")

    # E) کندل استیک
    bullish_patterns = ['hammer', 'engulfing', 'morning', 'piercing']
    if any(p in pattern for p in bullish_patterns):
        score += 1.0
        reasons.append(f"Pattern: {pattern}")

    # F) گپ مثبت
    if gap_positive:
        score += 0.5
        reasons.append("Gap Up 📈")

    # نرمال‌سازی امتیاز (حداکثر 10)
    score = min(score, 10.0)

    # 7. مدیریت ریسک و نقاط ورود/خروج
    entry_price = last_price
    
    # تعیین حد سود و ضرر (ساده)
    # تارگت: 5 درصد بالاتر، حد ضرر: 3 درصد پایین‌تر (یا بر اساس استراتژی شما)
    tp_percent = 0.05
    sl_percent = 0.03
    
    target_price = round(entry_price * (1 + tp_percent))
    stop_loss = round(entry_price * (1 - sl_percent))

    # محاسبه ATR
    atr = estimate_atr_from_live(live)

    # شرط نهایی خرید قوی
    # باید امتیاز بالا باشد + قدرت خریدار خوب باشد + حجم معقول خورده باشد
    is_strong_buy = (
        score >= SCORE_THRESHOLD and 
        power_ratio >= 1.5 and 
        volume_ratio >= MIN_VOLUME_TO_BASE_PERCENT
    )

    return {
        "symbol_id": tsetmc_id,         # کد عددی (برای لینک دادن اگر نیاز شد)
        "symbol_name": symbol_label,     # نام فارسی (مثلا فولاد) -> داشبورد این را می‌خواهد
        
        "score": round(score, 1),
        "is_strong_buy": is_strong_buy,
        "reasons": reasons,
        
        # فیلدها را از داخل دیکشنری بیرون می‌آوریم (Unpack)
        "power_ratio": power_ratio,
        "volume_ratio": round(volume_ratio, 2),
        "rsi": rsi_val,
        "last_price": int(last_price),
        "percent_change": round(((last_price - py) / py) * 100, 2) if py > 0 else 0,
        
        "entry": int(entry_price),
        "target": int(target_price),
        "stop": int(stop_loss),
        "risk_reward": round(tp_percent / sl_percent, 2),
        
        # دیتای خام را نگه می‌داریم شاید برای دیباگ لازم شود
        "raw_live": live, 
        "phase1": phase1
    }