from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # Telegram
    BOT_TOKEN: str
    ADMIN_IDS: List[int] = []
    
    # Marzban
    MARZBAN_URL: str
    MARZBAN_USERNAME: str
    MARZBAN_PASSWORD: str
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./bot.db"
    
    # Trial settings
    TRIAL_DATA_LIMIT: int = 5368709120  # 5 GB
    TRIAL_EXPIRE_DAYS: int = 3
    
    # Logging
    LOG_LEVEL: str = "INFO"
    ENABLE_LOGGING: bool = True
    LOG_FILE: str = "bot.log"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
