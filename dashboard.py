import streamlit as st
import json
import glob
import os
import pandas as pd
from datetime import datetime
import plotly.express as px
import numpy as np
# 💡 ایمپورت کتابخانه رفرش خودکار
from streamlit_autorefresh import st_autorefresh 

# --- تنظیمات رفرش خودکار ---
# هر ۵ ثانیه رفرش شود (۵ * ۱۰۰۰ میلی‌ثانیه)
# این خط، کل صفحه داشبورد را به صورت خودکار رفرش می‌کند.
count = st_autorefresh(interval=5000, key="data_refresher") 

# تنظیمات صفحه
st.set_page_config(page_title="TSE Trader Dashboard", layout="wide")

st.title("🚀 داشبورد دستیار خرید TSE (فاز ۲) - Cache Reader")
st.markdown("---")

# تعیین مسیر لاگ‌ها (فرض بر این است که main.py لاگ‌ها را در پوشه 'logs' ذخیره می‌کند)
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True) 

# پیدا کردن آخرین JSON لاگ
# جستجو در داخل پوشه logs
logs = glob.glob(os.path.join(LOG_DIR, "phase2_alerts_*.json"))
# 💡 اصلاح: فیلتر کردن لاگ‌ها بر اساس تاریخ امروز
today_date_str = datetime.now().strftime('%Y%m%d')

# فقط فایل‌هایی را که تاریخ امروز را در نام خود دارند (YYYYMMDD) در نظر بگیرید.
today_logs = [log for log in logs if today_date_str in os.path.basename(log)]

if today_logs:
    # از بین لاگ‌های امروز، جدیدترین را انتخاب کنید.
    latest_log = max(today_logs, key=os.path.getctime) 
    
    try:
        with open(latest_log, 'r', encoding='utf-8') as f:
            data = json.load(f)
        alerts = data.get('alerts', [])
        timestamp = data['timestamp']
    except Exception as e:
        st.error(f"خطا در خواندن یا پردازش فایل لاگ ({latest_log}): {e}")
        alerts = []
        timestamp = "نامشخص"

    if alerts:
        # تبدیل alerts به DataFrame
        df = pd.DataFrame(alerts)

        # 💡 اصلاح: نگاشت فیلدهای JSON به نام‌های فارسی برای نمایش در داشبورد
        df = df.rename(columns={
            'symbol_id': 'نماد (کد)', # نگهداری کد عددی
            'symbol_name': 'نماد',    # 👈 استفاده از نام نماد فارسی
            'score': 'امتیاز',
            'reasons': 'دلایل',
            'entry': 'ورود (قیمت)',
            'target': 'هدف (قیمت)',
            'stop': 'حد ضرر (قیمت)',
            'power_ratio': 'قدرت خریدار',
            'volume_ratio': 'نسبت حجم',
            'is_strong_buy': 'خرید قوی'
        })
        
        # مرتب‌سازی بر اساس امتیاز
        df = df.sort_values(by='امتیاز', ascending=False)

        # تبدیل لیست دلایل به رشته برای نمایش در جدول
        df['دلایل'] = df['دلایل'].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)

        st.subheader("📊 لیست هشدارهای اخیر")
        
        # نمایش جدول با ستون‌های به‌روز شده
        # 💡 اصلاح: نمایش 'نماد' (فارسی) به جای 'نماد (کد)'
        st.dataframe(
            df[['نماد', 'امتیاز', 'قدرت خریدار', 'نسبت حجم', 'ورود (قیمت)', 'هدف (قیمت)', 'حد ضرر (قیمت)', 'دلایل', 'خرید قوی', 'نماد (کد)']], 
            width='stretch', 
            height=350 
        )

        # چارت امتیازها
        # 💡 اصلاح: استفاده از 'نماد' برای محور X
        fig = px.bar(
            df, 
            x='نماد', 
            y='امتیاز', 
            title="امتیازهای هشدارها (به ترتیب نزولی)", 
            color='امتیاز', 
            color_continuous_scale='viridis',
            height=400
        )
        st.plotly_chart(fig, use_container_width=True) # width='stretch' در اینجا با use_container_width=True جایگزین شد

        # Metricها برای top alert
        top_alert = df.iloc[0] if not df.empty else None
        
        # 💡 اصلاح خطای 'The truth value of a Series is ambiguous'
        if top_alert is not None:
            # محاسبه دلتا
            entry_price = top_alert['ورود (قیمت)']
            target_price = top_alert['هدف (قیمت)']
            
            delta_value = target_price - entry_price
            
            # 💡 بهبود پایداری: بررسی برای جلوگیری از تقسیم بر صفر
            if entry_price and entry_price != 0:
                delta_percent = (delta_value / entry_price) * 100 
            else:
                delta_percent = 0

            col1, col2, col3, col4 = st.columns(4)
            # 💡 اصلاح: نمایش نام فارسی در metric اول
            col1.metric("نماد برتر", top_alert['نماد']) 
            col2.metric("امتیاز", top_alert['امتیاز'])
            col3.metric("ورود پیشنهادی", f"{entry_price:,}")
            # محاسبه دلتا و نمایش آن
            col4.metric(
                "هدف قیمتی", 
                f"{target_price:,}", 
                delta=f"{delta_percent:.1f}% ({delta_value:,.0f} ریال)",
                delta_color="normal"
            )

        st.info(f"آخرین به‌روزرسانی: {timestamp}")
        st.download_button(
            "⬇️ دانلود CSV", 
            df.to_csv(index=False).encode('utf-8'), # Encode برای utf-8
            f"alerts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", 
            "text/csv;charset=utf-8"
        )
    else:
        st.warning("هیچ هشداری در این اجرا یافت نشد.")
else:
    st.warning("⚠️ فایل لاگ هشدار یافت نشد. لطفاً ابتدا اسکریپت اصلی (main.py) را اجرا کنید.")

# دکمه رفرش دستی
if st.button("🔄 رفرش دستی داده‌ها"):
    st.rerun()

st.markdown("---")
st.caption("ساخته‌شده با Streamlit – برای تست: streamlit run dashboard.py")
