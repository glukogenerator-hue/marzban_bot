"""
Pydantic модели для строгой типизации и валидации данных
"""
from pydantic import BaseModel, Field, validator, EmailStr
from typing import Optional, List, Union, Literal
from datetime import datetime
import re


# ==================== User Schemas ====================

class UserBase(BaseModel):
    """Базовая схема пользователя"""
    telegram_id: int = Field(..., gt=0, description="Telegram ID пользователя")
    username: Optional[str] = Field(None, max_length=32, description="Telegram username")
    first_name: Optional[str] = Field(None, max_length=64, description="Имя пользователя")
    last_name: Optional[str] = Field(None, max_length=64, description="Фамилия пользователя")
    
    @validator('username')
    def validate_username(cls, v):
        if v is None:
            return v
        # Telegram username может содержать буквы, цифры, underscore
        if not re.match(r'^[a-zA-Z0-9_]{3,32}$', v):
            raise ValueError('Invalid Telegram username format')
        return v


class UserCreateSchema(UserBase):
    """Схема для создания пользователя"""
    telegram_id: int = Field(..., gt=0)


class UserUpdateSchema(BaseModel):
    """Схема для обновления пользователя"""
    username: Optional[str] = Field(None, max_length=32)
    first_name: Optional[str] = Field(None, max_length=64)
    last_name: Optional[str] = Field(None, max_length=64)
    marzban_username: Optional[str] = Field(None, max_length=100)
    subscription_url: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None
    data_limit: Optional[int] = Field(None, ge=0)
    expire_date: Optional[datetime] = None
    used_traffic: Optional[int] = Field(None, ge=0)
    trial_used: Optional[bool] = None
    notifications_enabled: Optional[bool] = None
    notify_on_expire: Optional[bool] = None


class UserResponseSchema(UserBase):
    """Схема ответа с информацией о пользователе"""
    id: int
    marzban_username: Optional[str]
    subscription_url: Optional[str]
    is_active: bool
    data_limit: Optional[int]
    expire_date: Optional[datetime]
    used_traffic: int
    trial_used: bool
    notifications_enabled: bool
    notify_on_expire: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ==================== Subscription Schemas ====================

class SubscriptionPlan(BaseModel):
    """Схема тарифного плана"""
    days: int = Field(..., gt=0, le=365)
    data_limit: int = Field(..., gt=0)
    price: int = Field(..., ge=0)
    
    @validator('data_limit')
    def validate_data_limit(cls, v):
        # Проверяем, что лимит в разумных пределах (от 1 ГБ до 10 ТБ)
        if v < 1_073_741_824 or v > 10_995_116_277_760:
            raise ValueError('Data limit must be between 1GB and 10TB')
        return v


class SubscriptionCreateSchema(BaseModel):
    """Схема для создания подписки"""
    username: str = Field(..., min_length=3, max_length=50)
    data_limit: int = Field(..., gt=0)
    expire_days: int = Field(..., gt=0, le=365)
    
    @validator('username')
    def validate_username(cls, v):
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('Username can only contain letters, numbers and underscore')
        return v
    
    @validator('data_limit')
    def validate_data_limit(cls, v):
        # Проверяем, что лимит в разумных пределах (от 1 ГБ до 10 ТБ)
        if v < 1_073_741_824 or v > 10_995_116_277_760:
            raise ValueError('Data limit must be between 1GB and 10TB')
        return v
    
    @validator('expire_days')
    def validate_expire_days(cls, v):
        # Дополнительная проверка (уже есть le=365 в Field)
        if v <= 0 or v > 365:
            raise ValueError('Expire days must be between 1 and 365')
        return v


class SubscriptionInfoSchema(BaseModel):
    """Схема информации о подписке"""
    username: str
    data_limit: int
    used_traffic: int
    expire_date: datetime
    status: str
    subscription_url: str
    
    @validator('status')
    def validate_status(cls, v):
        valid_statuses = ['active', 'disabled', 'expired', 'limited']
        if v not in valid_statuses:
            raise ValueError(f'Invalid status. Must be one of: {valid_statuses}')
        return v


# ==================== Transaction Schemas ====================

class TransactionBase(BaseModel):
    """Базовая схема транзакции"""
    user_id: int = Field(..., gt=0)
    telegram_id: int = Field(..., gt=0)
    amount: float = Field(..., gt=0)
    description: Optional[str] = Field(None, max_length=255)


class TransactionCreateSchema(TransactionBase):
    """Схема для создания транзакции"""
    pass


