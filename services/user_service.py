"""
Сервис для работы с пользователями - слой бизнес-логики
"""
from datetime import datetime, timedelta
from typing import Optional, List
from database.db_manager import db_manager
from marzban.api_client import marzban_api
from types.schemas import (
    UserCreateSchema, 
    UserUpdateSchema, 
    SubscriptionCreateSchema,
    SubscriptionInfoSchema,
    UserResponseSchema
)
from utils.helpers import generate_username, format_bytes, calculate_expire_days
from utils.retry_handler import retry, RETRY_CONFIGS, retry_handler
from config import settings
from utils.logger import logger


class UserService:
    """Сервис для управления пользователями"""
    
    def __init__(self):
        self.db = db_manager
        self.api = marzban_api
    
    async def get_user(self, telegram_id: int) -> Optional[UserResponseSchema]:
        """Получить пользователя по Telegram ID"""
        user = await self.db.get_user(telegram_id)
        if not user:
            return None
        return UserResponseSchema.from_orm(user)
    
    async def create_user(self, user_data: UserCreateSchema) -> UserResponseSchema:
        """Создать нового пользователя"""
        # Проверяем, не существует ли уже пользователь
        existing = await self.db.get_user(user_data.telegram_id)
        if existing:
            raise ValueError(f"User with telegram_id {user_data.telegram_id} already exists")
        
        user = await self.db.create_user(
            telegram_id=user_data.telegram_id,
            username=user_data.username,
            first_name=user_data.first_name,
            last_name=user_data.last_name
        )
        
        logger.info(f"Created new user: {user_data.telegram_id}")
        return UserResponseSchema.from_orm(user)
    
    async def update_user(self, telegram_id: int, update_data: UserUpdateSchema) -> bool:
        """Обновить данные пользователя"""
        update_dict = update_data.dict(exclude_unset=True)
        if not update_dict:
            raise ValueError("No data to update")
        
        success = await self.db.update_user(telegram_id, **update_dict)
        if success:
            logger.info(f"Updated user: {telegram_id}")
        return success
    
    @retry(
        max_attempts=3,
        exceptions=(Exception,),
        circuit_breaker_key="marzban_trial"
    )
    async def create_trial_subscription(self, telegram_id: int) -> dict:
        """
        Создание тестовой подписки с полной валидацией
        
        Returns:
            dict: Данные подписки (username, subscription_url, data_limit, expire_days)
        
        Raises:
            ValueError: Если пользователь не найден или уже имеет подписку
            Exception: Если не удалось создать подписку в Marzban
        """
        user = await self.db.get_user(telegram_id)
        
        if not user:
            raise ValueError("User not found")
        
        if user.trial_used:
            raise ValueError("Trial already used")
        
        if user.marzban_username:
            raise ValueError("User already has subscription")
        
        # Генерируем уникальное имя
        username = generate_username(telegram_id)
        
        # Создаем пользователя в Marzban с ретраями
        marzban_user = await self.api.create_user(
            username=username,
            data_limit=settings.TRIAL_DATA_LIMIT,
            expire_days=settings.TRIAL_EXPIRE_DAYS
        )
        
        expire_date = datetime.utcnow() + timedelta(days=settings.TRIAL_EXPIRE_DAYS)
        
        # Обновляем данные в БД
        await self.db.update_user(
            telegram_id,
            marzban_username=username,
            subscription_url=marzban_user.get('subscription_url', ''),
            trial_used=True,
            is_active=True,
            data_limit=settings.TRIAL_DATA_LIMIT,
            expire_date=expire_date
        )
        
        logger.info(f"Trial subscription created for user {telegram_id}")
        
        return {
            "username": username,
            "subscription_url": marzban_user.get('subscription_url', ''),
            "data_limit": settings.TRIAL_DATA_LIMIT,
            "expire_days": settings.TRIAL_EXPIRE_DAYS
        }
    
    async def get_subscription_info(self, telegram_id: int) -> Optional[SubscriptionInfoSchema]:
        """Получить информацию о подписке пользователя"""
        user = await self.db.get_user(telegram_id)
        
        if not user or not user.marzban_username:
            return None
        
        # Получаем актуальную информацию из Marzban
        usage = await self.api.get_user_usage(user.marzban_username)
        
        expire_date = datetime.fromtimestamp(usage['expire'])
        
        return SubscriptionInfoSchema(
            username=user.marzban_username,
            data_limit=usage['data_limit'],
            used_traffic=usage['used_traffic'],
            expire_date=expire_date,
            status=usage['status'],
            subscription_url=user.subscription_url or ""
        )
    
    @retry(
        max_attempts=3,
        exceptions=(Exception,),
        circuit_breaker_key="marzban_renew"
    )
    async def renew_subscription(
        self, 
        telegram_id: int, 
        days: int, 
        data_limit: Optional[int] = None
    ) -> bool:
        """
        Продление подписки пользователя
        
        Args:
            telegram_id: ID пользователя
            days: Количество дней для продления
            data_limit: Новый лимит трафика (если None - сохраняется текущий)
        
        Returns:
            bool: Успешно ли продлено
        """
        user = await self.db.get_user(telegram_id)
        
        if not user or not user.marzban_username:
            raise ValueError("User or subscription not found")
        
        # Получаем текущую информацию
        usage = await self.api.get_user_usage(user.marzban_username)
        
        # Вычисляем новую дату истечения
        current_expire = usage.get('expire', 0)
        if current_expire:
            current_expire_dt = datetime.fromtimestamp(current_expire)
            if current_expire_dt < datetime.utcnow():
                new_expire = datetime.utcnow() + timedelta(days=days)
            else:
                new_expire = current_expire_dt + timedelta(days=days)
        else:
            new_expire = datetime.utcnow() + timedelta(days=days)
        
        new_expire_timestamp = int(new_expire.timestamp())
        
        # Обновляем в Marzban
        await self.api.update_user(
            user.marzban_username,
            expire_days=days,
            data_limit=data_limit,
            status="active"
        )
        
        # Обновляем в БД
        await self.db.update_user(
            telegram_id,
            expire_date=new_expire,
            is_active=True,
            data_limit=data_limit or user.data_limit
        )
        
        logger.info(f"Subscription renewed for user {telegram_id} on {days} days")
        return True
    
    async def suspend_subscription(self, telegram_id: int) -> bool:
        """Приостановить подписку"""
        user = await self.db.get_user(telegram_id)
        
        if not user or not user.marzban_username:
            raise ValueError("User or subscription not found")
        
        await self.api.update_user(user.marzban_username, status="disabled")
        await self.db.update_user(telegram_id, is_active=False)
        
        logger.info(f"Subscription suspended for user {telegram_id}")
        return True
    
    async def activate_subscription(self, telegram_id: int) -> bool:
        """Активировать подписку"""
        user = await self.db.get_user(telegram_id)
        
        if not user or not user.marzban_username:
            raise ValueError("User or subscription not found")
        
        await self.api.update_user(user.marzban_username, status="active")
        await self.db.update_user(telegram_id, is_active=True)
        
        logger.info(f"Subscription activated for user {telegram_id}")
        return True
    
    async def delete_user(self, telegram_id: int) -> bool:
        """Удалить пользователя полностью"""
        user = await self.db.get_user(telegram_id)
        
        if not user:
            return False
        
        # Удаляем из Marzban
        if user.marzban_username:
            try:
                await self.api.delete_user(user.marzban_username)
            except Exception as e:
                logger.error(f"Failed to delete from Marzban: {e}")
        
        # Удаляем из БД
        await self.db.delete_user(telegram_id)
        
        logger.info(f"User {telegram_id} deleted")
        return True
    
    async def get_expiring_users(self, days: int = 3) -> List[UserResponseSchema]:
        """Получить пользователей с истекающей подпиской"""
        users = await self.db.get_expiring_users(days)
        return [UserResponseSchema.from_orm(user) for user in users]
    
    async def get_all_users(self, active_only: bool = False) -> List[UserResponseSchema]:
        """Получить всех пользователей"""
        users = await self.db.get_all_users(active_only)
        return [UserResponseSchema.from_orm(user) for user in users]
    
    async def sync_with_marzban(self, telegram_id: int) -> bool:
        """
        Синхронизировать данные пользователя с Marzban
        
        Returns:
            bool: Успешно ли синхронизировано
        """
        user = await self.db.get_user(telegram_id)
        
        if not user or not user.marzban_username:
            return False
        
        try:
            usage = await self.api.get_user_usage(user.marzban_username)
            
            await self.db.update_user(
                telegram_id,
                used_traffic=usage['used_traffic'],
                is_active=(usage['status'] == 'active')
            )
            
            logger.info(f"Synced user {telegram_id} with Marzban")
            return True
        except Exception as e:
            logger.error(f"Failed to sync user {telegram_id}: {e}")
            return False


# Глобальный экземпляр сервиса
user_service = UserService()