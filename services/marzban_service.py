"""
Сервис для работы с Marzban API
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from marzban.api_client import marzban_api
from types.schemas import MarzbanUserCreateSchema, MarzbanUserUpdateSchema, MarzbanUserResponseSchema
from utils.retry_handler import retry, RETRY_CONFIGS
from utils.logger import logger


class MarzbanService:
    """Сервис для взаимодействия с Marzban API"""
    
    def __init__(self):
        self.api = marzban_api
    
    @retry(
        max_attempts=3,
        exceptions=(Exception,),
        circuit_breaker_key="marzban_api"
    )
    async def create_user(self, user_data: MarzbanUserCreateSchema) -> MarzbanUserResponseSchema:
        """Создать пользователя в Marzban"""
        # Валидация данных
        user_data.dict()  # Pydantic автоматически проверит данные
        
        result = await self.api.create_user(
            username=user_data.username,
            data_limit=user_data.data_limit,
            expire_days=user_data.expire // 86400  # Конвертируем timestamp в дни
        )
        
        logger.info(f"Created Marzban user: {user_data.username}")
        return MarzbanUserResponseSchema(**result)
    
    @retry(
        max_attempts=3,
        exceptions=(Exception,),
        circuit_breaker_key="marzban_api"
    )
    async def get_user(self, username: str) -> Optional[MarzbanUserResponseSchema]:
        """Получить пользователя из Marzban"""
        try:
            result = await self.api.get_user(username)
            return MarzbanUserResponseSchema(**result)
        except Exception as e:
            logger.error(f"Failed to get user {username}: {e}")
            return None
    
    @retry(
        max_attempts=3,
        exceptions=(Exception,),
        circuit_breaker_key="marzban_api"
    )
    async def update_user(self, username: str, update_data: MarzbanUserUpdateSchema) -> bool:
        """Обновить пользователя в Marzban"""
        update_dict = update_data.dict(exclude_unset=True)
        
        if not update_dict:
            raise ValueError("No data to update")
        
        # Конвертируем expire_days в timestamp если нужно
        if 'expire' in update_dict:
            expire_timestamp = int((datetime.utcnow() + timedelta(days=update_dict['expire'])).timestamp())
            update_dict['expire'] = expire_timestamp
        
        await self.api.update_user(username, **update_dict)
        logger.info(f"Updated Marzban user: {username}")
        return True
    
    @retry(
        max_attempts=2,
        exceptions=(Exception,),
        circuit_breaker_key="marzban_api"
    )
    async def delete_user(self, username: str) -> bool:
        """Удалить пользователя из Marzban"""
        success = await self.api.delete_user(username)
        if success:
            logger.info(f"Deleted Marzban user: {username}")
        return success
    
    @retry(
        max_attempts=3,
        exceptions=(Exception,),
        circuit_breaker_key="marzban_api"
    )
    async def get_user_usage(self, username: str) -> Dict[str, Any]:
        """Получить информацию об использовании трафика"""
        return await self.api.get_user_usage(username)
    
    async def health_check(self) -> bool:
        """Проверить доступность Marzban API"""
        try:
            # Пробуем получить токен
            await self.api._get_token()
            return True
        except Exception as e:
            logger.error(f"Marzban health check failed: {e}")
            return False


# Глобальный экземпляр сервиса
marzban_service = MarzbanService()