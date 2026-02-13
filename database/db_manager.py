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
    
    async def create_user(self, telegram_id: int = None, username: str = None,
                         first_name: str = None, last_name: str = None,
                         marzban_username: str = None, subscription_url: str = None,
                         is_active: bool = False, data_limit: int = None,
                         expire_date: datetime = None, used_traffic: int = 0,
                         trial_used: bool = False) -> User:
        """Создать пользователя"""
        async with self.async_session() as session:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                marzban_username=marzban_username,
                subscription_url=subscription_url,
                is_active=is_active,
                data_limit=data_limit,
                expire_date=expire_date,
                used_traffic=used_traffic,
                trial_used=trial_used
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(f"User created: {telegram_id or marzban_username}")
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

    async def sync_marzban_users(self) -> int:
        """Синхронизировать пользователей из Marzban (только если база пуста)"""
        from marzban.api_client import marzban_api
        from datetime import datetime
        from utils.helpers import extract_telegram_id_from_username
        
        # Проверяем, есть ли уже пользователи в базе
        users_count = await self.get_users_count()
        if users_count > 0:
            logger.info(f"База данных уже содержит {users_count} пользователей, синхронизация не требуется")
            return 0
        
        try:
            # Получаем список пользователей из Marzban
            response = await marzban_api.get_users(limit=1000)
            users = response.get("users", [])
            created_count = 0
            
            for marzban_user in users:
                username = marzban_user.get("username")
                if not username:
                    continue
                
                # Извлекаем telegram_id из имени пользователя (только для пользователей, созданных ботом)
                telegram_id = extract_telegram_id_from_username(username)
                if not telegram_id:
                    # Пропускаем пользователей, не созданных ботом (не соответствующих шаблону)
                    continue
                
                # Проверяем, существует ли уже пользователь с таким telegram_id
                async with self.async_session() as session:
                    result = await session.execute(
                        select(User).where(User.telegram_id == telegram_id)
                    )
                    existing = result.scalar_one_or_none()
                    if existing:
                        # Пользователь уже существует, возможно обновить данные
                        continue
                
                # Получаем информацию о подписке
                expire_timestamp = marzban_user.get("expire")
                expire_date = datetime.fromtimestamp(expire_timestamp) if expire_timestamp else None
                status = marzban_user.get("status", "disabled")
                is_active = status == "active"
                
                # Создаем пользователя с извлеченным telegram_id
                await self.create_user(
                    telegram_id=telegram_id,
                    marzban_username=username,
                    subscription_url=marzban_user.get("subscription_url"),
                    is_active=is_active,
                    data_limit=marzban_user.get("data_limit"),
                    expire_date=expire_date,
                    used_traffic=marzban_user.get("used_traffic", 0),
                    trial_used=False  # Не помечаем как тестовый
                )
                created_count += 1
                logger.info(f"Создан пользователь из Marzban: {username} (telegram_id: {telegram_id})")
            
            logger.info(f"Синхронизация завершена. Создано {created_count} пользователей (только созданные ботом)")
            return created_count
            
        except Exception as e:
            logger.error(f"Ошибка синхронизации пользователей из Marzban: {e}")
            return 0
    
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
            # Генерируем order_id
            import uuid
            order_id = f"order_{uuid.uuid4().hex[:10]}"
            
            transaction = Transaction(
                user_id=user_id,
                telegram_id=telegram_id,
                amount=amount,
                description=description,
                order_id=order_id
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
    
    async def update_transaction_by_order_id(self, order_id: str, **kwargs) -> bool:
        """Обновить транзакцию по order_id"""
        async with self.async_session() as session:
            result = await session.execute(
                update(Transaction)
                .where(Transaction.order_id == order_id)
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
