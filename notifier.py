# notifier.py
# وظیفه: ارسال پیام‌ها و سیگنال‌ها به تلگرام

import os
import requests
import time
import logging

logger = logging.getLogger(__name__)

# خواندن متغیرهای محیطی
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

class TelegramNotifier:
    """
    کلاسی برای ارسال سیگنال‌ها و پیام‌های متنی به تلگرام با استفاده از MarkdownV2.
    """
    def __init__(self, bot_token=None, chat_id=None, max_retries=3):
        self.bot_token = bot_token or TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or TELEGRAM_CHAT_ID
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram token/chat_id not set. Notifier will be inactive.")
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.max_retries = max_retries

    def _md_escape(self, s: str) -> str:
        """فرار دادن کاراکترهای خاص مورد نیاز MarkdownV2 به جز پارامترهای مجاز."""
        if not s:
            return ""
        # این لیست شامل تمام کاراکترهای خاص در MarkdownV2 است.
        replacements = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for ch in replacements:
            s = s.replace(ch, f"\\{ch}")
        return s

    def _send_request(self, text: str, parse_mode: str = "MarkdownV2") -> bool:
        """منطق ارسال پیام با تلاش مجدد (Retry Mechanism)"""
        if not self.bot_token or not self.chat_id:
            return False

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                r = requests.post(url, json=payload, timeout=10)
                r.raise_for_status()
                # 200 (OK)
                return True
            except requests.RequestException as e:
                logger.warning(f"⚠️ تلاش {attempt} برای ارسال پیام ناموفق بود: {e}")
                time.sleep(2 * attempt)
            
        logger.error("❌ ارسال پیام پس از چند تلاش ناموفق ماند.")
        return False

    def send_message(self, text: str) -> bool:
        """
        💡 اضافه شده: تابعی برای ارسال پیام‌های خام (مانند summary یا لیست سیگنال‌ها).
        این تابع در main.py برای ارسال پیام‌های فرمت‌شده استفاده می‌شود.
        """
        if not text:
            return False
        
        # پیام خام از main.py می‌آید و فرض می‌شود Escape شده است.
        return self._send_request(text=text, parse_mode="MarkdownV2")


    def send_alert(self, alert: dict) -> bool:
        """
        پیام هشدار خرید را به تلگرام ارسال می‌کند.
        فیلدهای دیکشنری alert باید مسطح (Flat) باشند (سازگار با analysis_engine.py جدید).
        """
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram not configured, skipping send_alert.")
            return False

        # --- قالب بندی پیام با استفاده از کلیدهای مسطح (Flat Keys) ---
        text_lines = [
            f"📈 *سیگنال خرید قوی شناسایی شد!*",
            f"نماد: *{alert.get('symbol_name') or alert.get('symbol_id')}*",
            "",
            f"امتیاز سیگنال: `{alert.get('score', 'N/A')}`",
            f"قدرت خریدار به فروشنده: `{alert.get('power_ratio', 'N/A')}`",
            f"نسبت حجم به میانگین: `{alert.get('volume_ratio', 'N/A')}`",
            "",
            f"نقطه ورود: `{alert.get('entry', 'N/A')}`",
            f"هدف قیمتی: `{alert.get('target', 'N/A')}`",
            f"حد ضرر: `{alert.get('stop', 'N/A')}`",
            "",
            f"دلایل شناسایی سیگنال:",
            "، ".join([str(r) for r in alert.get('reasons', [])]) or "—",
            "",
            f"⏱ سیستم: *دستیار معاملاتی صبحگاهی یادا*"
        ]
        text = "\n".join(text_lines)

        # متن پیام را برای تلگرام Escaping می‌کنیم
        payload_text = self._md_escape(text)

        # ارسال پیام
        success = self._send_request(text=payload_text, parse_mode="MarkdownV2")
        if success:
            logger.info(f"✅ پیام تکی برای {alert.get('symbol_name') or alert.get('symbol_id')} ارسال شد.")
        return success