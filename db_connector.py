# db_connector.py
import os
import uuid
from datetime import date, datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, Date, DateTime, UniqueConstraint, ForeignKey, Text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.engine import Engine
from typing import Optional


# 1. تنظیمات آدرس دیتابیس
# آدرس مستقیم
DATABASE_URL = "sqlite:///E:/BourseAnalysis/V-3/Backend-V3/app.db"
# اگر می‌خواهید از .env استفاده کنید:
# load_dotenv()
# DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./phase1_db.sqlite")

# تعریف Base برای SQLAlchemy Declarative
Base = declarative_base()

# =================================================================
# --- مدل‌های داده اصلی (اصلاح‌شده بر اساس ساختار کامل شما) ---
# =================================================================

class WeeklyWatchlistResult(Base):
    """مدل مربوط به نتایج نهایی هفتگی."""
    __tablename__ = 'weekly_watchlist_results'
    id = Column(Integer, primary_key=True)
    signal_unique_id = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    
    # Foreign Key به comprehensive_symbol_data
    symbol_id = Column(String(50), ForeignKey('comprehensive_symbol_data.symbol_id'), nullable=False, index=True) 
    symbol_name = Column(String(100), nullable=False)
    
    entry_price = Column(Float, nullable=False)
    entry_date = Column(Date, nullable=False)
    jentry_date = Column(String(10), nullable=False)
    outlook = Column(String(255))
    reason = Column(Text)
    probability_percent = Column(Float)
    score = Column(Float, nullable=True)
    
    status = Column(String(50), default='active', nullable=False)
    exit_price = Column(Float, nullable=True)
    exit_date = Column(Date, nullable=True)
    jexit_date = Column(String(10), nullable=True)
    profit_loss_percentage = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f"<WeeklyWatchlistResult {self.symbol_id}>"


class GoldenKeyResult(Base):
    """مدل مربوط به نتایج فیلتر Golden Key."""
    __tablename__ = 'golden_key_results'
    id = Column(Integer, primary_key=True)
    symbol_id = Column(String(50), ForeignKey('comprehensive_symbol_data.symbol_id'), nullable=False, index=True)
    symbol_name = Column(String(100), nullable=False)
    
    # این ستون برای کوئری main.py حیاتی بود!
    jdate = Column(String(10), nullable=False) 
    
    is_golden_key = Column(Boolean, default=False)
    score = Column(Integer, default=0)
    reason = Column(Text)
    timestamp = Column(DateTime, default=datetime.now)
    satisfied_filters = Column(Text)
    recommendation_price = Column(Float)
    recommendation_jdate = Column(String(10))
    status = Column(String(50), default='active', nullable=True)
    
    __table_args__ = (
        UniqueConstraint('symbol_id', 'jdate', name='_symbol_jdate_golden_key_uc'),
    )

    def __repr__(self):
        return f'<GoldenKeyResult {self.symbol_name} {self.jdate} (Score: {self.score})>'


class PotentialBuyQueueResult(Base):
    """مدل مربوط به نتایج صف خرید بالقوه."""
    __tablename__ = 'potential_buy_queue_results'
    id = Column(Integer, primary_key=True)
    symbol_id = Column(String(50), ForeignKey('comprehensive_symbol_data.symbol_id'), nullable=False, index=True) 
    symbol_name = Column(String(255), nullable=False)
    
    # این ستون برای کوئری main.py حیاتی بود!
    jdate = Column(String(10), nullable=False) 
    
    reason = Column(Text, nullable=True)
    current_price = Column(Float, nullable=True)
    volume_change_percent = Column(Float, nullable=True)
    real_buyer_power_ratio = Column(Float, nullable=True)
    matched_filters = Column(Text, nullable=True)
    group_type = Column(String(50), nullable=True)
    timestamp = Column(DateTime, default=datetime.now)
    probability_percent = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint('symbol_id', 'jdate', name='_symbol_jdate_potential_queue_uc'),
    )

    def __repr__(self):
        return f'<PotentialBuyQueueResult {self.symbol_name} {self.jdate}>'


# -----------------------------------------------------------------
# --- مدل‌های مورد نیاز برای فاز 2 و داده‌های تکنیکال ---
# -----------------------------------------------------------------

