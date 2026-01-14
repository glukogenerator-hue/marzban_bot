"""
Валидация входных данных
"""
from typing import Any, Optional
from pydantic import BaseModel, ValidationError
from types.schemas import ErrorResponseSchema, ValidationErrorResponseSchema
from utils.logger import logger


class DataValidator:
    """Централизованная валидация данных"""
    
    @staticmethod
    def validate(model_class: BaseModel, data: dict) -> tuple[bool, Optional[BaseModel], Optional[ValidationErrorResponseSchema]]:
        """
        Валидация данных по Pydantic модели
        
        Returns:
            tuple: (is_valid, validated_model, error_response)
        """
        try:
            validated = model_class(**data)
            return True, validated, None
        except ValidationError as e:
            errors = []
            for error in e.errors():
                errors.append({
                    'field': '.'.join(str(loc) for loc in error['loc']),
                    'message': error['msg'],
                    'type': error['type']
                })
            
            error_response = ValidationErrorResponseSchema(
                field=errors[0]['field'],
                message=errors[0]['message'],
                value=str(data.get(errors[0]['field'], ''))
            )
            
            logger.warning(f"Validation failed: {errors}")
            return False, None, error_response
    
    @staticmethod
    def validate_telegram_id(telegram_id: Any) -> bool:
        """Валидация Telegram ID"""
        try:
            telegram_id = int(telegram_id)
            return telegram_id > 0
        except (ValueError, TypeError):
            return False
    
    @staticmethod
    def validate_username(username: Any) -> bool:
        """Валидация username"""
        if not isinstance(username, str):
            return False
        
        import re
        return bool(re.match(r'^[a-zA-Z0-9_]{3,50}$', username))
    
    @staticmethod
    def validate_message_text(text: Any) -> bool:
        """Валидация текста сообщения"""
        if not isinstance(text, str):
            return False
        
        text = text.strip()
        return 1 <= len(text) <= 4000
    
    @staticmethod
    def validate_data_limit(limit: Any) -> bool:
        """Валидация лимита данных"""
        try:
            limit = int(limit)
            # 1 GB to 10 TB
            return 1_073_741_824 <= limit <= 10_995_116_277_760
        except (ValueError, TypeError):
            return False
    
    @staticmethod
    def validate_expire_days(days: Any) -> bool:
        """Валидация дней истечения"""
        try:
            days = int(days)
            return 1 <= days <= 365
        except (ValueError, TypeError):
            return False
    
    @staticmethod
    def validate_price(price: Any) -> bool:
        """Валидация цены"""
        try:
            price = float(price)
            return price >= 0
        except (ValueError, TypeError):
            return False
    
    @staticmethod
    def validate_url(url: Any) -> bool:
        """Валидация URL"""
        if not isinstance(url, str):
            return False
        
        import re
        pattern = r'^https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/.*)?$'
        return bool(re.match(pattern, url))


# Предопределенные валидаторы
def validate_user_input(data: dict) -> tuple[bool, Optional[dict], Optional[ValidationErrorResponseSchema]]:
    """Валидация входных данных пользователя"""
    from types.schemas import UserCreateSchema
    
    is_valid, model, error = DataValidator.validate(UserCreateSchema, data)
    if is_valid:
        return True, model.dict(), None
    return False, None, error


def validate_subscription_input(data: dict) -> tuple[bool, Optional[dict], Optional[ValidationErrorResponseSchema]]:
    """Валидация данных подписки"""
    from types.schemas import SubscriptionCreateSchema
    
    is_valid, model, error = DataValidator.validate(SubscriptionCreateSchema, data)
    if is_valid:
        return True, model.dict(), None
    return False, None, error


def validate_message_input(data: dict) -> tuple[bool, Optional[dict], Optional[ValidationErrorResponseSchema]]:
    """Валидация сообщения"""
    from types.schemas import MessageCreateSchema
    
    is_valid, model, error = DataValidator.validate(MessageCreateSchema, data)
    if is_valid:
        return True, model.dict(), None
    return False, None, error


# Утилиты для быстрой валидации
def require_valid(model_class: BaseModel, data: dict) -> BaseModel:
    """Валидация с исключением при ошибке"""
    try:
        return model_class(**data)
    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        raise ValueError(f"Invalid data: {e}")


def safe_validate(model_class: BaseModel, data: dict) -> Optional[BaseModel]:
    """Безопасная валидация, возвращает None при ошибке"""
    try:
        return model_class(**data)
    except ValidationError:
        return None