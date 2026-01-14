from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, update, delete, func
from typing import Optional, List
from datetime import datetime, timedelta
from database.models import Base, User, Transaction, Message
from config import settings
from utils.logger import logger

class DatabaseManager:
    def __init__(self):
        self.engine = create_async_engine(settings.DATABASE_URL, echo=False)
        self.async_session = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
    
    async def init_db(self):
        """Инициализация БД"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized")
    
    async def get_session(self):
        """Получить сессию (generator для dependency injection)"""
        async with self.async_session() as session:
            yield session
    
    async def close(self):
        """Закрыть соединение с БД"""
        await self.engine.dispose()
    
    # ========== User operations ==========
    
    async def get_user(self, telegram_id: int) -> Optional[User]:
        """Получить пользователя по telegram_id"""
        async with self.async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()
    
    async def create_user(self, telegram_id: int, username: str = None, 
                         first_name: str = None, last_name: str = None) -> User:
        """Создать пользователя"""
        async with self.async_session() as session:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(f"User created: {telegram_id}")
            return user
    
    async def update_user(self, telegram_id: int, **kwargs) -> bool:
        """Обновить пользователя"""
        async with self.async_session() as session:
            result = await session.execute(
                update(User)
                .where(User.telegram_id == telegram_id)
                .values(**kwargs, updated_at=datetime.utcnow())
            )
            await session.commit()
            return result.rowcount > 0
    
    async def delete_user(self, telegram_id: int) -> bool:
        """Удалить пользователя"""
        async with self.async_session() as session:
            result = await session.execute(
                delete(User).where(User.telegram_id == telegram_id)
            )
            await session.commit()
            logger.info(f"User deleted: {telegram_id}")
            return result.rowcount > 0
    
    async def get_all_users(self, active_only: bool = False) -> List[User]:
        """Получить всех пользователей"""
        async with self.async_session() as session:
            query = select(User)
            if active_only:
                query = query.where(User.is_active == True)
            result = await session.execute(query)
            return result.scalars().all()
    
    async def get_users_count(self, active_only: bool = False) -> int:
        """Получить количество пользователей"""
        async with self.async_session() as session:
            query = select(func.count(User.id))
            if active_only:
                query = query.where(User.is_active == True)
            result = await session.execute(query)
            return result.scalar()
    
    async def get_expiring_users(self, days: int = 3) -> List[User]:
        """Получить пользователей с истекающей подпиской"""
        expire_date = datetime.utcnow() + timedelta(days=days)
        async with self.async_session() as session:
            result = await session.execute(
                select(User)
                .where(User.is_active == True)
                .where(User.expire_date <= expire_date)
                .where(User.notifications_enabled == True)
                .where(User.notify_on_expire == True)
            )
            return result.scalars().all()
    
    # ========== Transaction operations ==========
    
    async def create_transaction(self, user_id: int, telegram_id: int, 
                                 amount: float, description: str = None) -> Transaction:
        """Создать транзакцию"""
        async with self.async_session() as session:
            transaction = Transaction(
                user_id=user_id,
                telegram_id=telegram_id,
                amount=amount,
                description=description
            )
            session.add(transaction)
            await session.commit()
            await session.refresh(transaction)
            return transaction
    
    async def update_transaction(self, transaction_id: int, **kwargs) -> bool:
        """Обновить транзакцию"""
        async with self.async_session() as session:
            result = await session.execute(
                update(Transaction)
                .where(Transaction.id == transaction_id)
                .values(**kwargs, updated_at=datetime.utcnow())
            )
            await session.commit()
            return result.rowcount > 0
    
    async def get_transaction_by_order_id(self, order_id: str) -> Optional[Transaction]:
        """Получить транзакцию по order_id"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Transaction).where(Transaction.order_id == order_id)
            )
            return result.scalar_one_or_none()
    
    # ========== Message operations ==========
    
    async def create_message(self, from_telegram_id: int, message_text: str,
                            to_telegram_id: int = None) -> Message:
        """Создать сообщение"""
        async with self.async_session() as session:
            message = Message(
                from_telegram_id=from_telegram_id,
                to_telegram_id=to_telegram_id,
                message_text=message_text
            )
            session.add(message)
            await session.commit()
            await session.refresh(message)
            return message
    
    async def get_unread_messages(self, to_telegram_id: int = None) -> List[Message]:
        """Получить непрочитанные сообщения"""
        async with self.async_session() as session:
            query = select(Message).where(Message.is_read == False)
            if to_telegram_id:
                query = query.where(Message.to_telegram_id == to_telegram_id)
            else:
                query = query.where(Message.to_telegram_id.is_(None))
            result = await session.execute(query)
            return result.scalars().all()
    
    async def mark_message_read(self, message_id: int) -> bool:
        """Отметить сообщение прочитанным"""
        async with self.async_session() as session:
            result = await session.execute(
                update(Message)
                .where(Message.id == message_id)
                .values(is_read=True)
            )
            await session.commit()
            return result.rowcount > 0

db_manager = DatabaseManager()