class ComprehensiveSymbolData(Base):
    """
    💡مدل ضروری: برای تعریف Foreign Key مورد نیاز است.
    """
    __tablename__ = 'comprehensive_symbol_data'
    # در اینجا فقط فیلدهایی که در Foreign Key استفاده شده را اضافه می‌کنیم.
    symbol_id = Column(String(50), primary_key=True, unique=True, nullable=False) 
    symbol_name = Column(String(100))

    def __repr__(self):
        return f'<Symbol {self.symbol_name}>'

class TechnicalIndicatorData(Base):
    """داده‌های شاخص‌های تکنیکال."""
    __tablename__ = 'technical_indicator_data'
    id = Column(Integer, primary_key=True)
    symbol_id = Column(String(50), index=True)
    
    # این ستون برای کوئری main.py حیاتی بود!
    jdate = Column(String(10), index=True) 
    
    RSI = Column(Float)
    halftrend_signal = Column(Integer)
    # اضافه کردن created_at برای اطمینان از مرتب‌سازی در صورت نبود jdate دقیق
    created_at = Column(DateTime, default=datetime.now) 


class CandlestickPatternDetection(Base):
    """نتایج تشخیص الگوهای کندل استیک."""
    __tablename__ = 'candlestick_pattern_detection'
    id = Column(Integer, primary_key=True)
    symbol_id = Column(String(50), index=True)
    
    # این ستون برای کوئری main.py حیاتی بود!
    jdate = Column(String(10), index=True) 
    
    pattern_name = Column(String(100))
    # اضافه کردن created_at برای اطمینان از مرتب‌سازی در صورت نبود jdate دقیق
    created_at = Column(DateTime, default=datetime.now) 


class DynamicSupportOpportunity(Base):
    """ذخیره سازی نتایج نهایی تحلیل حمایت دینامیک و پول هوشمند."""
    __tablename__ = 'dynamic_support_opportunities'
    id = Column(Integer, primary_key=True)
    
    analysis_date = Column(Date, default=date.today, nullable=False) 
    symbol_id = Column(String(50), nullable=False)
    symbol_name = Column(String(100), nullable=False)
    
    current_price = Column(Float, nullable=False)
    support_level = Column(Float, nullable=False)
    distance_from_support = Column(Float, nullable=False) 
    power_ratio = Column(Float, nullable=False) 
    
    created_at = Column(DateTime, default=datetime.now)
    
    __table_args__ = (
        UniqueConstraint('symbol_id', 'analysis_date', name='uq_symbol_date'),
    )

    def __repr__(self):
        return f'<DynamicSupportOpportunity {self.symbol_name} on {self.analysis_date}>'

# =================================================================
# --- تنظیمات Engine و Session ---
# =================================================================

# Engine creation: for sqlite on windows, pass connect_args
engine_kwargs = {}

if DATABASE_URL.startswith("sqlite"):
    # تنظیم check_same_thread: False برای SQLite در محیط چند-رشته‌ای
    # اضافه کردن 'timeout': 60 برای مدیریت خطای "database is locked"
    engine_kwargs = {
        "connect_args": {
            "check_same_thread": False,
            "timeout": 60 
        }
    }
    
engine: Engine = create_engine(DATABASE_URL, echo=False, **engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)

def get_db_session() -> Session:
    """
    یک سشن جدید SQLAlchemy برمی‌گرداند. فراخواننده موظف به بستن آن با close() است.
    """
    return SessionLocal()

def create_tables():
    """ایجاد تمام جداول تعریف شده در Base."""
    Base.metadata.create_all(bind=engine)

def get_symbol_name_by_id(symbol_id: str) -> Optional[str]:
    """
    نام نماد (symbol_name) را با استفاده از symbol_id از جدول
    comprehensive_symbol_data استخراج می کند.
    """
    session = get_db_session()
    try:
        # جستجوی نام نماد بر اساس symbol_id
        result = session.query(ComprehensiveSymbolData.symbol_name)\
                        .filter(ComprehensiveSymbolData.symbol_id == symbol_id)\
                        .scalar()
        
        return result
        
    except Exception as e:
        # در صورت بروز هرگونه خطا (مثلاً عدم اتصال)
        logging.error(f"❌ Error fetching symbol name for ID {symbol_id}: {e}")
        return None
    finally:
        session.close()


if __name__ == '__main__':
    # در صورت اجرای مستقیم فایل، جداول را ایجاد می‌کند.
    create_tables()
    print("✅ Database tables created/checked.")