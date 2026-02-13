"""
Тесты для модуля валидации
"""
import pytest
from datetime import datetime
from schemas.schemas import (
    UserCreateSchema,
    SubscriptionCreateSchema,
    MessageCreateSchema,
    MarzbanUserCreateSchema
)
from utils.validation import DataValidator


class TestUserValidation:
    """Тесты валидации пользователя"""
    
    def test_valid_user_create(self):
        """Валидные данные пользователя"""
        data = {
            "telegram_id": 123456789,
            "username": "test_user",
            "first_name": "Test",
            "last_name": "User"
        }
        user = UserCreateSchema(**data)
        assert user.telegram_id == 123456789
        assert user.username == "test_user"
    
    def test_invalid_telegram_id(self):
        """Невалидный Telegram ID"""
        with pytest.raises(ValueError):
            UserCreateSchema(telegram_id=-1, username="test")
    
    def test_invalid_username(self):
        """Невалидный username"""
        with pytest.raises(ValueError):
            UserCreateSchema(telegram_id=123, username="ab")  # Слишком короткий
    
    def test_username_too_long(self):
        """Username слишком длинный"""
        with pytest.raises(ValueError):
            UserCreateSchema(telegram_id=123, username="a" * 33)


class TestSubscriptionValidation:
    """Тесты валидации подписки"""
    
    def test_valid_subscription(self):
        """Валидные данные подписки"""
        data = {
            "username": "user_123",
            "data_limit": 10737418240,  # 10 GB
            "expire_days": 30
        }
        sub = SubscriptionCreateSchema(**data)
        assert sub.data_limit == 10737418240
        assert sub.expire_days == 30
    
    def test_invalid_data_limit(self):
        """Невалидный лимит данных"""
        with pytest.raises(ValueError):
            SubscriptionCreateSchema(
                username="user_123",
                data_limit=100,  # Слишком мало
                expire_days=30
            )
    
    def test_invalid_expire_days(self):
        """Невалидные дни истечения"""
        with pytest.raises(ValueError):
            SubscriptionCreateSchema(
                username="user_123",
                data_limit=10737418240,
                expire_days=400  # Слишком много
            )


class TestMessageValidation:
    """Тесты валидации сообщений"""
    
    def test_valid_message(self):
        """Валидное сообщение"""
        data = {
            "from_telegram_id": 123456,
            "message_text": "Hello, world!"
        }
        msg = MessageCreateSchema(**data)
        assert msg.message_text == "Hello, world!"
    
    def test_empty_message(self):
        """Пустое сообщение"""
        with pytest.raises(ValueError):
            MessageCreateSchema(
                from_telegram_id=123456,
                message_text=""
            )
    
    def test_message_too_long(self):
        """Сообщение слишком длинное"""
        with pytest.raises(ValueError):
            MessageCreateSchema(
                from_telegram_id=123456,
                message_text="a" * 4001
            )


class TestMarzbanUserValidation:
    """Тесты валидации Marzban пользователя"""
    
    def test_valid_marzban_user(self):
        """Валидный пользователь Marzban"""
        data = {
            "username": "user_123",
            "data_limit": 10737418240,
            "expire": int(datetime.utcnow().timestamp()) + 86400 * 30,
            "status": "active"
        }
        user = MarzbanUserCreateSchema(**data)
        assert user.username == "user_123"
        assert user.status == "active"
    
    def test_invalid_status(self):
        """Невалидный статус"""
        with pytest.raises(ValueError):
            MarzbanUserCreateSchema(
                username="user_123",
                data_limit=10737418240,
                expire=1234567890,
                status="invalid_status"
            )


class TestDataValidator:
    """Тесты DataValidator"""
    
    def test_validate_telegram_id(self):
        assert DataValidator.validate_telegram_id(123456) is True
        assert DataValidator.validate_telegram_id(-1) is False
        assert DataValidator.validate_telegram_id("abc") is False
    
    def test_validate_username(self):
        assert DataValidator.validate_username("user_123") is True
        assert DataValidator.validate_username("ab") is False
        assert DataValidator.validate_username("a" * 51) is False
        assert DataValidator.validate_username("user name") is False  # Пробел не допускается
    
    def test_validate_message_text(self):
        assert DataValidator.validate_message_text("Hello") is True
        assert DataValidator.validate_message_text("") is False
        assert DataValidator.validate_message_text("a" * 4001) is False
    
    def test_validate_data_limit(self):
        assert DataValidator.validate_data_limit(1073741824) is True  # 1 GB
        assert DataValidator.validate_data_limit(100) is False  # Слишком мало
        assert DataValidator.validate_data_limit(10995116277761) is False  # Слишком много
    
    def test_validate_expire_days(self):
        assert DataValidator.validate_expire_days(30) is True
        assert DataValidator.validate_expire_days(0) is False
        assert DataValidator.validate_expire_days(400) is False
    
    def test_validate_price(self):
        assert DataValidator.validate_price(300) is True
        assert DataValidator.validate_price(0) is True
        assert DataValidator.validate_price(-10) is False
        assert DataValidator.validate_price("abc") is False
    
    def test_validate_url(self):
        assert DataValidator.validate_url("https://example.com") is True
        assert DataValidator.validate_url("http://test.com/path") is True
        assert DataValidator.validate_url("not_a_url") is False
        assert DataValidator.validate_url("ftp://example.com") is False


class TestValidationHelpers:
    """Тесты вспомогательных функций валидации"""
    
    def test_require_valid_success(self):
        """Успешная валидация с исключением"""
        from utils.validation import require_valid
        
        data = {"telegram_id": 123, "username": "test"}
        result = require_valid(UserCreateSchema, data)
        assert result.telegram_id == 123
    
    def test_require_valid_failure(self):
        """Неуспешная валидация с исключением"""
        from utils.validation import require_valid
        
        with pytest.raises(ValueError):
            require_valid(UserCreateSchema, {"telegram_id": -1})
    
    def test_safe_validate_success(self):
        """Безопасная валидация - успех"""
        from utils.validation import safe_validate
        
        data = {"telegram_id": 123, "username": "test"}
        result = safe_validate(UserCreateSchema, data)
        assert result is not None
        assert result.telegram_id == 123
    
    def test_safe_validate_failure(self):
        """Безопасная валидация - ошибка"""
        from utils.validation import safe_validate
        
        result = safe_validate(UserCreateSchema, {"telegram_id": -1})
        assert result is None