class TransactionResponseSchema(TransactionBase):
    """Схема ответа транзакции"""
    id: int
    status: Literal['pending', 'completed', 'failed']
    created_at: datetime
    
    class Config:
        from_attributes = True


# ==================== Message Schemas ====================

class MessageBase(BaseModel):
    """Базовая схема сообщения"""
    from_telegram_id: int = Field(..., gt=0)
    to_telegram_id: Optional[int] = Field(None, gt=0)
    message_text: str = Field(..., min_length=1, max_length=4000)


class MessageCreateSchema(MessageBase):
    """Схема для создания сообщения"""
    pass


class MessageResponseSchema(MessageBase):
    """Схема ответа сообщения"""
    id: int
    is_read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


# ==================== API Schemas ====================

class MarzbanUserCreateSchema(BaseModel):
    """Схема для создания пользователя в Marzban"""
    username: str = Field(..., min_length=3, max_length=50)
    proxies: dict = Field(default_factory=lambda: {"vless": {}})
    data_limit: int = Field(..., gt=0)
    expire: int = Field(..., gt=0)
    status: Literal['active', 'disabled'] = 'active'
    
    @validator('username')
    def validate_username(cls, v):
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('Invalid username format')
        return v


class MarzbanUserUpdateSchema(BaseModel):
    """Схема для обновления пользователя в Marzban"""
    data_limit: Optional[int] = Field(None, gt=0)
    expire: Optional[int] = Field(None, gt=0)
    status: Optional[Literal['active', 'disabled']] = None


class MarzbanUserResponseSchema(BaseModel):
    """Схема ответа пользователя Marzban"""
    username: str
    proxies: dict
    data_limit: int
    expire: int
    status: str
    used_traffic: int
    subscription_url: Optional[str] = None
    
    class Config:
        from_attributes = True


# ==================== Config Schemas ====================

class BotConfig(BaseModel):
    """Схема конфигурации бота"""
    environment: Literal['development', 'staging', 'production'] = 'development'
    bot_token: str
    admin_ids: List[int] = Field(default_factory=list)
    marzban_url: str
    marzban_username: str
    marzban_password: str
    database_url: str
    trial_data_limit: int = Field(default=5_368_709_120, gt=0)  # 5 GB
    trial_expire_days: int = Field(default=3, gt=0, le=30)
    api_timeout: int = Field(default=30, gt=0)
    api_retry_attempts: int = Field(default=3, ge=1)
    api_retry_delay: float = Field(default=1.0, ge=0)
    log_level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] = 'INFO'
    enable_logging: bool = True
    log_file: str = 'bot.log'
    
    @validator('bot_token')
    def validate_bot_token(cls, v):
        if not v or len(v) < 20:
            raise ValueError('Invalid bot token format')
        return v
    
    @validator('marzban_url')
    def validate_marzban_url(cls, v):
        if not v.startswith(('http://', 'https://')):
            raise ValueError('Marzban URL must start with http:// or https://')
        return v
    
    @validator('admin_ids')
    def validate_admin_ids(cls, v):
        if not all(isinstance(x, int) and x > 0 for x in v):
            raise ValueError('Admin IDs must be positive integers')
        return v


# ==================== Error Schemas ====================

class ErrorResponseSchema(BaseModel):
    """Схема для ответов об ошибках"""
    error: str
    details: Optional[str] = None
    code: Optional[str] = None
    
    class Config:
        from_attributes = True


class ValidationErrorResponseSchema(BaseModel):
    """Схема для ответов об ошибках валидации"""
    error: str = "Validation error"
    field: str
    message: str
    value: Optional[str] = None


# ==================== Health Check Schemas ====================

class HealthCheckSchema(BaseModel):
    """Схема для health check ответов"""
    status: Literal['healthy', 'unhealthy']
    timestamp: datetime
    checks: dict
    
    class Config:
        from_attributes = True


# ==================== Cache Schemas ====================

class CachedUserSchema(BaseModel):
    """Схема для кэширования данных пользователя"""
    user_id: int
    data: UserResponseSchema
    expires_at: datetime


# ==================== Pagination Schemas ====================

class PaginationParams(BaseModel):
    """Параметры пагинации"""
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=100)
    
    def offset(self) -> int:
        return (self.page - 1) * self.limit


class PaginatedResponse(BaseModel):
    """Базовый ответ с пагинацией"""
    items: List[Union[UserResponseSchema, TransactionResponseSchema, MessageResponseSchema]]
    total: int
    page: int
    limit: int
    pages: int
    
    @validator('pages')
    def calculate_pages(cls, v, values):
        total = values.get('total', 0)
        limit = values.get('limit', 10)
        return max(1, (total + limit - 1) // limit)