import logging
import sys
from pathlib import Path
from config import settings

class Logger:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.logger = logging.getLogger("MarzbanBot")
        
        if settings.ENABLE_LOGGING:
            self.logger.setLevel(getattr(logging, settings.LOG_LEVEL))
            
            # Форматтер
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            
            # Console handler
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
            
            # File handler
            file_handler = logging.FileHandler(settings.LOG_FILE, encoding='utf-8')
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
        else:
            self.logger.addHandler(logging.NullHandler())
    
    def get_logger(self):
        return self.logger

logger = Logger().get_logger()
