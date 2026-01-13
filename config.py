from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List, Union

class Settings(BaseSettings):
    # Telegram
    BOT_TOKEN: str
    ADMIN_IDS: Union[List[int], str] = []
    
    @field_validator('ADMIN_IDS', mode='before')
    @classmethod
    def parse_admin_ids(cls, v):
        """Парсинг ADMIN_IDS из строки, списка или int"""
        if v is None:
            return []
        
        # Если уже список, возвращаем как есть
        if isinstance(v, list):
            return [int(x) for x in v if x]
        
        # Если int (одно значение)
        if isinstance(v, int):
            return [v]
        
        # Если строка
        if isinstance(v, str):
            # Убираем квадратные скобки если есть
            v_cleaned = v.strip().strip('[]')
            # Если строка, разбиваем по запятым и конвертируем в int
            if v_cleaned:
                return [int(x.strip()) for x in v_cleaned.split(',') if x.strip()]
        
        return []
    
    @field_validator('ADMIN_IDS', mode='after')
    @classmethod
    def ensure_list(cls, v):
        """Убеждаемся, что результат - список"""
        if isinstance(v, list):
            return v
        return []
    
    # Marzban
    MARZBAN_URL: str
    MARZBAN_USERNAME: str
    MARZBAN_PASSWORD: str
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./bot.db"
    
    # Trial settings
    TRIAL_DATA_LIMIT: int = 10737418240  # 10 GB
    TRIAL_EXPIRE_DAYS: int = 3
    
    # Subscription plans (days, data_limit in bytes, price in rubles)
    SUBSCRIPTION_PLANS: dict = {
        "1": {"days": 30, "data_limit": 107374182400, "price": 300},  # 100 GB
        "3": {"days": 90, "data_limit": 322122547200, "price": 750},  # 300 GB
        "6": {"days": 180, "data_limit": 644245094400, "price": 1000},  # 600 GB
        "12": {"days": 365, "data_limit": 1288490188800, "price": 2000}  # 1.2 TB
    }
    
    # API settings
    API_TIMEOUT: int = 30
    API_RETRY_ATTEMPTS: int = 3
    API_RETRY_DELAY: float = 1.0
    
    # Logging
    LOG_LEVEL: str = "INFO"
    ENABLE_LOGGING: bool = True
    LOG_FILE: str = "bot.log"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
