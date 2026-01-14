from datetime import datetime
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Boolean, Float, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import AsyncAttrs

Base = declarative_base()

class User(AsyncAttrs, Base):
    """Пользователи бота с оптимизированными индексами"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(32), nullable=True, index=True)
    first_name = Column(String(64), nullable=True)
    last_name = Column(String(64), nullable=True)
    
    # Marzban
    marzban_username = Column(String(50), unique=True, nullable=True, index=True)
    subscription_url = Column(String(500), nullable=True)
    
    # Subscription info
    is_active = Column(Boolean, default=False, index=True)
    data_limit = Column(BigInteger, nullable=True)
    expire_date = Column(DateTime, nullable=True, index=True)
    used_traffic = Column(BigInteger, default=0)
    
    # Trial
    trial_used = Column(Boolean, default=False, index=True)
    
    # Notifications
    notifications_enabled = Column(Boolean, default=True)
    notify_on_expire = Column(Boolean, default=True)
    notify_on_traffic = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Составные индексы для частых запросов
    __table_args__ = (
        Index('idx_user_active_expire', 'is_active', 'expire_date'),
        Index('idx_user_telegram_active', 'telegram_id', 'is_active'),
        Index('idx_user_trial_active', 'trial_used', 'is_active'),
    )
    
    def __repr__(self):
        return f"<User {self.telegram_id} - {self.username}>"

class Transaction(AsyncAttrs, Base):
    """Транзакции пользователей"""
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    telegram_id = Column(BigInteger, nullable=False, index=True)
    
    amount = Column(Float, nullable=False)
    description = Column(String(255), nullable=True)
    status = Column(String(20), default="pending", index=True)  # pending, completed, failed
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Индексы для аналитики
    __table_args__ = (
        Index('idx_transaction_status_date', 'status', 'created_at'),
        Index('idx_transaction_user_amount', 'user_id', 'amount'),
    )
    
    def __repr__(self):
        return f"<Transaction {self.id} - User {self.telegram_id}>"

class Message(AsyncAttrs, Base):
    """Сообщения пользователей и администраторов"""
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True)
    from_telegram_id = Column(BigInteger, nullable=False, index=True)
    to_telegram_id = Column(BigInteger, nullable=True, index=True)  # None = to admin
    
    message_text = Column(String(4000), nullable=False)
    is_read = Column(Boolean, default=False, index=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Индексы для быстрого поиска непрочитанных
    __table_args__ = (
        Index('idx_messages_unread', 'is_read', 'created_at'),
        Index('idx_messages_from_to', 'from_telegram_id', 'to_telegram_id'),
    )
    
    def __repr__(self):
        return f"<Message {self.id}>"
