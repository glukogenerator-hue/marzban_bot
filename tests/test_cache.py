"""
Тесты для модуля кэширования
"""
import pytest
import asyncio
from datetime import timedelta
from utils.cache import MemoryCache, cache, CACHE_TTL


class TestMemoryCache:
    """Тесты MemoryCache"""
    
    @pytest.mark.asyncio
    async def test_set_get(self):
        """Сохранение и получение из кэша"""
        cache = MemoryCache()
        
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        
        assert result == "value1"
    
    @pytest.mark.asyncio
    async def test_get_nonexistent(self):
        """Получение несуществующего ключа"""
        cache = MemoryCache()
        
        result = await cache.get("nonexistent")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_ttl(self):
        """Проверка TTL"""
        cache = MemoryCache()
        
        await cache.set("key1", "value1", ttl=timedelta(seconds=1))
        
        # Сразу получаем
        result = await cache.get("key1")
        assert result == "value1"
        
        # Ждем и получаем снова
        await asyncio.sleep(1.1)
        result = await cache.get("key1")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_delete(self):
        """Удаление из кэша"""
        cache = MemoryCache()
        
        await cache.set("key1", "value1")
        await cache.delete("key1")
        result = await cache.get("key1")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_clear(self):
        """Очистка кэша"""
        cache = MemoryCache()
        
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.clear()
        
        assert cache.size() == 0
    
    @pytest.mark.asyncio
    async def test_cleanup(self):
        """Очистка просроченных записей"""
        cache = MemoryCache()
        
        await cache.set("permanent", "value", ttl=None)
        await cache.set("expired", "value", ttl=timedelta(seconds=-1))
        
        await cache.cleanup()
        
        assert await cache.get("permanent") == "value"
        assert await cache.get("expired") is None
    
    @pytest.mark.asyncio
    async def test_generate_key(self):
        """Генерация ключа"""
        cache = MemoryCache()
        
        key1 = cache._generate_key("prefix", 123, name="test")
        key2 = cache._generate_key("prefix", 123, name="test")
        key3 = cache._generate_key("prefix", 123, name="other")
        
        assert key1 == key2
        assert key1 != key3


class TestCacheDecorator:
    """Тесты декоратора cache"""
    
    @pytest.mark.asyncio
    async def test_cache_decorator(self):
        """Декоратор кэширования"""
        call_count = 0
        
        @cache(ttl=timedelta(minutes=5), key_prefix="test")
        async def expensive_function(x, y):
            nonlocal call_count
            call_count += 1
            return x + y
        
        # Первый вызов
        result1 = await expensive_function(1, 2)
        assert result1 == 3
        assert call_count == 1
        
        # Второй вызов с теми же параметрами (должен использовать кэш)
        result2 = await expensive_function(1, 2)
        assert result2 == 3
        assert call_count == 1  # Не увеличилось
        
        # Третий вызов с другими параметрами
        result3 = await expensive_function(2, 3)
        assert result3 == 5
        assert call_count == 2
    
    @pytest.mark.asyncio
    async def test_cache_decorator_ttl(self):
        """Декоратор с TTL"""
        call_count = 0
        
        @cache(ttl=timedelta(seconds=0.1))
        async def timed_function():
            nonlocal call_count
            call_count += 1
            return call_count
        
        # Первый вызов
        result1 = await timed_function()
        assert result1 == 1
        assert call_count == 1
        
        # Второй вызов сразу (кэш)
        result2 = await timed_function()
        assert result2 == 1
        assert call_count == 1
        
        # Ждем TTL
        await asyncio.sleep(0.15)
        
        # Третий вызов (новый)
        result3 = await timed_function()
        assert result3 == 2
        assert call_count == 2


class TestUserCache:
    """Тесты UserCache"""
    
    @pytest.mark.asyncio
    async def test_user_cache(self):
        """Кэширование пользователей"""
        from utils.cache import UserCache
        
        user_cache = UserCache()
        
        # Сохраняем пользователя
        user_data = {"id": 123, "name": "Test"}
        await user_cache.set_user(123, user_data)
        
        # Получаем
        result = await user_cache.get_user(123)
        assert result == user_data
        
        # Инвалидируем
        await user_cache.invalidate_user(123)
        result = await user_cache.get_user(123)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_subscription_cache(self):
        """Кэширование подписок"""
        from utils.cache import UserCache
        
        user_cache = UserCache()
        
        sub_data = {"username": "user1", "active": True}
        await user_cache.set_subscription(123, sub_data)
        
        result = await user_cache.get_subscription(123)
        assert result == sub_data


class TestStatsCache:
    """Тесты StatsCache"""
    
    @pytest.mark.asyncio
    async def test_stats_cache(self):
        """Кэширование статистики"""
        from utils.cache import StatsCache
        
        stats_cache = StatsCache()
        
        stats_data = {"total_users": 100, "active": 50}
        await stats_cache.set_stats("general", stats_data, ttl=timedelta(hours=1))
        
        result = await stats_cache.get_stats("general")
        assert result == stats_data
        
        # Инвалидация
        await stats_cache.invalidate_stats("general")
        result = await stats_cache.get_stats("general")
        assert result is None


class TestCacheUtilities:
    """Тесты утилит кэша"""
    
    @pytest.mark.asyncio
    async def test_quick_functions(self):
        """Быстрые функции работы с кэшем"""
        from utils.cache import get_from_cache, set_to_cache, invalidate_cache
        
        # Сохраняем
        await set_to_cache("test_key", "test_value", ttl=timedelta(minutes=5))
        
        # Получаем
        result = await get_from_cache("test_key")
        assert result == "test_value"
        
        # Удаляем
        await invalidate_cache("test_key")
        result = await get_from_cache("test_key")
        assert result is None
    
    def test_cache_ttl_constants(self):
        """Константы TTL"""
        from utils.cache import CACHE_TTL
        
        assert CACHE_TTL['short'].total_seconds() == 300
        assert CACHE_TTL['medium'].total_seconds() == 1800
        assert CACHE_TTL['long'].total_seconds() == 3600
        assert CACHE_TTL['very_long'].total_seconds() == 86400