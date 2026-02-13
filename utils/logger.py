import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
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
            
            # Форматтер из настроек или по умолчанию
            formatter = logging.Formatter(
                settings.LOG_FORMAT,
                datefmt=settings.LOG_DATE_FORMAT
            )
            
            # Console handler
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
            
            # Rotating file handler
            try:
                file_handler = RotatingFileHandler(
                    settings.LOG_FILE,
                    maxBytes=settings.LOG_MAX_SIZE,
                    backupCount=settings.LOG_BACKUP_COUNT,
                    encoding='utf-8'
                )
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
                self.logger.info(f"Logging to {settings.LOG_FILE} with rotation")
            except Exception as e:
                # Fallback to basic FileHandler if rotation fails
                self.logger.error(f"Failed to setup rotating logs: {e}")
                file_handler = logging.FileHandler(settings.LOG_FILE, encoding='utf-8')
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
                self.logger.warning("Using basic file handler instead of rotating")
        else:
            self.logger.addHandler(logging.NullHandler())
        
        # Prevent propagation to root logger
        self.logger.propagate = False
    
    def get_logger(self):
        return self.logger

logger = Logger().get_logger()
