"""
Кэширование данных для оптимизации производительности
"""
import asyncio
from typing import Any, Optional, Dict, TypeVar, Generic
from datetime import datetime, timedelta
from functools import wraps
import hashlib
import json

from utils.logger import logger

T = TypeVar('T')


class CacheEntry(Generic[T]):
    """Запись в кэше с метаданными"""
    
    def __init__(self, value: T, ttl: Optional[timedelta] = None):
        self.value = value
        self.created_at = datetime.utcnow()
        self.ttl = ttl
        self.expires_at = self.created_at + ttl if ttl else None
    
    def is_expired(self) -> bool:
        """Проверить, истек ли срок действия"""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at


class MemoryCache:
    """In-memory кэш с TTL"""
    
    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()
    
    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """Генерация уникального ключа"""
        key_data = {
            'prefix': prefix,
            'args': args,
            'kwargs': kwargs
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    async def get(self, key: str) -> Optional[Any]:
        """Получить значение из кэша"""
        async with self._lock:
            entry = self._cache.get(key)
            
            if entry is None:
                return None
            
            if entry.is_expired():
                del self._cache[key]
                return None
            
            return entry.value
    
    async def set(self, key: str, value: Any, ttl: Optional[timedelta] = None):
        """Сохранить значение в кэш"""
        async with self._lock:
            self._cache[key] = CacheEntry(value, ttl)
    
    async def delete(self, key: str):
        """Удалить значение из кэша"""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
    
    async def clear(self):
        """Очистить весь кэш"""
        async with self._lock:
            self._cache.clear()
    
    async def cleanup(self):
        """Очистить просроченные записи"""
        async with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
            
            if expired_keys:
                logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")
    
    def size(self) -> int:
        """Размер кэша"""
        return len(self._cache)


# Глобальный экземпляр кэша
memory_cache = MemoryCache()


def cache(ttl: Optional[timedelta] = None, key_prefix: str = ""):
    """
    Декоратор для кэширования результатов функций
    
    Args:
        ttl: Время жизни кэша
        key_prefix: Префикс для ключа кэша
    
    Пример:
        @cache(ttl=timedelta(minutes=5), key_prefix="user")
        async def get_user(user_id: int):
            # ... код
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Генерируем ключ
            cache_key = memory_cache._generate_key(
                key_prefix or func.__name__,
                *args,
                **kwargs
            )
            
            # Пробуем получить из кэша
            cached_value = await memory_cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached_value
            
            # Выполняем функцию
            result = await func(*args, **kwargs)
            
            # Сохраняем в кэш
            await memory_cache.set(cache_key, result, ttl)
            logger.debug(f"Cache miss: {cache_key}")
            
            return result
        return wrapper
    return decorator


class UserCache:
    """Кэш для данных пользователей"""
    
    def __init__(self):
        self.cache = memory_cache
    
    async def get_user(self, telegram_id: int) -> Optional[Any]:
        """Получить пользователя из кэша"""
        key = f"user_{telegram_id}"
        return await self.cache.get(key)
    
    async def set_user(self, telegram_id: int, user_data: Any, ttl: Optional[timedelta] = None):
        """Сохранить пользователя в кэш"""
        key = f"user_{telegram_id}"
        await self.cache.set(key, user_data, ttl)
    
    async def get_subscription(self, telegram_id: int) -> Optional[Any]:
        """Получить подписку из кэша"""
        key = f"subscription_{telegram_id}"
        return await self.cache.get(key)
    
    async def set_subscription(self, telegram_id: int, subscription_data: Any, ttl: Optional[timedelta] = None):
        """Сохранить подписку в кэш"""
        key = f"subscription_{telegram_id}"
        await self.cache.set(key, subscription_data, ttl)
    
    async def invalidate_user(self, telegram_id: int):
        """Инвалидировать кэш пользователя"""
        await self.cache.delete(f"user_{telegram_id}")
        await self.cache.delete(f"subscription_{telegram_id}")


class StatsCache:
    """Кэш для статистики"""
    
    def __init__(self):
        self.cache = memory_cache
    
    async def get_stats(self, stats_type: str) -> Optional[Any]:
        """Получить статистику из кэша"""
        key = f"stats_{stats_type}"
        return await self.cache.get(key)
    
    async def set_stats(self, stats_type: str, data: Any, ttl: Optional[timedelta] = None):
        """Сохранить статистику в кэш"""
        key = f"stats_{stats_type}"
        await self.cache.set(key, data, ttl)
    
    async def invalidate_stats(self, stats_type: str):
        """Инвалидировать статистику"""
        await self.cache.delete(f"stats_{stats_type}")


# Предопределенные TTL
CACHE_TTL = {
    'short': timedelta(minutes=5),    # Для часто меняющихся данных
    'medium': timedelta(minutes=30),  # Для пользователей
    'long': timedelta(hours=1),       # Для статистики
    'very_long': timedelta(days=1),   # Для редко меняющихся данных
}


# Удобные функции
async def get_from_cache(key: str) -> Optional[Any]:
    """Быстрое получение из кэша"""
    return await memory_cache.get(key)


async def set_to_cache(key: str, value: Any, ttl: Optional[timedelta] = None):
    """Быстрое сохранение в кэш"""
    await memory_cache.set(key, value, ttl)


async def invalidate_cache(key: str):
    """Быстрая инвалидация"""
    await memory_cache.delete(key)


async def cleanup_cache():
    """Очистка кэша"""
    await memory_cache.cleanup()


# Автоматическая очистка каждые 5 минут
async def periodic_cleanup():
    """Периодическая очистка просроченных записей"""
    while True:
        try:
            await asyncio.sleep(300)  # 5 минут
            await cleanup_cache()
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}")


# Запуск фоновой задачи очистки
def start_cache_cleanup():
    """Запустить фоновую очистку кэша"""
    asyncio.create_task(periodic_cleanup())
    logger.info("Cache cleanup task started")