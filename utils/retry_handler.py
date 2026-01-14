"""
Единый механизм ретраев и обработки ошибок
"""
import asyncio
import logging
from typing import Callable, Any, Tuple, Type, Optional
from functools import wraps
from datetime import datetime, timedelta
import aiohttp

logger = logging.getLogger("RetryHandler")


class RetryConfig:
    """Конфигурация для ретраев"""
    def __init__(
        self,
        max_attempts: int = 3,
        backoff_factor: float = 1.5,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        max_wait: float = 30.0,
        jitter: bool = True
    ):
        self.max_attempts = max_attempts
        self.backoff_factor = backoff_factor
        self.exceptions = exceptions
        self.max_wait = max_wait
        self.jitter = jitter


class CircuitBreaker:
    """Паттерн Circuit Breaker для защиты от перегрузки"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        
    def record_failure(self):
        """Записать неудачный вызов"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit breaker OPENED after {self.failure_count} failures")
    
    def record_success(self):
        """Записать успешный вызов"""
        self.failure_count = 0
        self.state = "CLOSED"
    
    def can_attempt(self) -> bool:
        """Проверить, можно ли выполнить вызов"""
        if self.state == "CLOSED":
            return True
        
        if self.state == "OPEN":
            if self.last_failure_time:
                time_since_failure = (datetime.now() - self.last_failure_time).total_seconds()
                if time_since_failure >= self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    logger.info("Circuit breaker entering HALF_OPEN state")
                    return True
            return False
        
        if self.state == "HALF_OPEN":
            return True
        
        return False


class RetryHandler:
    """Управление ретраями и ошибками"""
    
    def __init__(self):
        self.circuit_breakers = {}
    
    def get_circuit_breaker(self, key: str, failure_threshold: int = 5, recovery_timeout: int = 60) -> CircuitBreaker:
        """Получить или создать circuit breaker для ключа"""
        if key not in self.circuit_breakers:
            self.circuit_breakers[key] = CircuitBreaker(failure_threshold, recovery_timeout)
        return self.circuit_breakers[key]
    
    async def execute_with_retry(
        self,
        func: Callable,
        *args,
        config: Optional[RetryConfig] = None,
        circuit_breaker_key: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Выполнить функцию с ретраями и обработкой ошибок
        
        Args:
            func: Асинхронная функция для выполнения
            *args: Аргументы функции
            config: Конфигурация ретраев
            circuit_breaker_key: Ключ для circuit breaker (если None - не используется)
            **kwargs: Именованные аргументы функции
        
        Returns:
            Результат выполнения функции
        
        Raises:
            Exception: Если все попытки исчерпаны
        """
        if config is None:
            config = RetryConfig()
        
        circuit_breaker = None
        if circuit_breaker_key:
            circuit_breaker = self.get_circuit_breaker(circuit_breaker_key)
        
        last_exception = None
        
        for attempt in range(1, config.max_attempts + 1):
            # Проверяем circuit breaker
            if circuit_breaker and not circuit_breaker.can_attempt():
                raise Exception("Circuit breaker is OPEN. Service temporarily unavailable.")
            
            try:
                result = await func(*args, **kwargs)
                
                # Успешное выполнение
                if circuit_breaker:
                    circuit_breaker.record_success()
                
                if attempt > 1:
                    logger.info(f"Success after {attempt} attempts for {func.__name__}")
                
                return result
                
            except config.exceptions as e:
                last_exception = e
                
                # Записываем неудачу в circuit breaker
                if circuit_breaker:
                    circuit_breaker.record_failure()
                
                # Если это последняя попытка - логируем и выходим
                if attempt == config.max_attempts:
                    logger.error(
                        f"Failed after {config.max_attempts} attempts for {func.__name__}: {e}"
                    )
                    break
                
                # Вычисляем время ожидания
                wait_time = config.backoff_factor ** (attempt - 1)
                
                # Добавляем jitter для предотвращения thundering herd
                if config.jitter:
                    import random
                    wait_time = wait_time * (0.5 + random.random() * 0.5)
                
                # Ограничиваем максимальное время ожидания
                wait_time = min(wait_time, config.max_wait)
                
                logger.warning(
                    f"Attempt {attempt}/{config.max_attempts} failed for {func.__name__}: {e}. "
                    f"Retrying in {wait_time:.2f}s..."
                )
                
                await asyncio.sleep(wait_time)
        
        # Все попытки исчерпаны
        raise last_exception


# Глобальный экземпляр
retry_handler = RetryHandler()


def retry(
    max_attempts: int = 3,
    backoff_factor: float = 1.5,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    circuit_breaker_key: Optional[str] = None,
    failure_threshold: int = 5,
    recovery_timeout: int = 60
):
    """
    Декоратор для ретраев функций
    
    Пример использования:
        @retry(max_attempts=3, exceptions=(aiohttp.ClientError,))
        async def fetch_data():
            # ... код функции
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            config = RetryConfig(
                max_attempts=max_attempts,
                backoff_factor=backoff_factor,
                exceptions=exceptions
            )
            
            return await retry_handler.execute_with_retry(
                func,
                *args,
                config=config,
                circuit_breaker_key=circuit_breaker_key,
                **kwargs
            )
        
        return wrapper
    return decorator


# Предопределенные конфигурации
RETRY_CONFIGS = {
    "api": RetryConfig(
        max_attempts=3,
        backoff_factor=1.5,
        exceptions=(aiohttp.ClientError, asyncio.TimeoutError),
        max_wait=10.0
    ),
    "database": RetryConfig(
        max_attempts=2,
        backoff_factor=1.2,
        exceptions=(Exception,),
        max_wait=5.0
    ),
    "critical": RetryConfig(
        max_attempts=5,
        backoff_factor=2.0,
        exceptions=(Exception,),
        max_wait=30.0
    )
}


async def execute_with_fallback(
    primary_func: Callable,
    fallback_func: Callable,
    *args,
    **kwargs
) -> Any:
    """
    Выполнить функцию с fallback на запасной вариант
    
    Args:
        primary_func: Основная функция
        fallback_func: Запасная функция
        *args, **kwargs: Аргументы
    
    Returns:
        Результат основной или запасной функции
    """
    try:
        return await primary_func(*args, **kwargs)
    except Exception as e:
        logger.warning(f"Primary function failed, using fallback: {e}")
        try:
            return await fallback_func(*args, **kwargs)
        except Exception as fallback_error:
            logger.error(f"Fallback also failed: {fallback_error}")
            raise


class ErrorHandler:
    """Централизованная обработка ошибок"""
    
    @staticmethod
    def log_error(error: Exception, context: str = ""):
        """Логирование ошибки с контекстом"""
        logger.error(f"{context}: {type(error).__name__}: {error}")
    
    @staticmethod
    def is_retryable_error(error: Exception) -> bool:
        """Проверить, можно ли повторить операцию при этой ошибке"""
        retryable_errors = (
            aiohttp.ClientError,
            asyncio.TimeoutError,
            ConnectionError,
            TimeoutError
        )
        return isinstance(error, retryable_errors)
    
    @staticmethod
    def format_user_error(error: Exception) -> str:
        """Форматировать ошибку для показа пользователю"""
        if isinstance(error, aiohttp.ClientError):
            return "❌ Сервис временно недоступен. Попробуйте позже."
        elif isinstance(error, asyncio.TimeoutError):
            return "⏰ Превышено время ожидания. Попробуйте еще раз."
        elif isinstance(error, ValueError):
            return f"❌ Ошибка в данных: {error}"
        else:
            return "❌ Произошла ошибка. Попробуйте позже."