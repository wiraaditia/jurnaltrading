from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from datetime import datetime
from database import Base

class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, index=True)
    pair = Column(String, index=True, nullable=False)
    position_type = Column(String, nullable=False)  # Long / Short
    leverage = Column(Integer, default=1)
    entry_price = Column(Float, nullable=False)
    tp_price = Column(Float, nullable=True)
    sl_price = Column(Float, nullable=True)
    status = Column(String, default="Running")  # Win, Loss, Running, Cancelled
    pnl = Column(Float, default=0.0)  # PnL in percentage or USDT
    notes = Column(Text, nullable=True)
    image_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    id = Column(Integer, primary_key=True, index=True)
    pair = Column(String, index=True, nullable=False)
    position_type = Column(String, nullable=False)  # Long / Short
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=False)
    status = Column(String, nullable=False)  # Win / Loss
    pnl = Column(Float, default=0.0)  # PnL percentage or amount
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
