from datetime import datetime
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import AsyncAttrs

Base = declarative_base()

class User(AsyncAttrs, Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    
    # Marzban
    marzban_username = Column(String, unique=True, nullable=True)
    subscription_url = Column(String, nullable=True)
    
    # Subscription info
    is_active = Column(Boolean, default=False)
    data_limit = Column(BigInteger, nullable=True)
    expire_date = Column(DateTime, nullable=True)
    used_traffic = Column(BigInteger, default=0)
    
    # Trial
    trial_used = Column(Boolean, default=False)
    
    # Notifications
    notifications_enabled = Column(Boolean, default=True)
    notify_on_expire = Column(Boolean, default=True)
    notify_on_traffic = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<User {self.telegram_id} - {self.username}>"

class Transaction(AsyncAttrs, Base):
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    telegram_id = Column(BigInteger, nullable=False)
    
    amount = Column(Float, nullable=False)
    description = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending, completed, failed
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Transaction {self.id} - User {self.telegram_id}>"

class Message(AsyncAttrs, Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True)
    from_telegram_id = Column(BigInteger, nullable=False)
    to_telegram_id = Column(BigInteger, nullable=True)  # None = to admin
    
    message_text = Column(String, nullable=False)
    is_read = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Message {self.id}>"
